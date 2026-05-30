import uvicorn
import webbrowser
import sys
import os
import json
import base64
import shutil
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, os.path.dirname(__file__))

from database import (  # noqa: E402
    init_db, get_db, get_setting, set_setting,
    get_dashboard_stats, get_daily_correct_rate, get_category_accuracy,
    get_top_errors, get_daily_heatmap_data,
    get_all_questions, get_all_code_questions,
    get_question_by_id, get_code_question_by_id, get_random_code_question,
    insert_question, update_question, delete_question, can_delete_question,
    insert_code_question, update_code_question, delete_code_question, can_delete_code_question,
    get_distinct_categories,
    reset_records, reset_all_questions,
    export_questions_json, export_code_questions_json,
    import_questions_json, import_code_questions_json,
    get_ai_reports, save_answer_record,
    get_question, get_daily_question, update_sm2,
    save_answer_with_id, get_latest_answer_record, update_answer_self_assessment,
    get_related_questions, get_wrong_tags,
    get_all_tags, get_question_by_assessment, get_question_by_tag, get_assessment_counts,
    DB_PATH,
)

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ReviewMate", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
app.state.templates = templates


def _api_key_configured():
    key = get_setting("api_key")
    return bool(key and key.strip())


def _decode_api_key():
    key = get_setting("api_key")
    if not key:
        return ""
    try:
        return base64.b64decode(key).decode("utf-8")
    except Exception:
        return key


def _render(page, request, title="", **kwargs):
    return templates.TemplateResponse("base.html", {
        "request": request, "page": page, "title": title, **kwargs,
    })


# ========== Page Routes ==========

@app.get("/", response_class=HTMLResponse)
async def page_dashboard(request: Request):
    stats = get_dashboard_stats()
    trend = get_daily_correct_rate(7)
    chart_dates = [r["date"] for r in trend]
    chart_rates = [round(r["correct"] / r["total"] * 100, 1) if r["total"] > 0 else 0 for r in trend]
    wrong_tags = get_wrong_tags(8)
    mastered = 0
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM sm2_state WHERE repetitions >= 3 AND easiness >= 2.5"
        ).fetchone()
        mastered = row[0] if row else 0
    correct_rate = 0
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as t, SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END) as c "
            "FROM answer_records WHERE date(timestamp) >= date('now','localtime','-7 days')"
        ).fetchone()
        if row and row["t"] > 0:
            correct_rate = round(row["c"] / row["t"] * 100, 1)
    stats["correct_rate"] = correct_rate
    stats["mastered"] = mastered
    with get_db() as conn:
        stats["total_code"] = conn.execute("SELECT COUNT(*) FROM code_questions").fetchone()[0]
    return _render("dashboard", request, title="仪表盘",
                   stats=stats, total_questions=stats["today_completed"],
                   correct_rate=correct_rate, streak=stats["streak_days"],
                   mastered=mastered, wrong_tags=wrong_tags,
                   chart_dates=chart_dates, chart_rates=chart_rates)


@app.get("/practice", response_class=HTMLResponse)
async def page_practice(request: Request, mode: str = "daily",
                         filter_type: str = "", filter_value: str = ""):
    question = None
    if mode == "daily":
        question = get_daily_question("daily")
    elif mode == "review":
        question = get_daily_question("review")
    elif mode == "category":
        if filter_type == "assessment" and filter_value:
            question = get_question_by_assessment(filter_value)
        elif filter_type == "tag" and filter_value:
            question = get_question_by_tag(filter_value)
    tags = get_all_tags() if mode == "category" else []
    counts = get_assessment_counts() if mode == "category" else {}

    # HTMX requests: return just the practice-content fragment
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("practice_content.html", {
            "request": request, "mode": mode, "question": question,
            "filter_type": filter_type, "filter_value": filter_value,
            "all_tags": tags, "assessment_counts": counts,
        })

    return _render("practice", request, title="每日练习", mode=mode,
                   question=question, filter_type=filter_type,
                   filter_value=filter_value, all_tags=tags, assessment_counts=counts)


