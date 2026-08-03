# 配置

pico 的配置按下面这个优先级合并：

```
CLI 显式参数 > 环境变量 > 项目 .pico.toml > 全局 ~/.config/pico/config.toml > 代码默认
```

## Provider profile

provider 是 TOML 里的一段配置 profile，名字（如 `deepseek` `openai` `anthropic`）只用于人类辨识；真正决定走哪个协议的是 `protocol` 字段，目前支持 `openai` 和 `anthropic` 两种。

### .pico.toml 示例

放在仓库根目录。真实 key 放在本地 `.env`，不要提交：

```toml
provider = "deepseek"

[providers.deepseek]
protocol = "anthropic"
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"

[providers.openai]
protocol = "openai"
base_url = "https://api.openai.com/v1"
model = "gpt-5.4"

[providers.anthropic]
protocol = "anthropic"
base_url = "https://api.anthropic.com"
model = "claude-sonnet-4-6"
```

切 provider：

```bash
pico                       # 用 toml 里的默认 provider
pico --provider openai     # 临时切换
pico --provider anthropic --model claude-opus-4-6
```

## Feature flags

MapEngine repo map 默认关闭。需要在项目内试用时，可以在 `.pico.toml` 中开启：

```toml
[features]
map_engine = true
```

CLI 显式参数覆盖 TOML：

```bash
pico --map-engine
pico --no-map-engine
```

## 环境变量

不写 toml 也能跑——只设环境变量即可：

| 变量 | 用途 |
|------|------|
| `PICO_PROVIDER` | 默认 provider |
| `PICO_API_KEY` / `PICO_BASE_URL` / `PICO_MODEL` | 通用 override |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL` | Anthropic |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | DeepSeek |

兼容历史 `.env`：`PICO_OPENAI_*` / `PICO_ANTHROPIC_*` / `PICO_DEEPSEEK_*` 仍然能用。

### 跨 `--cwd` 使用本地 `.env`

CLI 会先建立 `--cwd` 指向的 `WorkspaceContext`，随后从 `--cwd` 开始解析 provider 配置；目标仓库的 `.env` 则在 provider 配置之后才加载。因此 `.env` 位于启动目录、而被分析仓库是另一个目录时，先把本地环境变量导入 shell：

```bash
cd pico
set -a; source .env; set +a
PYTHONPATH=. ../.venv/bin/python -m pico \
  --cwd /absolute/path/to/target-repo \
  --provider deepseek --map-engine \
  "Explain src/auth.py"
```

不要为了让 `--cwd` 读取 key 而把 `.env` 复制到目标仓库，也不要把它加入 Git。

## 全局配置

`~/.config/pico/config.toml` 适合放跨项目都用的 provider profile。项目 `.pico.toml` 覆盖它，CLI 参数再覆盖项目。

## CLI 参数

```bash
pico --provider deepseek --model deepseek-v4-pro
pico --api-key sk-... --base-url https://...
pico --max-steps 50 --max-new-tokens 4096
pico --model-input-budget-tokens 65536 --prompt-safety-margin-tokens 2048
pico --temperature 0.0
pico --approval ask          # ask | auto | never
pico --map-engine            # 启用 MapEngine repo map feature
pico --no-map-engine         # 禁用 MapEngine repo map feature
pico --sandbox best_effort   # off | best_effort | required
pico --no-auto-dream         # 关闭后台 memory 整合
pico --cwd /path/to/repo     # 切换工作目录
pico --resume latest         # 续接上一个 session
pico --config /path/to/custom.toml
```

跑 `pico --help` 看完整参数。

## ModelRequestBudget

`ModelRequestBudget` 是完整 selector 请求和最终主模型请求的输入门禁，不是 `max-new-tokens` 输出上限，也不是 MapEngine repo map 的渲染预算。

预算字段按以下顺序解析：

```text
CLI --model-input-budget-tokens / --prompt-safety-margin-tokens
> [model_request_budget]
> [providers.<selected-provider>]
> fallback
```

未配置时 fallback 为 `model_input_budget_tokens = 32768`、`prompt_safety_margin_tokens = 1024`；token 估算为 `ceil(chars / 4)`。只有当“估算请求 + margin”不超过 input budget 时才会发送请求。fallback 是代码默认值，不代表 provider/model 已验证的上下文窗口。

```toml
[providers.deepseek]
protocol = "anthropic"
base_url = "https://api.deepseek.com/anthropic"
model = "deepseek-v4-pro"
model_input_budget_tokens = 65536
prompt_safety_margin_tokens = 2048

[model_request_budget]
# 对所有 selected provider 覆盖同名字段
model_input_budget_tokens = 98304
prompt_safety_margin_tokens = 2048
```

只在确认所选模型实际 input limit 后再提高预算。MapEngine 的 focused/broad map 固定渲染预算分别为 4,096 / 8,192 tokens，不会随本节配置变化。

## 默认值速查

| 项 | 默认 |
|----|------|
| `max-steps` | 50 |
| `max-new-tokens` | Anthropic 32000 / OpenAI 8192 / DeepSeek 8192 / fallback 4096 |
| `temperature` | 0.2 |
| `approval` | `ask` |
| `sandbox` | `off` |
| `dream-interval` | 24 小时 |
| `dream-min-sessions` | 5 |
| MapEngine focused map | 4096 tokens（固定渲染预算） |
| MapEngine broad map | 8192 tokens（固定渲染预算） |
| ModelRequestBudget fallback input | 32768 tokens |
| ModelRequestBudget fallback margin | 1024 tokens |

## 调试

- `/session` 查看 session 文件路径和当前 runtime 标识
- `/context` 查看上下文用量切片
- `/usage` 查看 token / call 数
- 所有事件流写到 `.pico/sessions/<id>.events.jsonl`，可以用 `tail -f` 观察
- 每次运行的 trace 在 `.pico/runs/<run_id>/trace.jsonl`
- 启用 MapEngine 后，首次实际注入的 repo map 在 `.pico/runs/<run_id>/artifacts/repo-map-001.txt`，结构化证据在同目录的 `map-evidence-001.json`。
- Branch A 命中明确文件、symbol 或 path ident 后直接生成 focused map；仅 path ident 不形成文件 focus，也不调用 selector。三类有效命中均为空时进入 Branch B，selector 只能建议 visible paths；未确认、无有效建议或 selector 请求超预算时继续使用 broad map，并在 trace/report 中记录原因。
