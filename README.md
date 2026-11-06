# Mini Coding Agent（基于 DeepSeek API）

《深度学习》课程期末考核作品：一个能接收自然语言编程任务、自主读写代码、执行程序、根据报错自动修复的
命令行 Coding Agent。

- 模型：DeepSeek 官方 API（OpenAI 兼容协议）
- 形态：命令行，无 GUI
- 运行：普通 CPU 即可

## 快速开始

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu

copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

python scripts\smoke.py          # 环境自检，全绿再往下
```

## 运行一次任务

```powershell
# 任务写在文件里（推荐，考场上原样保存教师给的题目）
python -m agent.main --task-file task.txt

# 或者直接给一段文字
python -m agent.main --task "实现一个支持 get/put 的 LRU Cache"
```

程序会把每次运行的产物写到 `runs/<时间戳>-<任务名>/`：

| 文件 | 内容 |
|---|---|
| `task.txt` | 本次任务的原文 |
| `trace.jsonl` | 结构化事件日志（每步一次工具调用） |
| `agent.log` | 人类可读日志 |
| `workspace/` | 被测代码的独立工作目录 |

## 目录结构

```
agent/
  main.py      CLI 入口（参数解析、建运行目录）
  config.py    配置（全部来自 .env / 环境变量，无交互输入）
  loop.py      主循环：模型 -> 工具 -> 观测 -> 再模型
  llm.py       DeepSeek 客户端封装（重试、用量统计）
  context.py   上下文管理（保留窗口、孤儿消息清理）
  prompts.py   系统提示词与任务模板
  logger.py    JSONL 日志 + API Key 脱敏
  tools/       工具集（文件读写、执行、pytest、完成信号）
scripts/
  smoke.py     环境自检
  freeze.ps1   冻结版本（git tag + 快照 + sha256）
  grade.py     跑模拟题并汇总
eval/          三道模拟题（任务一/二/三）
runs/          运行产物（不进 git）
```

## 实现进度

| 模块 | 状态 |
|---|---|
| 配置 / 日志 / 脱敏 | 已实现 |
| 文件工具（读/写/替换/列目录） | 已实现 |
| 执行工具（run_python / run_pytest，含超时与输出截断） | 已实现 |
| DeepSeek 客户端（重试 + 用量统计） | 已实现 |
| 主循环（工具调用 + 终止条件 + 预算） | 最小可用 |
| 上下文摘要压缩 | 待实现（骨架已留位） |
| 模拟题集 `eval/` | 待填充 |
| 冻结脚本 | 骨架已留位 |

## 安全与纪律

- `.env` 已在 `.gitignore` 中；日志写盘前统一脱敏 `sk-` 开头的密钥。
- 所有文件工具被限制在本次运行的工作目录内，无法越界读写。
- 程序全程无交互，不需要人工逐步确认（符合课堂"人工操作边界"要求）。