@app.get("/practice/free", response_class=HTMLResponse)
async def page_free_practice(request: Request, category: str = "Python", question_id: int = None):
    if question_id:
        q = get_code_question_by_id(question_id)
    else:
        q = get_random_code_question(category)
    if q and isinstance(q.get("test_cases"), str):
        try:
            q["test_cases"] = json.loads(q["test_cases"])
        except (json.JSONDecodeError, TypeError):
            pass
    return _render("free_practice", request, title="自由练习",
                   category=category, code_question=q)


@app.get("/library", response_class=HTMLResponse)
async def page_library(request: Request):
    categories = get_distinct_categories()
    questions, q_total = get_all_questions(limit=50)
    code_qs, cq_total = get_all_code_questions(limit=50)
    return _render("library", request, title="我的题库",
                   categories=categories, questions=questions, q_total=q_total,
                   code_questions=code_qs, cq_total=cq_total)


@app.get("/stats", response_class=HTMLResponse)
async def page_stats(request: Request):
    trend_data = get_daily_correct_rate(30)
    radar_data = get_category_accuracy()
    error_data = get_top_errors(5)
    heatmap_data = get_daily_heatmap_data(365)
    reports = get_ai_reports()
    return _render("stats", request, title="统计中心",
                   trend_data=trend_data, radar_data=radar_data,
                   error_data=error_data, heatmap_data=heatmap_data,
                   reports=reports)


@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    api_key_set = _api_key_configured()
    daily_reminder = get_setting("daily_reminder") or "on"
    default_mode = get_setting("default_mode") or "daily"
    return _render("settings", request, title="设置",
                   api_key_set=api_key_set, daily_reminder=daily_reminder,
                   default_mode=default_mode)


# ========== API: Test ==========

@app.get("/api/test")
async def api_test():
    return {"status": "ok"}


# ========== Module 2: Submit Answer & SM-2 ==========

@app.post("/api/submit-answer")
async def api_submit_answer(request: Request, question_id: int = Form(...),
                            question_type: str = Form(...), user_answer: str = Form(""),
                            mode: str = Form("daily"), self_assessment: str = Form(""),
                            filter_type: str = Form(""), filter_value: str = Form("")):
    if self_assessment:
        record = get_latest_answer_record(question_id, question_type)
        if record:
            update_answer_self_assessment(record["id"], self_assessment)
            update_sm2(question_id, question_type, self_assessment)
        params = f"mode={mode}"
        if filter_type:
            params += f"&filter_type={filter_type}&filter_value={filter_value}"
        next_url = f"/api/next-question?{params}"
        return HTMLResponse(
            f'<div class="toast toast-success" style="text-align:center;padding:24px;">'
            f'<p style="font-size:1.1rem;margin-bottom:8px;">自评已记录，即将进入下一题...</p>'
            f'</div>'
            f'<div hx-get="{next_url}" hx-trigger="load delay:0.6s"'
            f' hx-target="#question-container" hx-swap="innerHTML"></div>')
    q = get_question(question_id, question_type)
    if not q:
        return HTMLResponse('<div class="toast toast-error">题目不存在。</div>')
    is_correct = False
    match_details = {}
    if question_type == "choice":
        is_correct = user_answer.strip() == q["answer"].strip()
        match_details = {"mode": "exact", "correct": is_correct}
    elif question_type == "open":
        match_mode = q.get("answer_match_mode", "exact")
        user_clean = user_answer.strip()
        answer_clean = q["answer"].strip()
        if match_mode == "exact":
            is_correct = user_clean == answer_clean
            match_details = {"mode": "exact", "correct": is_correct}
        elif match_mode == "normalized":
            import re
            def normalize(s):
                return re.sub(r'\s+', '', s).lower()
            is_correct = normalize(user_clean) == normalize(answer_clean)
            match_details = {"mode": "normalized", "correct": is_correct}
        elif match_mode == "keywords":
            keywords = q.get("keywords", [])
            if isinstance(keywords, str):
                try:
                    keywords = json.loads(keywords)
                except (json.JSONDecodeError, TypeError):
                    keywords = []
            user_lower = user_clean.lower()
            missing = [kw for kw in keywords if kw.lower() not in user_lower]
            is_correct = len(missing) == 0
            match_details = {"mode": "keywords", "correct": is_correct,
                             "missing_keywords": missing, "required_keywords": keywords}
    record_id = save_answer_with_id(
        question_id=question_id, question_type=question_type,
        user_answer=user_answer, is_correct=is_correct,
        match_details=match_details, mode=mode)
    return templates.TemplateResponse("partials/answer_result.html", {
        "request": request, "is_correct": is_correct, "match_details": match_details,
        "question": q, "user_answer": user_answer, "record_id": record_id,
        "question_id": question_id, "question_type": question_type, "mode": mode,
        "filter_type": filter_type, "filter_value": filter_value,
        "answer": q.get("answer", ""), "explanation": q.get("explanation", ""),
    })


