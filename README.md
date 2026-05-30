# ReviewMate

面向大一计算机基础课程的间隔重复学习系统，支持选择题、简答题和编程题。基于 SM-2 算法智能调度复习，集成 DeepSeek AI 用于题目生成、弱点分析和学习报告。

## 功能特性

- **SM-2 间隔重复** — 根据答题自评动态调整复习间隔，高效巩固记忆
- **三种题型** — 选择题、简答题（含关键词匹配）、编程题（PTA 风格沙箱判题）
- **AI 辅助** — 题目生成、弱点分析、学习报告、对话辅导（DeepSeek）
- **HTMX 局部刷新** — 页面无感更新，无需引入重型前端框架
- **数据可视化** — ECharts 趋势图、雷达图、错题排行、答题热力图
- **题库管理** — 支持 CRUD、JSON 批量导入导出
- **数据便携** — SQLite 数据库，支持一键导出/导入

## 快速开始

### 环境要求

- Python 3.10+
- （可选）GCC/Clang — C 语言编程题判题
- （可选）DeepSeek API Key — AI 功能

### 安装运行

```bash
pip install -r requirements.txt
python main.py
```

浏览器自动打开 http://127.0.0.1:8520

也可以双击 `start.bat`（Windows）或运行 `bash start.sh`（Mac/Linux）。

## 技术栈

| 层 | 技术 |
|----|------|
| Web 框架 | FastAPI + Uvicorn |
| 模板引擎 | Jinja2 + HTMX |
| 数据库 | SQLite（WAL 模式） |
| AI | DeepSeek API（openai SDK） |
| 图表 | ECharts 5.5 |
| 代码编辑 | CodeMirror 5.65 |
| 代码高亮 | highlight.js 11.9 |

## 目录结构

```
reviewmate/
├── main.py              # FastAPI 应用，所有路由
├── database.py          # SQLite 操作，SM-2 算法实现
├── ai_client.py         # DeepSeek API 封装
├── judge_sandbox.py     # 代码判题沙箱（Python + C）
├── seed_data.json       # 选择题/简答题种子数据（176 道）
├── seed_code_data.json  # 编程题种子数据（39 道，PTA 风格）
├── requirements.txt     # Python 依赖
├── start.bat / start.sh # 启动脚本
├── data/                # SQLite 数据库文件
├── templates/           # Jinja2 模板（含 HTMX 局部刷新组件）
└── static/              # CSS / JS 静态资源
```

## 题目体系

| 分类 | 知识点 |
|------|--------|
| C 语言 | 变量与数据类型、输入输出、运算符、条件判断、循环、数组、函数、指针、字符串、结构体、内存管理 |
| Python | 变量与类型、输入输出、运算符、条件判断、循环、列表、字典、字符串、函数、推导式、文件读写、异常处理、切片 |
| SQL | SELECT/WHERE/ORDER BY/LIKE、INSERT/UPDATE/DELETE、聚合函数、GROUP BY/HAVING、JOIN、子查询 |
| 数据结构 | 数组、链表、栈、队列、排序、查找、树基础、哈希表 |

## AI 功能

在设置页配置 DeepSeek API Key 后可使用：

- 自动生成选择题/简答题/编程题
- 基于答题记录分析薄弱知识点
- 生成 Markdown 格式学习周报
- AI 对话辅导

## SM-2 算法

根据答题自评（已掌握 / 模糊 / 未掌握）动态计算下次复习时间：

- **已掌握** → 间隔延长
- **模糊** → 间隔缩短
- **未掌握** → 重置间隔，近期再练

出题优先级：到期复习 > 未学过的新题 > 随机

## 重置数据

删除 `data/reviewmate.db` 后重启应用，自动从种子数据 JSON 文件重新导入。

## 判题依赖

| 题目类型 | 依赖 |
|----------|------|
| Python 编程题 | 系统需安装 Python |
| C 语言编程题 | 系统需安装 GCC 或 Clang（Windows 推荐 MinGW-w64） |

## License

MIT
