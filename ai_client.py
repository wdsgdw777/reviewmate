"""
ReviewMate AI Client - DeepSeek API wrapper.
All AI calls go through this module.
"""

import json
import re
import base64
from openai import AsyncOpenAI
from database import get_setting


def _get_client() -> AsyncOpenAI | None:
    api_key = get_setting("api_key")
    if not api_key:
        return None
    try:
        api_key = base64.b64decode(api_key).decode("utf-8")
    except Exception:
        pass  # already plaintext or malformed
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


async def ask_ai(messages: list[dict], model: str = "deepseek-chat") -> str:
    """Send messages to DeepSeek and return the response text."""
    client = _get_client()
    if client is None:
        return "[错误] 未配置 API Key，请在设置页面配置 DeepSeek API Key。"
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[AI 调用失败] {str(e)}"


async def generate_questions(
    category: str = "",
    tags: list[str] | None = None,
    qtype: str = "choice",
    difficulty: str = "medium",
    count: int = 5,
) -> list[dict]:
    """Generate questions via AI. Returns a list of question dicts ready for DB insert."""
    tag_str = ", ".join(tags) if tags else "无"

    # 大一基础水平的知识范围
    scope_map = {
        "C": "C 语言基础语法（变量、数据类型、printf/scanf、if/else、for/while 循环、一维数组、函数定义与调用、指针基本概念）",
        "Python": "Python 基础语法（变量、print/input、列表、字典、字符串操作、if/elif/else、for/while 循环、函数定义 def、基本文件读写）",
        "SQL": "SQL 基础（SELECT、WHERE、ORDER BY、LIKE、INSERT/UPDATE/DELETE、COUNT/SUM/AVG 聚合函数、简单 JOIN）",
        "数据结构": "基础数据结构概念（数组、链表基本概念、栈和队列的 LIFO/FIFO、二分查找思路、简单排序冒泡/选择）",
    }
    scope = scope_map.get(category, "大学一年级计算机基础水平的知识点")

    prompt = f"""请生成 {count} 道{'选择题' if qtype == 'choice' else '简答题'}。

分类: {category or '通用'}
难度: {difficulty}
知识点范围: {scope}
标签: {tag_str}

【重要约束】
- 用户是大一学生，题目必须是入门基础水平
- 不要出超纲内容（如 C 语言不要出多级指针、位运算、联合体；Python 不要出装饰器、生成器、元类、异步编程）
- easy 难度 = 概念记忆/语法识别，medium 难度 = 简单理解和应用
- 解析要详细、通俗易懂，帮助初学者理解

请严格按照以下 JSON 数组格式返回，不要包含其他内容：
[
  {{
    "category": "分类",
    "tags": ["标签1", "标签2"],
    "type": "{qtype}",
    "difficulty": "{difficulty}",
    "content": "题目内容",
    "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"],
    "answer": "B",
    "answer_match_mode": "exact",
    "keywords": [],
    "explanation": "详细解析，用通俗语言解释为什么选这个答案",
    "source": "ai"
  }}
]

注意：
- 如果是简答题(type=open)，options 设为 []，answer_match_mode 选 "normalized" 或 "keywords"
- keywords 模式请提供 3-5 个关键词"""

    messages = [
        {"role": "system", "content": "你是一位大学计算机基础课教师，给大一学生出题。题目范围严格限定在入门基础水平，不出超纲题。解析要通俗易懂。请始终返回合法的 JSON。"},
        {"role": "user", "content": prompt},
    ]

    resp = await ask_ai(messages)
    try:
        json_match = re.search(r"\[[\s\S]*\]", resp)
        if json_match:
            return json.loads(json_match.group())
        return []
    except json.JSONDecodeError:
        return []


async def generate_code_questions(
    category: str = "Python",
    tags: list[str] | None = None,
    difficulty: str = "medium",
    count: int = 2,
) -> list[dict]:
    """Generate code questions via AI."""
    tag_str = ", ".join(tags) if tags else "无"

    scope_map = {
        "C": "C 语言基础编程（变量、输入输出、if/else 判断、for/while 循环、一维数组操作、简单函数）",
        "Python": "Python 基础编程（变量与输入输出、字符串/列表操作、if/elif/else 判断、for/while 循环、函数定义与调用）",
    }
    scope = scope_map.get(category, "大学一年级编程基础")

    prompt = f"""请生成 {count} 道{category}编程题。

难度: {difficulty}
知识点范围: {scope}（严格限定在大一基础水平）
标签: {tag_str}

【重要约束】
- 用户是大一学生，编程题必须是入门基础水平
- 不涉及复杂算法、数据结构或高级语言特性
- easy = 单一知识点（如只考 if/else），medium = 组合 1-2 个知识点（如循环+数组）
- 每个题提供 3-4 个测试用例

请严格按照以下 JSON 数组格式返回，不要包含其他内容：
[
  {{
    "title": "题目标题",
    "category": "{category}",
    "tags": ["标签"],
    "difficulty": "{difficulty}",
    "description": "题目描述（说明输入输出格式，给出示例）",
    "template_code": "代码模板（提供函数签名和输入读取框架）",
    "test_cases": [
      {{"input": "输入", "expected_output": "期望输出"}},
      {{"input": "输入", "expected_output": "期望输出"}},
      {{"input": "输入", "expected_output": "期望输出"}}
    ],
    "source": "ai"
  }}
]"""

    messages = [
        {"role": "system", "content": "你是一位大学编程基础课教师，给大一学生出编程练习。题目严格限定在入门水平，不超纲。请始终返回合法的 JSON。"},
        {"role": "user", "content": prompt},
    ]

    resp = await ask_ai(messages)
    try:
        json_match = re.search(r"\[[\s\S]*\]", resp)
        if json_match:
            return json.loads(json_match.group())
        return []
    except json.JSONDecodeError:
        return []