# ========== Module 3: Next Question API ==========

@app.get("/api/next-question")
async def api_next_question(request: Request, mode: str = "daily",
                             filter_type: str = "", filter_value: str = "",
                             question_id: int = 0):
    """Return just the question card (or empty state) for auto-next after self-assessment."""
    question = None
    if question_id:
        question = get_question_by_id(question_id)
        if question:
            for field in ('tags', 'options', 'keywords'):
                val = question.get(field)
                if val and isinstance(val, str):
                    try:
                        question[field] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        pass
    elif mode == "daily":
        question = get_daily_question("daily")
    elif mode == "review":
        question = get_daily_question("review")
    elif mode == "category":
        if filter_type == "assessment" and filter_value:
            question = get_question_by_assessment(filter_value)
        elif filter_type == "tag" and filter_value:
            question = get_question_by_tag(filter_value)

    if question:
        return templates.TemplateResponse("partials/question_card.html", {
            "request": request, "question": question, "mode": mode,
            "filter_type": filter_type, "filter_value": filter_value,
        })
    else:
        # Return empty state appropriate for the mode
        empty_html = ""
        if mode == 'review':
            empty_html = (
                '<div class="card empty-state"><div class="card-body text-center">'
                '<p style="font-size:1.1rem;margin-bottom:8px;">🎉 暂无待复习的题目</p>'
                '<p class="text-muted">所有题目都已掌握！</p>'
                '<button class="btn btn-primary mt-3"'
                ' hx-get="/practice?mode=daily" hx-target="#practice-content" hx-swap="innerHTML">📝 去每日练习</button>'
                '</div></div>')
        elif mode == 'category' and filter_type:
            empty_html = (
                '<div class="card empty-state"><div class="card-body text-center">'
                '<p style="font-size:1.1rem;margin-bottom:8px;">🎉 该分类暂无更多题目</p>'
                '<button class="btn btn-primary mt-3"'
                ' hx-get="/practice?mode=category" hx-target="#practice-content" hx-swap="innerHTML">🔙 返回分类选择</button>'
                '</div></div>')
        else:
            empty_html = (
                '<div class="card empty-state"><div class="card-body text-center">'
                '<p style="font-size:1.1rem;margin-bottom:8px;">📝 准备开始练习</p>'
                '<button class="btn btn-primary mt-3"'
                ' hx-get="/api/next-question?mode=daily" hx-target="#question-container" hx-swap="innerHTML">🎯 开始答题</button>'
                '</div></div>')
        return HTMLResponse(empty_html)


# ========== Module 3: Code Questions & Judging ==========

