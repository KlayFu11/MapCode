# MapCode v1

MapCode 是基于 Pico runtime 的本地 Coding Agent Harness。v1 在 Pico 原有的模型调用、工具、审批、任务状态和运行审计链路上增加 `MapEngine`：它先为仓库生成可追溯的导航上下文（repo map），再由 Pico 主模型决定读取哪些完整源码。

Repo map 只回答“优先到哪里看”，不是源码替代品，也不授予工具额外权限。实际读取、编辑和 shell 操作仍由 Pico 的工具策略与审批链路控制。

## v1 能力边界

- 以 Git 仓库中的 Python 文件为输入，使用 definitions、references 和文件图生成稳定的 repo map。
- **Branch A**：请求中有明确文件、已索引 symbol 或 path ident 命中时，直接生成 focused map。`pico/`、`src/` 这类 path ident 会形成 path personalization，但不会变成文件 focus，也不会调用 selector。
- **Branch B**：文件、symbol、path ident 三类有效命中都为空时，先生成 broad map，再由 selector 提出可见候选文件并等待“接受全部建议”或退回 broad map。
- focused map 固定预算为 **4,096 tokens**；broad map 固定预算为 **8,192 tokens**。它们是 repo map 的渲染预算，不是 provider 的模型上下文窗口。
- 排名、focus/path personalization、Aider-style multiplier/reason code、selector catalog、预算决策和降级原因都会写入运行证据。

正常的 broad fallback 不是 MapEngine 故障；例如 selector 请求超预算、没有有效建议或用户不接受建议时，运行时会复用原请求与 broad map 继续执行。只有索引、渲染、artifact 或最终请求门禁失败，才会受控地移除 repo map 并记录失败原因。

## 快速开始

从 `pico/` 目录启动，使用项目根目录的本地虚拟环境：

```bash
cd pico
cp .env.example .env
# 在 .env 中填写 PICO_DEEPSEEK_API_KEY，或使用 DEEPSEEK_API_KEY。
set -a; source .env; set +a
PYTHONPATH=. ../.venv/bin/python -m pico \
  --cwd /absolute/path/to/your/repository \
  --provider deepseek \
  --map-engine \
  "Explain src/auth.py"
```

`--cwd` 指向被分析的仓库。CLI 会先建立 `WorkspaceContext`，随后从 `--cwd` 开始解析 provider 配置；但目标仓库的 `.env` 要在 provider 配置之后才加载。因此当本地 `.env` 位于启动目录、而 `--cwd` 指向另一个仓库时，必须先在 shell 中 `source .env`；不要把密钥复制到被分析仓库，也不要提交 `.env`。

需要交互式演示时，保留同样的环境变量并使用：

```bash
PYTHONPATH=. ../.venv/bin/python -m pico --cwd /absolute/path/to/your/repository --map-engine --repl
PYTHONPATH=. ../.venv/bin/python -m pico --cwd /absolute/path/to/your/repository --map-engine --tui
```

默认审批策略是 `ask`。`--approval never` 仅适合一次性、只读且可丢弃的验收演示；它不应替代正常的人工审批。

## 请求预算

`ModelRequestBudget` 在完整 selector 请求和最终主模型请求发出前执行门禁。估算方法为 `ceil(chars / 4)`，当“估算 token + safety margin”超过 input budget 时，请求不会发送。

预算字段的优先级严格为：CLI 参数 > `.pico.toml` 的 `[model_request_budget]` > 已选 provider profile > fallback。fallback 是 32,768 input tokens 与 1,024 safety-margin tokens；它是保守默认值，不能被当作某个模型的已验证窗口。

```toml
# .pico.toml
[providers.deepseek]
protocol = "anthropic"
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"
model_input_budget_tokens = 65536
prompt_safety_margin_tokens = 2048

[model_request_budget]
# 覆盖 provider profile 的同名字段
model_input_budget_tokens = 98304
prompt_safety_margin_tokens = 2048
```

也可以只在当前调用覆盖：

```bash
pico --model-input-budget-tokens 98304 --prompt-safety-margin-tokens 2048
```

预算必须由你确认与所选 provider/model 的实际输入限制一致；MapCode 不从模型名称推断窗口大小。

## 运行证据与评测

每次启用 MapEngine 的运行在工作区写入 `.pico/runs/<run-id>/`。重点文件包括：

- `trace.jsonl`：retrieval、selector、预算和模型调用事件；
- `task_state.json` 与 `report.json`：运行级摘要；
- `artifacts/repo-map-001.txt`：首次实际注入的 repo map；
- `artifacts/map-evidence-001.json`：结构化检索、排名、预算和 artifact 一致性证据。

运行产物和 `.env` 都是本地数据，不应提交。固定 retrieval fixture、ground truth 和离线评测由 `pico/tests/test_map_engine_retrieval_eval.py` 覆盖；完整的 v1 回归从 `pico/` 目录运行：

```bash
PYTHONPATH=. ../.venv/bin/python -m pytest tests -q
../.venv/bin/python -m ruff check pico tests
```

## 限制与后续方向

- v1 的静态索引范围是 Python；非 Python 源码不会进入 MapEngine 的 definitions/reference 图。
- repo map 会受到固定渲染预算和最终请求预算的双重约束，因此完整 map section 可能被整体省略；证据会记录 omission reason。
- Branch B 的 selector 只能建议已展示的 visible paths，且 v1 只支持“接受全部建议”或 broad fallback，不支持部分编辑候选列表。
- provider、网络、工具循环的实际结果会影响一次真实运行；离线 retrieval eval 用固定 fixture 提供可重复的结构性验证，但不代表任意模型输出都确定。
