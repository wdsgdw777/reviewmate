# ReviewMate — 间隔重复学习系统

## 项目概述

面向大一计算机基础课程的间隔重复学习工具，支持选择题、简答题和编程题的练习。基于 SM-2 算法智能调度复习，集成 DeepSeek AI 用于题目生成、弱点分析、学习报告和 AI 对话辅导。

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI 0.115 + Uvicorn 0.34 |
| 模板 | Jinja2 3.1 + HTMX 2.0 (局部刷新, 不引入 React/Vue) |
| 数据库 | SQLite (WAL 模式, foreign_keys=ON) |
| AI | DeepSeek API via openai SDK (题目生成、弱点分析、学习报告、AI 对话) |
| 前端库 | ECharts 5.5 (图表), CodeMirror 5.65 (代码编辑), highlight.js 11.9 (代码高亮) |
| 判题 | subprocess 沙箱 (Python: sys.executable, C: gcc/clang, 临时目录 + 超时控制) |

## 目录结构

```
reviewmate/
├── main.py                # FastAPI 应用, 所有路由
├── database.py            # SQLite 操作, SM-2 算法
├── ai_client.py           # DeepSeek API 封装 (出题/分析/报告/对话)
├── judge_sandbox.py       # 代码判题沙箱 (Python + C)
├── seed_data.json         # 选择题/简答题种子数据 (176 道)
├── seed_code_data.json    # 编程题种子数据 (39 道, PTA 风格)
├── requirements.txt       # Python 依赖
├── start.sh / start.bat   # 启动脚本 (端口 8520)
├── data/
│   └── reviewmate.db     # SQLite 数据库
├── templates/
│   ├── base.html          # 全局布局 (侧边栏 + 主内容)
│   ├── dashboard.html     # 仪表盘
│   ├── practice.html      # 每日练习 (含 HTMX 分类过滤)
│   ├── practice_content.html  # 练习页 HTMX 内容区
│   ├── free_practice.html # 自由练习 (PTA 风格编程题)
│   ├── library.html       # 题库管理
│   ├── stats.html         # 统计中心
│   ├── settings.html      # 设置
│   └── partials/          # HTMX 局部刷新组件
│       ├── question_card.html
│       ├── answer_result.html
│       ├── question_form.html
│       ├── code_question_form.html
│       ├── question_desc.html
│       ├── judge_result.html
│       ├── library_table.html
│       └── next_question.html
└── static/
    ├── css/style.css      # 全局样式 (~32KB)
    └── js/                # 预留 JS 目录 (当前为空)
```

## 数据库表结构

### questions — 选择题/简答题
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增主键 |
| category | TEXT | 分类: C/Python/SQL/数据结构 |
| tags | TEXT (JSON) | 知识点标签数组 |
| type | TEXT | choice / open |
| difficulty | TEXT | easy / medium |
| content | TEXT | 题目内容 |
| options | TEXT (JSON) | 选项数组 (choice 类型) |
| answer | TEXT | 正确答案 |
| answer_match_mode | TEXT | exact / normalized / keywords |
| keywords | TEXT (JSON) | 关键词数组 (keywords 模式) |
| explanation | TEXT | 解析 |
| source | TEXT | manual / ai / seed |

### code_questions — 编程题 (PTA 风格)
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增主键 |
| title | TEXT | 题目标题 |
| category | TEXT | C / Python |
| tags | TEXT (JSON) | 知识点标签数组 |
| difficulty | TEXT | easy / medium / hard |
| description | TEXT | 题目描述 |
| input_format | TEXT | 输入格式说明 |
| output_format | TEXT | 输出格式说明 |
| sample_input | TEXT | 输入样例 |
| sample_output | TEXT | 输出样例 |
| template_code | TEXT | 代码模板 |
| test_cases | TEXT (JSON) | `[{"input":"", "expected_output":""}]` |
| time_limit_ms | INTEGER | 时间限制 (默认 2000) |
| memory_limit_mb | INTEGER | 内存限制 (默认 128) |
| stack_limit_mb | INTEGER | 栈限制 (默认 64) |
| solution_code | TEXT | 参考解答 |
| source | TEXT | manual / ai / seed |