@app.get("/api/code-question/{question_id}")
async def api_get_code_question(request: Request, question_id: int):
    q = get_code_question_by_id(question_id)
    if not q:
        return HTMLResponse("<p class='empty-state'>题目未找到</p>", status_code=404)
    if isinstance(q.get("test_cases"), str):
        try:
            q["test_cases"] = json.loads(q["test_cases"])
        except (json.JSONDecodeError, TypeError):
            pass
    return templates.TemplateResponse("partials/question_desc.html", {
        "request": request, "question": q})


@app.get("/api/random-code-question")
async def api_random_code_question(request: Request, category: str = "Python"):
    q = get_random_code_question(category)
    if not q:
        return HTMLResponse("<p class='empty-state'>暂无编程题</p>")
    if isinstance(q.get("test_cases"), str):
        try:
            q["test_cases"] = json.loads(q["test_cases"])
        except (json.JSONDecodeError, TypeError):
            pass
    return templates.TemplateResponse("partials/question_desc.html", {
        "request": request, "question": q})


@app.post("/api/judge")
async def api_judge(request: Request, code: str = Form(...), language: str = Form(...),
                    question_id: int = Form(...)):
    q = get_code_question_by_id(question_id)
    if not q:
        return HTMLResponse("<p class='empty-state'>题目未找到</p>", status_code=404)
    test_cases = json.loads(q["test_cases"]) if isinstance(q["test_cases"], str) else q["test_cases"]
    try:
        from judge_sandbox import judge_submission
        result = judge_submission(code=code, language=language, test_cases=test_cases,
                                  time_limit_ms=q.get("time_limit_ms", 2000),
                                  memory_limit_mb=q.get("memory_limit_mb", 128))
    except ImportError:
        return HTMLResponse('<div class="toast toast-error">判题模块未加载。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">判题失败：{str(e)}</div>')
    is_correct = result.get("status") == "Accepted"
    save_answer_record(question_id=question_id, question_type="code",
                       user_answer=code, is_correct=is_correct,
                       match_details={"status": result.get("status"),
                                      "passed_cases": result.get("passed_cases", 0),
                                      "total_cases": result.get("total_cases", 0),
                                      "total_time_ms": result.get("total_time_ms", 0),
                                      "language": language},
                       mode="free")
    return templates.TemplateResponse("partials/judge_result.html", {
        "request": request, "result": result})


# ========== Module 4: Consolidation Practice ==========

@app.get("/api/related-questions/{qid}")
async def api_related_questions(request: Request, qid: int,
                                 qtype: str = "choice", count: int = 5):
    """Return related questions for consolidation practice after a wrong answer."""
    questions = get_related_questions(qid, qtype, count)
    if not questions:
        return HTMLResponse('<p class="text-muted" style="padding:12px;">暂无相关题目，多做一些题后会有更多推荐。</p>')
    html = '<div class="related-questions-list">'
    html += '<p style="font-weight:600;margin-bottom:8px;">📚 巩固练习 — 同知识点题目：</p>'
    for i, q in enumerate(questions):
        tags_str = ', '.join(q.get('tags', [])) if q.get('tags') else ''
        html += (
            f'<div class="related-q-item" style="padding:8px 10px;margin-bottom:6px;'
            f'background:var(--color-bg);border-radius:6px;border:1px solid var(--color-border);'
            f'cursor:pointer;transition:background 0.15s;"'
            f' hx-get="/api/next-question?question_id={q["id"]}&mode=daily"'
            f' hx-target="#question-container" hx-swap="innerHTML"'
            f' onmouseover="this.style.background=\'var(--color-primary-bg)\'"'
            f' onmouseout="this.style.background=\'var(--color-bg)\'">'
            f'<span style="font-weight:500;">{i+1}. </span>'
            f'<span class="badge badge-info" style="margin-right:6px;">{q["category"]}</span>'
            f'{q["content"][:80]}{"..." if len(q.get("content","")) > 80 else ""}'
            f'<span style="color:var(--color-text-muted);font-size:.8rem;margin-left:6px;">{tags_str}</span>'
            f'</div>')
    html += '</div>'
    return HTMLResponse(html)