async def analyze_weakness(records_summary: str) -> dict:
    """Analyze weaknesses from recent answer records. Returns {"weak_points": [...], "suggestions": "..."}"""
    prompt = f"""以下是一名大一学生近期的答题记录摘要：
{records_summary}

该学生正在学习：C 语言基础、Python 基础、SQL 入门、数据结构入门。

请分析该学生的薄弱点，返回 JSON 格式：
{{
  "weak_points": ["具体薄弱知识点1", "具体薄弱知识点2"],
  "suggestions": "针对性改进建议（Markdown 格式，包括：1. 需要重点复习的知识点 2. 建议的练习方向 3. 鼓励性的话）。语气温暖鼓励，像学长/学姐。"
}}

只返回 JSON，不要其他内容。"""

    messages = [
        {"role": "system", "content": "你是一位耐心的大学助教，帮助大一学生分析计算机基础学习情况。分析聚焦基础概念理解，给出可操作的建议。请始终返回合法 JSON。"},
        {"role": "user", "content": prompt},
    ]

    resp = await ask_ai(messages)
    try:
        json_match = re.search(r"\{[\s\S]*\}", resp)
        if json_match:
            return json.loads(json_match.group())
        return {"weak_points": [], "suggestions": "AI 分析暂时不可用，请稍后再试。"}
    except json.JSONDecodeError:
        return {"weak_points": [], "suggestions": resp if resp else "分析失败"}


async def generate_report(stats_summary: str) -> str:
    """Generate a weekly learning report in Markdown."""
    prompt = f"""以下是一名大一学生本周的计算机基础学习统计数据：
{stats_summary}

该学生的课程范围：C 语言基础、Python 基础、SQL 入门、数据结构入门。

请生成一份本周学习报告，使用 Markdown 格式，包含：
1. 总体概况（正确率、做题数量、连续打卡天数等）
2. 各分类表现分析（C/Python/SQL/数据结构分别评价）
3. 进步亮点与需要加强的地方
4. 下周具体学习建议（给出可操作的小目标，如"每天做 3 道 Python 循环题"）
5. 一段温暖的鼓励语

报告语言：通俗、鼓励性强，像学长/学姐写给学弟学妹的。不要用太专业的术语。"""

    messages = [
        {"role": "system", "content": "你是一位贴心的大学助教，给大一新生写每周学习反馈报告。报告要温暖、具体、有帮助。请用中文，Markdown 格式。"},
        {"role": "user", "content": prompt},
    ]

    return await ask_ai(messages)


async def chat_with_context(
    conversation_history: list[dict],
    user_context: str,
    system_prompt_override: str | None = None,
) -> str:
    """Chat with AI, using conversation history and user context."""
    system_prompt = system_prompt_override or f"""你是 ReviewMate 的 AI 学习教练。你的用户是一名大一学生，正在学习计算机基础课程。

用户目前掌握的课程范围：
- C 语言：基础语法、数据类型、输入输出、条件判断、循环、一维数组、函数、指针入门
- Python：基础语法、变量与数据类型、列表/字典/字符串、条件与循环、函数、文件读写入门
- SQL：SELECT 查询、WHERE 过滤、ORDER BY 排序、INSERT/UPDATE/DELETE、聚合函数（COUNT/SUM/AVG）
- 数据结构：数组、链表概念、栈与队列（LIFO/FIFO）、基础排序（冒泡/选择）、二分查找概念

你的职责：
1. 用通俗易懂的语言解释概念，多用类比和生活例子
2. 出题时严格控制在上述范围内的基础水平，不要超纲
3. 鼓励学生，帮他们建立信心
4. 分析薄弱点时聚焦基础知识的掌握情况

你可以执行以下操作（通过在回复中包含 JSON action）：
- 出题：{{"action": "generate_questions", "category": "C|Python|SQL|数据结构", "type": "choice|open", "count": 5}}
- 出编程题：{{"action": "generate_code_questions", "category": "C|Python", "difficulty": "easy|medium", "count": 2}}
- 分析薄弱点：{{"action": "analyze_weakness"}}
- 生成报告：{{"action": "generate_report"}}

用户学习概况：
{user_context}

请用中文回复，保持友好、鼓励的语气，像个耐心的学长/学姐。"""

    messages = [{"role": "system", "content": system_prompt}]
    for h in conversation_history:
        messages.append({"role": h["role"], "content": h["content"]})

    return await ask_ai(messages)