### answer_records — 答题记录
| 列 | 类型 |
|----|------|
| id | INTEGER PK |
| question_id | INTEGER |
| question_type | TEXT (choice/open/code) |
| user_answer | TEXT |
| is_correct | BOOLEAN |
| match_details | TEXT (JSON) |
| self_assessment | TEXT (mastered/fuzzy/failed) |
| mode | TEXT |
| time_spent | INTEGER |
| timestamp | TIMESTAMP |

### sm2_state — SM-2 间隔重复状态
(PK: question_id + question_type)
easiness=2.5, interval=0, repetitions=0, next_review=date

### chat_history, ai_reports, user_settings, daily_task
通用表，键值对存储设置，ai_reports 存 AI 生成的报告。

## SM-2 算法

自评 quality: mastered=5, fuzzy=3, failed=1

```
if q >= 3:
    if rep == 0: interval = 1
    elif rep == 1: interval = 6
    else: interval = round(interval * easiness)
    rep += 1
else:
    rep = 0; interval = 1

easiness = easiness + 0.1 - (5-q) * (0.08 + (5-q) * 0.02)
easiness = max(1.3, easiness)
```

出题优先级: 到期复习 > 未学习新题 > 随机

## API 路由一览

### 页面路由
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | / | 仪表盘 — 统计数据、正确率、连续打卡、薄弱标签 |
| GET | /practice | 每日练习 — 支持 mode=daily/review/category, HTMX 局部刷新 |
| GET | /practice/free | 自由练习 — 编程题，按 category 随机选题 |
| GET | /library | 题库管理 — 选择题/编程题列表、筛选、CRUD |
| GET | /stats | 统计中心 — 趋势图、雷达图、错题排行、热力图、AI 报告 |
| GET | /settings | 设置 — API Key、每日提醒、默认练习模式 |

### 答题 & 判题
| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/submit-answer | 提交答案(选择题/简答题), 返回判分结果 + 自评入口 |
| GET | /api/next-question | 获取下一题 (SM-2 调度), 支持 mode/filter 参数 |
| GET | /api/code-question/{id} | 获取指定编程题详情 |
| GET | /api/random-code-question | 按分类随机获取编程题 |
| POST | /api/judge | 编程题判题 — 沙箱编译运行, 逐测试用例比对 |
| GET | /api/related-questions/{qid} | 巩固练习 — 同知识点相关题目推荐 |

### 统计数据 (JSON API)
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/stats/trend | 每日正确率趋势 (默认 30 天) |
| GET | /api/stats/radar | 各分类正确率 (雷达图) |
| GET | /api/stats/errors | 薄弱标签排行 (默认前 5) |
| GET | /api/stats/heatmap | 年度答题热力图 (默认 365 天) |

### AI 功能
| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/generate-report | 基于 30 天统计数据生成 AI 学习报告 |
| GET | /api/report/{id} | 查看历史 AI 报告详情 |

### 题库 CRUD
| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/library/questions | 题目列表 (支持 category/search/分页) |
| GET | /api/library/code-questions | 编程题列表 (支持 category/search/分页) |
| GET | /api/library/question-form/{id} | 题目编辑表单 (id=0 为新增) |
| GET | /api/library/code-question-form/{id} | 编程题编辑表单 (id=0 为新增) |
| POST | /api/library/question | 新增/更新题目 |
| POST | /api/library/code-question | 新增/更新编程题 |
| DELETE | /api/library/question/{id} | 删除题目 (内置题禁止删除) |
| DELETE | /api/library/code-question/{id} | 删除编程题 (内置题禁止删除) |
| POST | /api/library/export-questions | 导出选中题目为 JSON |
| POST | /api/library/export-code-questions | 导出选中编程题为 JSON |
| POST | /api/library/import-questions | 从 JSON 文件导入题目 |
| POST | /api/library/import-code-questions | 从 JSON 文件导入编程题 |