# ========== Module 5: Stats Charts ==========

@app.get("/api/stats/trend")
async def api_stats_trend(days: int = 30):
    return get_daily_correct_rate(days)


@app.get("/api/stats/radar")
async def api_stats_radar():
    return get_category_accuracy()


@app.get("/api/stats/errors")
async def api_stats_errors(limit: int = 5):
    return get_top_errors(limit)


@app.get("/api/stats/heatmap")
async def api_stats_heatmap(days: int = 365):
    return get_daily_heatmap_data(days)


# ========== Module 5: Reports ==========

@app.post("/api/generate-report")
async def api_generate_report(request: Request):
    if not _api_key_configured():
        return HTMLResponse(
            '<div class="toast toast-error">请先在设置页面配置 DeepSeek API Key。</div>')
    try:
        from ai_client import generate_report as ai_generate_report
        trend = get_daily_correct_rate(30)
        radar = get_category_accuracy()
        errors = get_top_errors(5)
        stats_summary = json.dumps({
            "trend_30_days": trend, "category_accuracy": radar, "top_errors": errors,
        }, ensure_ascii=False)
        report_text = await ai_generate_report(stats_summary)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO ai_reports (report_type, content) VALUES (?,?)",
                ("weekly", report_text))
            conn.commit()
        reports = get_ai_reports()
        html = '<div class="toast toast-success">报告已生成！</div>'
        html += (f'<div class="card mt-3"><div class="report-content"'
                 f' style="white-space:pre-wrap;">{report_text}</div></div>')
        html += '<h4 class="mt-3">历史报告</h4><div class="report-list">'
        for r in reports:
            html += (f'<div class="report-item" hx-get="/api/report/{r["id"]}"'
                     f' hx-target="#report-detail" hx-swap="innerHTML">'
                     f'<div><span class="report-type">{r["report_type"] or "学习报告"}</span></div>'
                     f'<span class="report-date">{r["created_at"]}</span></div>')
        html += '</div><div id="report-detail" class="mt-3"></div>'
        return HTMLResponse(html)
    except ImportError:
        return HTMLResponse('<div class="toast toast-error">AI 模块未加载。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">生成报告失败：{str(e)}</div>')


@app.get("/api/report/{report_id}")
async def api_get_report(report_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ai_reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        return HTMLResponse('<div class="toast toast-error">报告不存在。</div>')
    r = dict(row)
    return HTMLResponse(
        f'<div class="card mt-3"><h4>{r["report_type"] or "学习报告"}</h4>'
        f'<div style="white-space:pre-wrap;font-size:0.9rem;">{r["content"]}</div>'
        f'<div class="text-muted" style="font-size:0.8rem;">{r["created_at"]}</div></div>')


# ========== Module 5: Library CRUD ==========

@app.get("/api/library/questions")
async def api_library_questions(category: str = "", search: str = "",
                                offset: int = 0, limit: int = 50):
    cat = category if category else None
    s = search if search else None
    qs, total = get_all_questions(cat, s, offset, limit)
    html = ""
    for q in qs:
        tags = []
        try:
            tags = json.loads(q["tags"]) if q.get("tags") else []
        except (json.JSONDecodeError, TypeError):
            tags = [q["tags"]] if q.get("tags") else []
        tags_html = "".join(f'<span class="tag-chip">{t}</span>' for t in tags)
        src = q.get("source", "manual")
        html += (
            f'<tr>'
            f'<td><input type="checkbox" class="q-checkbox" value="{q["id"]}"></td>'
            f'<td>{q["id"]}</td>'
            f'<td><span class="badge badge-info">{q["category"]}</span></td>'
            f'<td><div class="tags-display">{tags_html}</div></td>'
            f'<td><span class="badge badge-type">{"选择" if q["type"] == "choice" else "简答"}</span></td>'
            f'<td><span class="badge badge-warning">{q.get("difficulty", "medium")}</span></td>'
            f'<td><span class="badge badge-source-{"ai" if src == "ai" else "info"}">{src}</span></td>'
            f'<td><div class="table-actions">'
            f'<button class="btn btn-sm btn-primary" hx-get="/api/library/question-form/{q["id"]}"'
            f' hx-target="#modal-container" hx-swap="innerHTML" onclick="openModal()">编辑</button>'
            f'<button class="btn btn-sm btn-danger" hx-delete="/api/library/question/{q["id"]}"'
            f' hx-target="closest tr" hx-swap="outerHTML" hx-confirm="确定删除此题目？">删除</button>'
            f'</div></td></tr>')
    if not qs:
        html = '<tr><td colspan="8" class="empty-state">暂无数据</td></tr>'
    return JSONResponse({"rows_html": html, "total": total, "offset": offset, "limit": limit})


@app.get("/api/library/code-questions")
async def api_library_code_questions(category: str = "", search: str = "",
                                     offset: int = 0, limit: int = 50):
    cat = category if category else None
    s = search if search else None
    qs, total = get_all_code_questions(cat, s, offset, limit)
    html = ""
    for q in qs:
        src = q.get("source", "manual")
        html += (
            f'<tr>'
            f'<td><input type="checkbox" class="cq-checkbox" value="{q["id"]}"></td>'
            f'<td>{q["id"]}</td><td>{q["title"]}</td>'
            f'<td><span class="badge badge-info">{q["category"]}</span></td>'
            f'<td><span class="badge badge-warning">{q.get("difficulty", "medium")}</span></td>'
            f'<td><span class="badge badge-source-{"ai" if src == "ai" else "info"}">{src}</span></td>'
            f'<td><div class="table-actions">'
            f'<button class="btn btn-sm btn-primary" hx-get="/api/library/code-question-form/{q["id"]}"'
            f' hx-target="#modal-container" hx-swap="innerHTML" onclick="openModal()">编辑</button>'
            f'<button class="btn btn-sm btn-danger" hx-delete="/api/library/code-question/{q["id"]}"'
            f' hx-target="closest tr" hx-swap="outerHTML" hx-confirm="确定删除此编程题？">删除</button>'
            f'</div></td></tr>')
    if not qs:
        html = '<tr><td colspan="7" class="empty-state">暂无数据</td></tr>'
    return JSONResponse({"rows_html": html, "total": total, "offset": offset, "limit": limit})


@app.get("/api/library/question-form/{qid}")
async def api_library_question_form(request: Request, qid: int):
    if qid == 0:
        q = {"id": 0, "category": "", "tags": [], "type": "choice", "difficulty": "medium",
             "content": "", "options": [], "answer": "", "answer_match_mode": "exact",
             "keywords": [], "explanation": "", "source": "manual"}
    else:
        q = get_question_by_id(qid)
        if not q:
            return HTMLResponse('<div class="toast toast-error">题目不存在</div>')
        for field in ('tags', 'options', 'keywords'):
            val = q.get(field)
            if val and isinstance(val, str):
                try:
                    q[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
    return templates.TemplateResponse("partials/question_form.html", {
        "request": request, "q": q})


@app.get("/api/library/code-question-form/{qid}")
async def api_library_code_question_form(request: Request, qid: int):
    if qid == 0:
        q = {"id": 0, "title": "", "category": "Python", "tags": [], "difficulty": "medium",
             "description": "", "input_format": "", "output_format": "",
             "sample_input": "", "sample_output": "",
             "template_code": "",
             "test_cases": [{"input": "", "expected_output": ""}],
             "time_limit_ms": 2000, "memory_limit_mb": 128, "stack_limit_mb": 64,
             "solution_code": "", "source": "manual"}
    else:
        q = get_code_question_by_id(qid)
        if not q:
            return HTMLResponse('<div class="toast toast-error">题目不存在</div>')
        if isinstance(q.get("test_cases"), str):
            try:
                q["test_cases"] = json.loads(q["test_cases"])
            except (json.JSONDecodeError, TypeError):
                q["test_cases"] = []
        if isinstance(q.get("tags"), str):
            try:
                q["tags"] = json.loads(q["tags"])
            except (json.JSONDecodeError, TypeError):
                q["tags"] = []
    return templates.TemplateResponse("partials/code_question_form.html", {
        "request": request, "q": q})


@app.post("/api/library/question")
async def api_library_save_question(
    request: Request, qid: int = Form(0), category: str = Form(...),
    tags: str = Form(""), qtype: str = Form(...), difficulty: str = Form("medium"),
    content: str = Form(...), options: str = Form(""), answer: str = Form(...),
    answer_match_mode: str = Form("exact"), keywords: str = Form(""),
    explanation: str = Form("")):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    opt_list = [o.strip() for o in options.split("\n") if o.strip()]
    data = {
        "category": category, "tags": tag_list, "type": qtype,
        "difficulty": difficulty, "content": content,
        "options": opt_list if qtype == "choice" else [],
        "answer": answer, "answer_match_mode": answer_match_mode,
        "keywords": kw_list, "explanation": explanation, "source": "manual"}
    if qid and qid > 0:
        update_question(qid, data)
        msg = "题目已更新"
    else:
        insert_question(data)
        msg = "题目已添加"
    return HTMLResponse(
        f'<div class="toast toast-success">{msg}</div>'
        '<script>setTimeout(function(){closeModal();refreshLibraryQuestions();},600);</script>')


@app.post("/api/library/code-question")
async def api_library_save_code_question(
    request: Request, qid: int = Form(0), title: str = Form(...),
    category: str = Form(...), tags: str = Form(""),
    difficulty: str = Form("medium"), description: str = Form(...),
    input_format: str = Form(""), output_format: str = Form(""),
    sample_input: str = Form(""), sample_output: str = Form(""),
    template_code: str = Form(""), test_cases: str = Form("[]"),
    time_limit_ms: int = Form(2000), memory_limit_mb: int = Form(128),
    stack_limit_mb: int = Form(64),
    solution_code: str = Form("")):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        tc = json.loads(test_cases)
    except json.JSONDecodeError:
        tc = [{"input": "", "expected_output": ""}]
    data = {
        "title": title, "category": category, "tags": tag_list,
        "difficulty": difficulty, "description": description,
        "input_format": input_format, "output_format": output_format,
        "sample_input": sample_input, "sample_output": sample_output,
        "template_code": template_code, "test_cases": tc,
        "time_limit_ms": time_limit_ms, "memory_limit_mb": memory_limit_mb,
        "stack_limit_mb": stack_limit_mb,
        "solution_code": solution_code, "source": "manual"}
    if qid and qid > 0:
        update_code_question(qid, data)
        msg = "编程题已更新"
    else:
        insert_code_question(data)
        msg = "编程题已添加"
    return HTMLResponse(
        f'<div class="toast toast-success">{msg}</div>'
        '<script>setTimeout(function(){closeModal();refreshLibraryCodeQuestions();},600);</script>')


@app.delete("/api/library/question/{qid}")
async def api_library_delete_question(qid: int):
    if not can_delete_question(qid):
        return HTMLResponse(
            '<tr><td colspan="8" class="empty-state">内置题目不可删除</td></tr>', status_code=403)
    delete_question(qid)
    return HTMLResponse("")


@app.delete("/api/library/code-question/{qid}")
async def api_library_delete_code_question(qid: int):
    delete_code_question(qid)
    return HTMLResponse("")


@app.post("/api/library/export-questions")
async def api_library_export_questions(ids: str = Form("")):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()] if ids else None
    data = export_questions_json(id_list)
    return JSONResponse({"data": json.loads(data)})


@app.post("/api/library/export-code-questions")
async def api_library_export_code_questions(ids: str = Form("")):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()] if ids else None
    data = export_code_questions_json(id_list)
    return JSONResponse({"data": json.loads(data)})