### 设置 & 数据管理
| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/settings/apikey | 保存 DeepSeek API Key (base64 编码存储) |
| POST | /api/settings/preferences | 保存偏好 (每日提醒开关、默认练习模式) |
| POST | /api/test-ai-connection | 测试 AI 连接 (调用 DeepSeek chat API) |
| GET | /api/export-db | 导出 SQLite 数据库文件 |
| POST | /api/import-db | 导入 SQLite 数据库 (自动备份旧文件) |
| POST | /api/reset-records | 清除所有答题记录和 SM-2 状态 |
| POST | /api/reset-all | 重置题库, 重新导入种子数据 |

## 题目分类与知识点体系

### C 语言
变量与数据类型, 输入输出(printf/scanf), 运算符, 条件判断(if/else/switch), 循环(for/while/do-while), 数组(一维/二维), 函数(定义/调用/递归), 指针基础, 字符串, 结构体入门, 内存管理入门

### Python
变量与数据类型, 输入输出(print/input), 运算符, 条件判断(if/elif/else), 循环(for/while), 列表, 字典, 字符串操作, 函数(定义/参数/返回值), 列表推导式, 文件读写, 异常处理入门, 切片操作

### SQL
SELECT 查询, WHERE 过滤, ORDER BY 排序, LIKE 模糊匹配, INSERT/UPDATE/DELETE, 聚合函数(COUNT/SUM/AVG/MAX/MIN), GROUP BY + HAVING, JOIN(INNER/LEFT), 子查询, DISTINCT, LIMIT/OFFSET

### 数据结构
数组, 链表(单向/双向), 栈(LIFO), 队列(FIFO), 排序(冒泡/选择/插入/快排概念), 查找(顺序/二分), 树基础(二叉树/遍历概念), 哈希表概念

## AI 模块 (ai_client.py)

通过 DeepSeek API 提供 6 个 AI 能力：

| 函数 | 功能 | 说明 |
|------|------|------|
| `generate_questions()` | 生成选择题/简答题 | 按分类/标签/难度生成, 返回 JSON 数组, 可直接入库 |
| `generate_code_questions()` | 生成编程题 | 按分类/难度生成, 含测试用例和代码模板 |
| `analyze_weakness()` | 分析薄弱点 | 基于答题记录找出薄弱知识点, 给出改进建议 |
| `generate_report()` | 生成学习报告 | 基于统计数据生成 Markdown 格式周报 |
| `chat_with_context()` | AI 对话辅导 | 基于学习概况的上下文对话, 支持出题/分析/报告 action |
| `ask_ai()` | 底层 API 调用 | 通用 DeepSeek chat 请求 |

注意: `generate_questions`、`generate_code_questions`、`analyze_weakness`、`chat_with_context` 当前仅在 ai_client.py 中定义, 前端通过 POST /api/generate-report 使用的是 `generate_report`。题目生成目前主要通过 `/api/settings` 页面的 AI 对话入口间接调用。

## 开发约定

- 题库扩充: 编辑 seed_data.json / seed_code_data.json 或通过设置页 AI 对话生成
- 编程题按 PTA 平台格式: 含输入格式、输出格式、输入样例、输出样例、代码长度限制、时间限制、内存限制、栈限制
- 自由练习室分类: C (17 道) / Python (22 道), 侧重基础语法、数据结构和算法入门
- 删除 data/reviewmate.db 即可重置到种子数据: 重启应用自动从 JSON 重新导入 (含 39 道 PTA 编程题)
- 旧数据库自动迁移: init_db() 会通过 ALTER TABLE 补充缺失的 PTA 字段
- AI 功能需要 DeepSeek API Key, 在设置页配置 (base64 编码存储)
- 判题依赖: Python 题需要系统有 Python, C 题需要 gcc 或 clang (Windows 需 MinGW-w64/TDM-GCC)
- 前端用 HTMX 做局部刷新, 不引入 React/Vue
- static/js/ 目录预留为空, 需要时可在其中添加 JS 文件
- **每次修改代码后必须同步更新此 CLAUDE.md**，保持文档与代码一致

## 启动方式

```bash
pip install -r requirements.txt
python main.py
# 或双击 start.bat
# 浏览器自动打开 http://127.0.0.1:8520
```