@app.post("/api/library/import-questions")
async def api_library_import_questions(file: UploadFile = File(...)):
    try:
        content = await file.read()
        count = import_questions_json(content.decode("utf-8"))
        return HTMLResponse(
            f'<div class="toast toast-success">成功导入 {count} 道题目。</div>'
            '<script>refreshLibraryQuestions();</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">导入失败：{str(e)}</div>')


@app.post("/api/library/import-code-questions")
async def api_library_import_code_questions(file: UploadFile = File(...)):
    try:
        content = await file.read()
        count = import_code_questions_json(content.decode("utf-8"))
        return HTMLResponse(
            f'<div class="toast toast-success">成功导入 {count} 道编程题。</div>'
            '<script>refreshLibraryCodeQuestions();</script>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">导入失败：{str(e)}</div>')


# ========== Module 5: Settings ==========

@app.post("/api/settings/apikey")
async def api_settings_apikey(api_key: str = Form("")):
    if not api_key.strip():
        return HTMLResponse('<div class="toast toast-error">API Key 不能为空。</div>')
    encoded = base64.b64encode(api_key.strip().encode("utf-8")).decode("utf-8")
    set_setting("api_key", encoded)
    return HTMLResponse('<div class="toast toast-success">API Key 已保存。</div>')


@app.post("/api/settings/preferences")
async def api_settings_preferences(daily_reminder: str = Form("off"),
                                   default_mode: str = Form("daily")):
    set_setting("daily_reminder", daily_reminder)
    set_setting("default_mode", default_mode)
    return HTMLResponse('<div class="toast toast-success">偏好设置已保存。</div>')


@app.post("/api/test-ai-connection")
async def api_test_ai_connection():
    if not _api_key_configured():
        return HTMLResponse('<div class="toast toast-error">请先配置 API Key。</div>')
    try:
        from openai import OpenAI
        client = OpenAI(api_key=_decode_api_key(), base_url="https://api.deepseek.com")
        client.chat.completions.create(
            model="deepseek-chat", messages=[{"role": "user", "content": "Hi"}], max_tokens=10)
        return HTMLResponse('<div class="toast toast-success">连接成功！模型可用。</div>')
    except ImportError:
        return HTMLResponse('<div class="toast toast-error">openai 库未安装。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">连接失败：{str(e)}</div>')


@app.get("/api/export-db")
async def api_export_db():
    if not os.path.exists(DB_PATH):
        return JSONResponse({"error": "数据库文件不存在"}, status_code=404)
    return FileResponse(DB_PATH, filename="reviewmate_backup.db",
                        media_type="application/octet-stream")


@app.post("/api/import-db")
async def api_import_db(db_file: UploadFile = File(...)):
    try:
        content = await db_file.read()
        if len(content) < 100 or content[:16] != b"SQLite format 3\x00":
            return HTMLResponse('<div class="toast toast-error">无效的 SQLite 数据库文件。</div>')
        backup_path = DB_PATH + ".backup"
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
        with open(DB_PATH, "wb") as f:
            f.write(content)
        return HTMLResponse(
            '<div class="toast toast-success">数据库已导入。旧数据已备份为 .backup 文件。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">导入失败：{str(e)}</div>')


@app.post("/api/reset-records")
async def api_reset_records():
    try:
        reset_records()
        return HTMLResponse('<div class="toast toast-success">所有答题记录和 SM-2 状态已重置。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">重置失败：{str(e)}</div>')


@app.post("/api/reset-all")
async def api_reset_all():
    try:
        reset_all_questions()
        return HTMLResponse('<div class="toast toast-success">题库已重置，种子数据已重新导入。</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="toast toast-error">重置失败：{str(e)}</div>')


# ========== Startup ==========

if __name__ == "__main__":
    port = 8520
    url = f"http://127.0.0.1:{port}"
    print(f"  ReviewMate starting at {url}")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
