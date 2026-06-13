# MapCode v1 技术规格说明

- 版本：v1.3
- 文档职责：技术实现指导文档
- 范围：单会话、单用户轮次、基础 MapEngine 检索与 Pico 执行闭环
- 当前实现底座：Pico runtime
- 长期产品目标：基于 Pico runtime 完成初步 MapEngine 功能接入后将该项目包装为 MapCode
- 接入 Pico 逻辑：控制流归 Engine，确定性检索归 MapEngine，数据适配归 Coordinator，prompt 注入归 ContextManager
- 优先级：端到端正确性 > 模块边界 > 可解释证据 > 检索优化

---

## 一、文档定位

本文档是 MapCode v1 的技术实现指导文档，负责定义：

- 目录结构与代码文件职责。
- 模块接口与数据模型。
- Engine、runtime、Coordinator、MapEngine 的边界。
- Branch A / Branch B 的实现方式。
- ContextManager 注入、预算、trace、artifact、report 和终端输出。
- 错误处理、测试策略、实施阶段和验收标准。

模块流程、数据走向、事件顺序和用户可见行为查阅 `FuncFlow_v1_3.md`。

---

## 二、v1 目标与边界

### 2.1 核心目标

MapCode v1 要验证以下最小闭环：

```text
启动 Pico
  -> 初始化 MapEngine 对象，但不扫描仓库、不生成 repo map
  -> 用户提交一个请求
  -> 首次 prompt 前执行一次 MapContext preparation
  -> 根据 prompt 命中情况进入 Branch A 或 Branch B
  -> 生成 repo map 导航上下文和结构化证据
  -> 在对应 LLM 调用前打印 repo map 简要状态
  -> 将 repo map 注入 Pico 主模型 prompt
  -> Pico 继续通过 read_file 获取完整源码后再编辑
  -> 检索过程进入 trace、report 和 run artifacts
```

### 2.2 “单轮次”的准确语义

v1 的“单轮次”表示：

- 一个用户请求对应一个 Pico run。
- 一个 run 只执行一次 MapContext preparation。该 preparation 先生成 prepared `MapContextResult`，首次 purpose="main_model" prompt 完成实际注入渲染后，再生成同 map_context_id 的 finalized MapContextResult。后续 retry/tool loop 复用 finalized 对象，不重新运行 MapEngine。
- 一个 run 内允许存在多个主模型调用和工具调用。
- 首次 main_model build 内的 auto-compaction 复用 prepared 对象；finalized 对象生成后，后续 retry 和 tool loop 只复用 finalized 对象。两者使用同一个 `map_context_id`，且均不重新运行 MapEngine。
- v1 不在同一 run 内根据文件修改自动刷新 repo map。

### 2.2.1 关键术语

- prepared `MapContextResult`：Branch、active result 和 selection decision 已确定，但首次主模型实际注入结果与 artifact 路径尚未确定的对象。其 `prompt_injection=None`，两个 artifact path 均为 `None`。
- finalized `MapContextResult`：`finalize_prompt_context()` 根据首次主模型实际使用的 build-local `RepoMapSectionRender` 完成 evidence 和 artifact 落盘后返回的对象。它与对应 prepared 对象使用同一个 `map_context_id`。
- `ModelRequestBudget`：Pico runtime 按当前 provider/model 解析出的主模型与 selector 请求输入上限。它是所有模型请求的硬门禁事实源，不等同于 `ContextManager.total_budget`，也不等同于控制输出长度的 `max_new_tokens`。
- auto-compaction：`Pico._build_prompt_and_metadata()` 为 `purpose="main_model"` 构建 prompt 后，检测到 base prompt 超过“为当前 repo map 预留空间后的有效 base prompt 预算”且 session history 满足压缩条件时，调用 `compact_history(trigger="auto_prompt_over_budget")` 修改并持久化 session history，然后重新执行一次 prompt build。该入口定义于 `pico/pico/core/runtime.py`，具体 compaction 行为定义于 `pico/pico/core/compact.py`。`ContextManager.build()` 自身不执行 compaction，也不清除 `current_map_context`；同一次 auto-compaction 前后的 build 复用同一个 prepared `MapContextResult`。
- `MapResult.mode`：表示该结果在 MapContext 控制流中的使用意图，取值为 `broad` 或 `focused`；它不声明实际执行了 PageRank 还是 Personalized PageRank。实际 ranking 算法只由 `RankingEvidence.algorithm` 表示。
- `path_ident_hits`：`mentioned_idents` 中实际命中当前 indexed Python 文件 path terms 的稳定有序 ident 集合；它只表示有效路径词信号，不表示目录、文件 focus 或读取授权。
- `path_ident_hit_files`：以保留原始大小写的 `path_ident_hits` 为 key，记录每个 path ident 命中的全部 indexed Python 文件；它是 PromptAnalyzer 匹配事实，不等同于实际进入文件图的 `path_personalization_files`。
- `personalization_files`：实际传给 PPR 的文件集合，是 `focus_personalization_files` 与 `path_personalization_files` 的稳定并集；只有前者允许获得 focus outbound boost。
- head clip：MapEngine 在独立 token budget 内按字符估算保留候选定义前缀并裁掉尾部。repo map body 已按 rank 从高到低排列，因此 head clip 保留高 rank 前部。

### 2.3 长期边界

项目对外从一开始叫 MapCode，但是代码内部先保留 pico 的骨架命名，等 MapEngine 跑通后，再分阶段重命名。

v1 的工程策略是**先在 Pico runtime 基础上完成 MapEngine 功能接入**，利用 Pico 已有的本地 Agent 执行链路、prompt 组装、trace、report、session/run artifact 等基础设施快速验证 MapEngine 的检索价值。明确 v1 和后续都在 Pico Runtime 上增量演进。

开发上长期基于 pico 迭代；简历和产品展示上叫 MapCode；简历卖点必须落在你新增的 MapEngine、执行链路解释、上下文选择、Trace/Report/评测闭环，而不是“把 pico 改名成 MapCode”。

因此，v1 文档中出现的 Pico / Aider 对齐关系只表示**功能接口和职责层面的参考**：

- Aider 提供 repo map、tree-sitter tags、PageRank / PPR、TreeContext 渲染等行为参照，将 aider 的Repo Map 能力抽象成 MapEngine。
- Pico 提供 runtime shell、ContextManager、RunStore、SessionEventBus、trace/report/eval 等工程参照。
- 第一阶段保留pico的命名和文件结构，先融合Aider抽象成的MapEngine，这一阶段的验收标准是pico 的 agent runtime 能不能稳定驱动 MapEngine，把仓库压缩、文件选择、上下文注入、工具调用、审批、Trace、Report 串成一条可解释链路。
- 后续的所有增量能力，几乎全在 pico 上改，把完整的功能做实后，再考虑清理内部 pico 命名，也就是 **MapCode=Pico+MapEngine**。

```text
Pico runtime shell
  + MapEngine repository intelligence
  + retrieval evidence / report / eval
  = MapCode v1 implementation
```

v1 不建立第二套 SessionManager、Agent loop、TraceWriter、审批系统或工具系统。

### 2.4 明确不做

- 多用户、多会话协同。
- 同一 run 内自动增量刷新 repo map。
- child runtime / worker 启用 MapEngine。
- Aider add-to-chat、editable/read-only 文件状态机。
- embedding、LSP、语义向量检索。
- 准确 call graph 或完整影响分析。
- 将 repo map 当作文件全文或 prior-read 凭证。
- 将 README、项目配置、容器配置、CI workflow 等非 Python 文件纳入 SymbolIndex、PageRank 或 repo map。
- 使用文件系统递归扫描作为 Git 文件枚举失败时的 fallback。
- v1 不引入 `mentioned_dirs`，也不把目录样式片段（如 `pico/`、`src/`）解析为 `mentioned_files`、目录 scope 或目录硬过滤。目录样式片段按 Aider-style identifier 提取规则切成 `mentioned_idents`，命中 indexed Python 文件的路径组件时形成 `path_ident_hits`；该 path ident 命中结果用于 Branch 判断、evidence 和 ranking personalization，不直接形成文件 focus。只有文件、symbol 和 path ident 均无有效命中时才进入 Branch B selector。

---

## 三、第一性原理与核心约束

### 3.1 Repo map 的真实作用

Repo map 只回答：

- 仓库中可能相关的文件和符号在哪里。
- 为什么这些文件被选中。
- 在当前预算下哪些结构摘要进入 prompt。

Repo map 不回答：

- 文件的完整当前内容是什么。
- 某个符号调用关系是否经过语义验证。
- 哪个文件可以直接编辑。
- 模型已经读取过哪个文件。
- README、项目配置、Dockerfile、CI workflow 等非代码文件表达的项目级语义是什么。

MapEngine v1 只增强 Git tracked Python 代码的结构导航。非代码文件继续由 Pico 通过 `WorkspaceContext` 中已有的项目文档片段，以及模型按需调用 `list_files` / `read_file` 自行读取和判断。`WorkspaceContext` 是 Pico 已有组件，定义于 `pico/pico/core/workspace.py`。Git tracked Python-only 是索引范围、噪音和隐私控制方案，不表示 repo map 已解决项目级语义理解。

必须保持：

```text
repo_map_context != full_source
repo_map_context != file_summaries
repo_map_context != prior_read_authorization
```

Pico 的 `patch_file` / `write_file` 仍必须遵守现有 `read_file` freshness 规则。

### 3.2 MapEngine 是确定性检索层

MapEngine 的核心过程不需要 LLM：

```text
文件枚举
  -> tree-sitter def/ref 提取
  -> 符号引用图构建
  -> PageRank / Personalized PageRank
  -> TreeContext 渲染
  -> 预算选择
  -> MapResult + MapContextEvidence
```

Branch B 的 selector LLM 是 runtime 控制流中的可选文件选择步骤，不属于 MapEngine。

---

## 四、控制面与数据面边界

### 4.1 总体职责表

| 组件 | v1 职责 | 明确不承担 |
|---|---|---|
| `Pico` runtime | 持有服务对象、`ModelRequestBudget` 和当前 run 临时状态；提供模型、交互、trace、RunStore 能力 | 不实现 ranking |
| `Engine` | 拥有 run/turn 控制生命周期；决定 Branch A/B；编排 selector 调用、用户确认、超预算降级和最终模型调用 | 不解析仓库、不实现 ranking、不直接写 artifact |
| `MapContextCoordinator` | 将 Engine 的明确命令转换为 MapEngine 调用、证据落盘和 trace | 不决定 Branch、不调用模型、不询问用户 |
| `MapSelector` helper | 构造包含固定 system prompt、动态 user prompt 和可见路径集合的 `SelectorModelRequest`；解析和校验结构化输出 | 不发起模型调用、不访问 MapEngine |
| `MapEngine` | 索引、prompt 信号分析、图排名、渲染、生成确定性 evidence | 不调用 LLM、不询问用户、不写 trace/RunStore、不打印 UI |
| `map_context_prompt.py` | 将结构化 MapContext 状态和 MapEngine 已按独立 token budget 生成的 map body 渲染为导航安全契约、动态状态行和 repo_map section | 不调用模型、不读取仓库、不写 trace/artifact、不修改全局 prefix |
| `ContextManager` | 根据显式 prompt purpose 和 `ModelRequestBudget` 构建 prompt；为 repo map 预留输入空间、缩减 base prompt、原子注入 repo map，并返回 build-local 结果 | 不触发 MapEngine、不二次裁剪 repo map body、不执行 compaction、不修改 `current_map_context` |
| `RunStore` | 保存当前 run 的 task state、trace、report 和 artifacts | 不参与检索决策 |
| `runtime.emit_trace()` | 对事件脱敏、标准化并写入 run trace | 不驱动必要业务操作 |
| `MapEngineConsoleReporter` | 将已有 evidence 转换为用户可见摘要 | 不产生新事实、不直接参与 ranking |
| CLI / TUI | 展示 Engine yield 的用户事件，提供 ask-user callback | 不实现 Branch A/B |

### 4.2 Engine“拥有 selector 和确认”的准确含义

Engine 拥有的是控制流：

- 决定是否需要 selector 调用。
- 决定何时发起 selector 调用。
- 调用 runtime/provider 已有模型能力。
- 决定是否调用 `runtime.ask_user()`。
- 将 selector 和单选确认结果转换为 `SelectionDecision`。
- Branch B v1 只允许“接受全部有效建议”或“使用 broad map”，不允许部分接受、增删或调整建议文件。

Engine 不应实现：

- 新模型客户端。
- selector ranking 算法。
- CLI/TUI 用户界面。
- MapEngine 内部计算。

### 4.3 Coordinator 的强边界

`MapContextCoordinator` 是数据面 adapter，不是“小 Engine”。

允许：

- 调用 MapEngine 的确定性接口。
- 接收 Engine 已形成的 `SelectionDecision`。
- 调用 `runtime.emit_trace()`。
- 调用 RunStore 写 map/evidence artifact。
- 更新人类便捷查看用的 latest repo-map 快照。
- 组装 `MapContextResult`。

禁止：

- 自己判断 Branch A/B。
- 自己发起 selector 模型调用。
- 自己调用 `runtime.ask_user()`。
- 自己构建主模型 prompt。
- 直接处理 CLI/TUI。

---

## 五、推荐目录结构

```text
pico/pico/
├── features/
│   └── map_engine/
│       ├── __init__.py
│       ├── config.py
│       ├── models.py
│       ├── source_files.py
│       ├── symbol_index.py
│       ├── prompt_analyzer.py
│       ├── graph_ranker.py
│       ├── context_renderer.py
│       ├── evidence.py
│       ├── engine.py
│       └── queries/
│           └── python-tags.scm
└── core/
    ├── engine.py
    ├── runtime.py
    ├── task_state.py
    ├── map_context.py
    ├── map_context_prompt.py
    ├── map_selector.py
    ├── map_context_reporter.py
    ├── context_manager.py
    ├── context_usage.py
    ├── run_store.py
    ├── runtime_events.py
    └── worker_runtime.py
```

### 5.1 为什么使用 `features/map_engine/`

- MapEngine 是可启用/禁用的 Pico 增强 feature。
- tree-sitter、图算法和 TreeContext 属于仓库智能能力，不属于核心 Agent loop。
- MapEngine 应可在未来从 Pico runtime 中抽离。
- MapEngine 单元测试不应依赖完整 Pico runtime。

### 5.2 为什么保留 `core/map_context.py`

`features/map_engine/` 不允许依赖 Pico runtime。

`MapContextCoordinator` 定义在 `pico/pico/core/map_context.py`。该模块负责将 Pico run 生命周期与 MapEngine 确定性能力连接起来，隔离以下差异：

- Pico `TaskState` / run id。
- `runtime.emit_trace()`。
- RunStore artifact。
- 当前 run 临时状态。
- report 摘要。

### 5.3 为什么单独使用 `core/map_selector.py`

selector system prompt、动态 user prompt、JSON DTO 和路径校验不属于 MapEngine，也不应堆进 Coordinator。

`map_selector.py` 只提供纯函数：

```python
def build_selector_request(
    original_user_message: str,
    broad_result: MapResult,
    selector_catalog: SelectorCandidateCatalog,
) -> SelectorModelRequest: ...

def parse_selector_output(raw: str, allowed_files: frozenset[str]) -> SelectorResult: ...

def render_selector_confirmation(valid_files: tuple[str, ...]) -> str: ...
```

实际模型调用仍由 Engine 发起。

`original_user_message` 是当前 turn 的原始 `user_message` 输入值，在 selector 和 normal broad fallback 流程中保持不变；它不是新的 DTO，也不表示要求用户再次输入。

`build_selector_request()` 返回的 `SelectorModelRequest.system_prompt` 是 selector LLM 的固定 provider-level system prompt。模板中的 `{max_selector_suggested_files}` 必须在请求发送前替换为 `MAX_SELECTOR_SUGGESTED_FILES` 的十进制字符串：

```text
You are MapCode's Branch-B file selector.

Your only job is to understand the user's request and select the most semantically relevant existing source files from the provided Broad Repo Map and Selector Candidate Catalog.

You are not the main coding agent.
Do not propose code changes.
Do not propose patches.
Do not propose test edits.
Do not write implementation plans.
Do not call or suggest tools.
Do not infer that any selected file has already been read.
Do not treat repo map snippets as complete file content.

You must respond ONLY with a JSON object in this exact format:
{
  "suggested_files": ["relative/path/to/file.py"],
  "reasoning": "brief explanation"
}

Rules:
- Only include files shown in the Broad Repo Map or Selector Candidate Catalog in the selector input
- Use repo-relative paths exactly as shown
- Do not suggest new files
- Return an empty list if no files are clearly relevant
- Prefer implementation/source files over test files for normal analysis, bug fixing, and feature requests
- Include test files only when the user explicitly asks about tests, test failures, pytest behavior, regression coverage, or when the test file is clearly necessary to understand the requested behavior
- Return at most {max_selector_suggested_files} files
```

JSON 示例本身必须是有效 JSON，因此不在数组中使用 `...`。`suggested_files` 可以包含零到 `MAX_SELECTOR_SUGGESTED_FILES` 个路径。

`SelectorModelRequest.user_prompt` 只保存本次 selector 的动态输入，固定格式为：

```text
[User Request]
{original_user_message}

[Broad Repo Map]
{broad_repo_map_text}

[Selector Candidate Catalog]
{selector_catalog_text}
```

`SelectorModelRequest.visible_paths` 是 `broad_result.rendered_files` 与 `selector_catalog.rendered_paths` 按首次出现顺序稳定去重后的并集。它是 selector 输入中实际展示路径的唯一事实源，也是 `parse_selector_output()` 的 `allowed_files` 来源。`candidate_paths` 仍用于证明 catalog 来源属于当前 SymbolIndex snapshot，但未进入 `visible_paths` 的路径不得被 selector 输出接受。

`parse_selector_output()` 在 JSON 成功解析后执行字段类型检查、路径校验、稳定去重、建议数量限制和 reasoning 字符限制；不得先裁剪原始 JSON 再解析。顶层必须是只包含 `suggested_files` 和 `reasoning` 的 JSON object；缺字段、额外字段或字段类型错误均记录为 `parse_error`，并形成无有效建议结果。

### 5.4 为什么单独使用 `core/map_context_prompt.py`

`map_context_prompt.py` 保存 repo map 注入主模型时使用的固定导航安全契约，并根据 `MapContextResult` 生成动态状态行。

它只提供纯模板和纯渲染函数，例如：

```python
def render_repo_map_contract(result: MapContextResult) -> str: ...

def render_repo_map_section(
    result: MapContextResult,
    active_repo_map_text: str,
) -> RepoMapSectionRender: ...
```

放在 `core/` 而不是 MapEngine 中，因为：

- 这段文本约束的是 Pico 主模型如何消费 repo map，不属于确定性索引、ranking 或 rendering。
- 它需要读取 `MapContextResult` 中的 branch、stage、focus 和 fallback 控制事实。
- MapEngine 不应了解 Pico prompt 格式。
- Coordinator 不构建主模型 prompt。

这段契约也不写入 Pico 全局 prefix。只有当前 run 存在 `MapContextResult` 时，ContextManager 才注入它，避免 MapEngine 禁用或 MapContext 失败时污染 Pico 原有行为。

---

## 六、数据模型

所有跨模块 DTO 优先使用不可变 dataclass。完整 repo map 文本和完整 evidence 不写入 session。

DTO 只描述跨模块传递或需要持久化的事实。模块内部临时变量不为“补类型”而额外建立 DTO。

### 6.1 PromptAnalysis

```python
@dataclass(frozen=True)
class PromptAnalysis:
    branch: Literal["specific", "fuzzy"]
    mentioned_files: tuple[str, ...]
    mentioned_idents: tuple[str, ...]
    effective_symbol_hits: tuple[str, ...]
    path_ident_hits: tuple[str, ...]
    path_ident_hit_files: Mapping[str, tuple[str, ...]]
```

规则：

```text
specific = mentioned_files 非空 OR effective_symbol_hits 非空 OR path_ident_hits 非空
fuzzy    = mentioned_files 为空 AND effective_symbol_hits 为空 AND path_ident_hits 为空
```

`PromptAnalysis` 不保存 `focus_fnames`，避免同一个聚焦文件集合出现多个来源：

- Branch A 调用 focused generation 时，`focus_fnames = analysis.mentioned_files`。
- Branch A 仅命中 symbol、未命中文件时，`focus_fnames = ()`，依靠完整 `mentioned_idents` 做 ident boost。
- Branch A 仅命中 path ident、未命中文件时，`focus_fnames = ()`，依靠 `path_ident_hits` 形成 path personalization。
- Branch B 接受建议时，`focus_fnames = selection_decision.confirmed_files`。
- 最终实际使用的聚焦文件只保存在 `MapResult.focus_fnames`。

`path_ident_hit_files` 是只读映射，满足以下不变量：

- `tuple(path_ident_hit_files.keys()) == path_ident_hits`。
- key 保留 prompt 中 ident 的原始大小写，并按 `mentioned_idents` 首次出现顺序排列。
- 每个 value 包含该 ident 命中的全部当前 indexed Python 文件，按 repo-relative path 升序排列。
- value 不受文件图节点、PageRank、rendering 或 token budget 过滤。
- 同一 normalized lowercase ident 以不同原始大小写多次出现在 `mentioned_idents` 时，可以分别保留为不同 key；ranking 对同一文件仍只增加一次 path personalization contribution。
- 构造完成后不得修改；写入 trace 或 evidence artifact 时序列化为保持上述 key 顺序的普通 JSON object。

### 6.2 SymbolIndex 与 MapEngine evidence 基础 DTO

以下类型是现有 SymbolIndex、ranking、rendering 和 evidence 数据流需要的最小跨模块契约：

```python
@dataclass(frozen=True)
class DefinitionRecord:
    name: str
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class ReferenceRecord:
    name: str
    path: str
    line: int


@dataclass(frozen=True)
class FileRecord:
    path: str
    mtime_ns: int
    size: int
    parser_version: str
    query_version: str
    schema_version: str


@dataclass(frozen=True)
class RankContributorEvidence:
    source_path: str
    identifier: str
    weighted_edge: float
    weight_multiplier: float
    weight_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RenderedFileEvidence:
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    render_rank: int
    reason_codes: tuple[str, ...]
    prompt_symbol_hits: tuple[str, ...]
    prompt_path_ident_hits: tuple[str, ...]
    rendered_symbols: tuple[str, ...]
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class OmittedFileEvidence:
    path: str
    node_pagerank: float
    pagerank_norm: float
    definition_rank_sum: float
    omission_reason: str
    reason_codes: tuple[str, ...]
    prompt_symbol_hits: tuple[str, ...]
    prompt_path_ident_hits: tuple[str, ...]
    top_rank_contributors: tuple[RankContributorEvidence, ...]


@dataclass(frozen=True)
class RankingEvidence:
    policy_version: str
    algorithm: Literal["pagerank", "personalized_pagerank", "stable_path_fallback"]
    focus_fnames: tuple[str, ...]
    ident_boost_inputs: tuple[str, ...]
    focus_personalization_files: tuple[str, ...]
    path_personalization_files: tuple[str, ...]
    personalization_files: tuple[str, ...]
    top_ranked_files: tuple[str, ...]


@dataclass(frozen=True)
class RenderingEvidence:
    target_tokens: int
    target_chars: int
    used_chars: int
    estimated_tokens: int
    budget_reduction_applied: bool
    focus_truncated: bool


@dataclass(frozen=True)
class CacheEvidence:
    read_status: Literal["hit", "miss", "read_failed"]
    write_status: Literal["not_needed", "written", "write_failed"]
    reused_files: tuple[str, ...]
    parsed_files: tuple[str, ...]
    skipped_files: tuple[str, ...]


@dataclass(frozen=True)
class IndexStatus:
    index_snapshot_id: str
    cache_status: CacheEvidence
    file_count: int
    definition_count: int
    reference_count: int
```

约束：

- 所有 `path` 均为 repo-relative path。
- `line` 使用 tree-sitter / TreeContext 消费所需的 0-based 行索引；仅在人类展示层需要时转换为 1-based 行号。
- `GraphRanker -> ContextRenderer` 使用按第 7.6 节规则排序后的 `tuple[DefinitionRecord, ...]` 和文件级排序结果；无 definition 的文件仍可按文件级排序输出路径，不为单个 definition 建立分数字段。
- `RankingEvidence.algorithm` 记录实际执行结果：使用 personalization 时为 `personalized_pagerank`，未使用 personalization 时为 `pagerank`，PageRank/PPR 失败或图为空时为 `stable_path_fallback`。
- `RankingEvidence.focus_fnames` 保存调用方要求聚焦的 repo-relative 文件，按调用方输入顺序稳定去重；它表示控制流输入，不保证每个文件都能成为 PPR seed。
- `RankingEvidence.focus_personalization_files` 是 `focus_fnames` 中实际存在于本次文件图节点的有序子集；只有这些文件可以获得 focus personalization contribution 和 `FOCUS_OUTBOUND_BOOST`。
- `RankingEvidence.path_personalization_files` 是 `path_ident_hit_files` values 中实际存在于本次文件图节点的文件稳定有序并集；它按 repo-relative path 升序保存，只获得 path personalization contribution，不获得 `FOCUS_OUTBOUND_BOOST`。
- `RankingEvidence.personalization_files` 是 `focus_personalization_files` 与 `path_personalization_files` 的稳定有序并集，也是实际传给 PageRank personalization 的文件集合。它不再要求是 `focus_fnames` 的子集。
- `PromptAnalysis.path_ident_hit_files` 保存 PromptAnalyzer 发现的全部 indexed file 匹配；`RankingEvidence.path_personalization_files` 只保存其中实际存在于本次文件图节点的稳定有序并集。两者不得混用。
- 每个 `MapResult` 必须满足 `MapResult.focus_fnames == MapResult.evidence.ranking.focus_fnames`。
- `IndexStatus` 只描述当前已就绪 SymbolIndex snapshot 和 cache 事实，供 Coordinator 在 prompt analysis 与 ranking 前发出 `map_index_status`；它不包含 ranking 或 rendering 信息。
- `IndexStatus.file_count = len(file_records)`；`definition_count` 和 `reference_count` 分别为 `definitions_by_file` 与 `references_by_file` 中记录数量的总和。
- `RankingEvidence.top_ranked_files` 保存预算渲染前排名最高的最多 `TOP_RANKED_FILES_LIMIT` 个不同文件。PageRank/PPR 成功时按 `node_pagerank` 降序、repo-relative path 升序打破平局；stable path fallback 时按 fallback 的稳定路径顺序。
- `RenderedFileEvidence` 只表示最终进入候选 map body 的文件；`OmittedFileEvidence` 只表示未进入候选 map body 的文件。
- `target_chars = target_tokens * 4`，`estimated_tokens = ceil(used_chars / 4)`；v1 使用该稳定估算执行 token budget，不表示模型 tokenizer 的精确结果。
- `budget_reduction_applied` 只表示 MapEngine 候选 map body 因独立 token budget 发生截断。

### 6.3 MapContextEvidence

`MapContextEvidence` 只保存 MapEngine 在不依赖 selector、用户确认和 Pico runtime 控制流的情况下产生或测量的事实：

```python
@dataclass(frozen=True)
class MapContextEvidence:
    schema_version: str
    index_snapshot_id: str
    analysis: PromptAnalysis
    ranking: RankingEvidence
    rendering: RenderingEvidence
    rendered_files: tuple[RenderedFileEvidence, ...]
    omitted_files: tuple[OmittedFileEvidence, ...]
    cache_status: CacheEvidence
    duration_ms: int
```

不得包含：

- selector LLM 原始输出。
- 用户确认结果。
- runtime trace id。
- artifact path。
- 终端打印文本。

### 6.4 MapResult

MapEngine 的唯一主要输出：

```python
@dataclass(frozen=True)
class MapResult:
    mode: Literal["broad", "focused"]
    repo_map_text: str					#实际渲染出的map候选文本，不是最终注入模型的文本
    focus_fnames: tuple[str, ...]		#调用方要求聚焦的文件，不等同于实际 personalization seed
    rendered_files: tuple[str, ...]		#进入map body的文件路径列表
    rendered_symbols: tuple[str, ...]	#进入map body的符号列表
    evidence: MapContextEvidence		#可解释证据
```

`MapResult.mode` 表示控制流使用意图，不表示实际 ranking 算法。特别是 symbol-only Branch A 仍返回 `mode="focused"`，但由于 `focus_fnames=()`、`personalization_files=()`，其实际算法记录为 `algorithm="pagerank"`；path-ident-only Branch A 同样返回 `mode="focused"`，当存在 `path_personalization_files` 时实际算法记录为 `algorithm="personalized_pagerank"`。若 PageRank/PPR 失败或图为空，则记录为 `algorithm="stable_path_fallback"`。

### 6.5 SelectorCandidateCatalog、SelectorModelRequest、SelectorResult 与 SelectionDecision

```python
@dataclass(frozen=True)
class SelectorCandidateCatalog:
    index_snapshot_id: str
    candidate_paths: tuple[str, ...]       # 当前 snapshot 的全量稳定路径，用于 catalog 完整性和来源证明
    rendered_paths: tuple[str, ...]        # 实际展示给 selector 的路径
    rendered_text: str                     # 受 selector catalog 预算约束
    file_count: int                         # 全量候选文件数
    definition_count: int                   # 全量 DefinitionRecord 数
    rendered_file_count: int
    rendered_definition_count: int
    estimated_tokens: int
    truncated: bool


@dataclass(frozen=True)
class SelectorModelRequest:
    system_prompt: str
    user_prompt: str
    visible_paths: tuple[str, ...]


@dataclass(frozen=True)
class SelectorResult:
    suggested_files: tuple[str, ...]
    invalid_files: tuple[str, ...]
    excess_files: tuple[str, ...]
    reasoning: str
    parse_error: str | None


FallbackReason = Literal[
    "one_shot_no_confirm",
    "selector_request_over_budget",
    "selector_no_valid_files",
    "user_selected_broad",
    "user_cancelled",
    "invalid_confirmation",
]


@dataclass(frozen=True)
class SelectionDecision:
    selector_result: SelectorResult | None
    confirmed_files: tuple[str, ...]
    fallback_mode: Literal["none", "broad_map"]
    fallback_reason: FallbackReason | None

    @classmethod
    def broad_fallback(
        cls,
        reason: FallbackReason,
        selector_result: SelectorResult | None = None,
    ) -> "SelectionDecision": ...

    @classmethod
    def from_single_choice(
        cls,
        selector_result: SelectorResult,
        answer: str,
    ) -> "SelectionDecision": ...
```

`SelectorCandidateCatalog` 由 MapEngine 从当前已就绪 SymbolIndex snapshot 确定性生成。它不包含完整源码，也不包含 SymbolIndex 范围外的文件。

catalog 的全量 snapshot 路径、模型可见文本和 selector 输出校验集合必须区分：

- `candidate_paths` 保存当前 snapshot 中全部已索引 Python 文件路径，按 repo-relative path 升序稳定排序，用于证明 catalog 来源和校验 `rendered_paths` 完整性；它不是 selector 输出的直接 `allowed_files`。
- `rendered_text` 只展示受 `SELECTOR_CATALOG_MAX_FILES`、`SELECTOR_CATALOG_MAX_DEFS_PER_FILE` 和 `SELECTOR_CATALOG_MAX_TOKENS` 约束的候选目录。
- `rendered_paths` 是实际出现在 `rendered_text` 中的路径，始终是 `candidate_paths` 的有序子集。
- `SelectorModelRequest.visible_paths` 是 broad map 实际展示文件与 `rendered_paths` 的稳定并集；只有其中路径可以进入 `SelectorResult.suggested_files`。
- selector 可以建议未进入 broad map、但实际出现在 `rendered_text` 中的文件。不得把 `candidate_paths` 描述为模型已看到的全量目录，也不得接受只存在于 `candidate_paths`、但没有展示给 selector 的路径。
- 文件按 repo-relative path 升序处理；每个文件内的 `DefinitionRecord` 按 `(line, name, kind)` 升序稳定排序，最多展示前 N 条。
- 超过 catalog token 预算时，只按完整文件块执行 head clip；不得截断路径行或输出无法解析的半个文件块。没有 definition 的文件仍可输出完整路径行。

`SelectionDecision` 由 Engine 形成后交给 Coordinator。

Branch B v1 的确认协议：

- `runtime.ask_user()` 只返回一个字符串，因此交互选项固定为 `["接受全部建议", "使用 broad map"]`。
- “接受全部建议”只接受路径校验后的 `suggested_files`，不包含 `invalid_files`。
- v1 不支持部分接受、增删或调整 selector 建议文件。
- selector 没有有效建议时不调用 `runtime.ask_user()`，直接使用 `selector_no_valid_files` broad fallback。
- 用户选择“使用 broad map”、Esc 返回空字符串或返回未知值时，分别形成 `user_selected_broad`、`user_cancelled` 或 `invalid_confirmation` broad fallback。
- `fallback_mode="none"` 时，`confirmed_files` 必须非空且 `fallback_reason=None`。
- `fallback_mode="broad_map"` 时，`confirmed_files=()` 且 `fallback_reason` 必须是 `FallbackReason` 中的一个值。
- 只有 `one_shot_no_confirm` 的 `selector_result=None`；只要实际调用过 selector，最终 `SelectionDecision.selector_result` 必须保存该次解析和校验结果。
- `selector_request_over_budget` 表示完整 `SelectorModelRequest.system_prompt + user_prompt` 超过 `ModelRequestBudget`，因此没有实际调用 selector，`selector_result=None` 且 `selector_model_calls` 不增加。
- `broad_fallback()` 和 `from_single_choice()` 只负责把已有 selector/确认结果规范化为不可变决策，不调用模型、不询问用户、不写 trace。
- `from_single_choice()` 的映射固定为：
  - `"接受全部建议"`：`confirmed_files=selector_result.suggested_files`、`fallback_mode="none"`。
  - `"使用 broad map"`：`user_selected_broad` fallback。
  - 空字符串：`user_cancelled` fallback。
  - 其他字符串：`invalid_confirmation` fallback。
- selector 解析失败或没有有效路径时，不调用 `from_single_choice()`，直接使用 `selector_no_valid_files` fallback；具体解析错误保留在 `SelectorResult.parse_error`。
- `parse_selector_output()` 先成功解析完整 JSON object 并校验固定字段，再规范化路径、按模型返回顺序稳定去重并使用 `SelectorModelRequest.visible_paths` 校验。前 `MAX_SELECTOR_SUGGESTED_FILES` 个有效路径进入 `suggested_files`，其余有效路径进入 `excess_files`，无效路径进入 `invalid_files`；`reasoning` 最终最多保留 `SELECTOR_REASONING_MAX_CHARS` 个字符。
- selector 没有有效建议或用户选择 broad fallback 时，Engine 复用 `original_user_message` 与已生成的 broad map 进入首次主模型调用；不得重新调用 selector、重新询问用户或要求用户重新输入 prompt。

### 6.6 MapContextResult

`MapContextResult` 是当前 run 中供 ContextManager 使用的完整对象：

```python
@dataclass(frozen=True)
class MapContextResult:
    map_context_id: str
    branch: Literal["specific", "fuzzy"]
    stage: Literal["execution", "fallback"]
    active_result: MapResult
    broad_result: MapResult | None			# Branch B 才有：selector 前生成的全景图
    selection_decision: SelectionDecision | None     # Branch B 才有：用户最终怎么选的
    selector_model_calls: int				# 这个 run 里 selector 调了几次
    prompt_injection: PromptInjectionEvidence | None
    repo_map_artifact_path: str | None		# artifact 落盘后填入
    evidence_artifact_path: str | None		# artifact 落盘后填入
```

约束：

- `current_map_context` 保存此对象，不保存字符串。
- ContextManager 使用 `active_result.repo_map_text`。
- `broad_result` 仅在 Branch B 中存在。
- 完整对象只在当前 run 生命周期内复用。
- `map_context_id = "mapctx_" + uuid4().hex`，由 Coordinator 在创建 prepared `MapContextResult` 时生成；finalized 对象沿用同一个 id。
- preparation 阶段 prompt/artifact 字段为空；首次主模型请求实际使用的 prompt section 确定后，Coordinator 返回带最终注入摘要和 artifact 路径的新对象。
- `stage` 和 `selection_decision.fallback_reason` 由 `map_context_prompt.py` 转换为动态 fallback notice，不由 MapEngine 生成自然语言提示。
- `stage="execution"` 表示 Branch A focused map，或 Branch B 接受全部有效建议后成功生成的 focused map；此时 `active_result.mode="focused"`。
- `stage="fallback"` 只表示 Branch B 正常使用 broad map fallback；此时 `active_result.mode="broad"`、`broad_result is active_result`，并且 `selection_decision.fallback_mode="broad_map"`。
- MapContext 整体失败不创建 `MapContextResult`，而是设置 `current_map_context=None` 后继续 Pico 原执行链。
- Branch A：`branch="specific"`、`broad_result=None`、`selection_decision=None`。
- Branch B confirmed focused：`branch="fuzzy"`、`stage="execution"`、`broad_result` 保存 selector 前生成的 broad map、`selection_decision.fallback_mode="none"`。
- Branch B broad fallback：`branch="fuzzy"`、`stage="fallback"`、`active_result` 复用 `broad_result`。
- Branch B 的 broad 与 focused 结果必须复用同一个 SymbolIndex snapshot，因此其 `index_snapshot_id` 必须相同；用户确认期间不重新枚举或刷新索引。
- Branch A 的 `selector_model_calls=0`；Branch B 中，`selector_model_calls = 1 if selection_decision.selector_result is not None else 0`。因此 one-shot fallback 和 `selector_request_over_budget` 为 0，其他实际调用过 selector 的 Branch B 路径为 1。v1 每个 run 最多调用一次 selector。
- `MapContextResult.selector_model_calls` 是 preparation 完成时 `TaskState.selector_model_calls` 的不可变快照。
- prepared 对象固定为 `prompt_injection=None` 且两个 artifact path 均为 `None`；finalized 对象固定为 `prompt_injection` 和两个 artifact path 均非空。

### 6.7 RepoMapSectionRender 与 PromptInjectionEvidence

`RepoMapSectionRender` 是 ContextManager 单次 build 的局部渲染结果：

```python
@dataclass(frozen=True)
class RepoMapSectionRender:
    section_text: str
    section_rendered: bool
    contract_rendered: bool
    fallback_notice_rendered: bool
    map_body_raw_chars: int
    map_body_rendered_chars: int
    section_rendered_chars: int
    section_rendered_hash: str
    base_prompt_reduction_applied: bool
    omission_reason: str | None
```

`PromptInjectionEvidence` 记录首次 `purpose="main_model"` 调用完成可能的 auto-compaction 后，最终返回并用于主模型请求的实际注入结果：

```python
@dataclass(frozen=True)
class PromptInjectionEvidence:
    section_rendered: bool
    contract_rendered: bool
    fallback_notice_rendered: bool
    map_body_raw_chars: int
    map_body_rendered_chars: int
    section_rendered_chars: int
    section_rendered_hash: str
    base_prompt_reduction_applied: bool
    omission_reason: str | None
```

约束：

- `contract_rendered=True` 时必须表示完整契约已注入，不能表示只保留了部分文本。
- `section_rendered=False` 时，`repo-map-001.txt` 保存首次主模型请求实际使用 prompt 的空注入结果，evidence 必须记录 `omission_reason`。
- `map_body_raw_chars` 是当前 active MapResult 候选 `{active_repo_map_text}` 的字符数，不包含固定导航安全契约、动态状态行或 fallback notice。
- `map_body_rendered_chars` 是实际进入 `section_text` 的 map body 字符数；正常注入时等于 `map_body_raw_chars`。
- `PromptInjectionEvidence` 由首次主模型 build 返回的 `RepoMapSectionRender` 逐字段复制得到，不允许从完整 prompt 字符串反推。
- `section_rendered=False` 时固定为：`section_text=""`、`contract_rendered=False`、`fallback_notice_rendered=False`、`map_body_rendered_chars=0`、`section_rendered_chars=0`、`section_rendered_hash=sha256("")`，且 `omission_reason` 非空。
- `section_rendered_hash` 固定使用 `"sha256:" + sha256(section_text UTF-8 bytes).hexdigest()`；因此空 section 的 hash 也是稳定非空字符串。
- `base_prompt_reduction_applied` 表示本次 build 是否为了给完整 repo map section 预留输入空间而缩减 Pico base prompt。它不表示 repo map body 被二次裁剪。

### 6.8 ModelRequestBudget、PromptPurpose 与 PromptBuildResult

```python
@dataclass(frozen=True)
class ModelRequestBudget:
    provider: str
    model: str
    model_input_budget_tokens: int
    prompt_safety_margin_tokens: int
    estimation_method: str
    source: Literal["explicit", "provider_model", "fallback"]


PromptPurpose = Literal[
    "main_model",
    "prompt_preview",
    "evaluation",
    "step_limit_summary",
]


@dataclass(frozen=True)
class PromptBuildResult:
    prompt: str
    metadata: dict
    repo_map_render: RepoMapSectionRender | None
```

约束：

- `ModelRequestBudget` 由 Pico runtime 初始化并持有，ContextManager、Engine selector 路径和最终 provider 调用读取同一个对象；MapEngine 不读取该对象。
- `model_input_budget_tokens` 表示当前 provider/model 允许发送的最大输入 token 数，不表示输出上限。Pico 原有 `max_new_tokens` 继续只控制输出。
- 预算解析优先级固定为：显式项目或 CLI 配置、已知 provider/model 配置、保守 fallback。未知模型不得继续使用 `ContextUsageAnalyzer.DEFAULT_CONTEXT_WINDOW` 作为未经校验的硬上限。
- v1.3 可以继续使用统一 `ceil(chars / 4)` 估算，但只能声明为保守门禁估算，不能声明为模型 tokenizer 的精确结果。后续可替换 estimator，不改变预算控制流。
- 每个 prompt build 调用点必须显式提供 `purpose`，不提供默认值。
- `repo_map_render` 只属于当前 `PromptBuildResult`，不得通过 `ContextManager.last_map_section_render` 或其他共享可变状态传递。
- Engine 只能持久化首次 `purpose="main_model"` 调用最终返回、并用于主模型请求的 `repo_map_render`。
- 辅助 prompt build 不得修改或覆盖主模型 prompt render 状态。
- `PromptBuildResult.metadata` 必须记录 `model_input_budget_tokens`、`prompt_safety_margin_tokens`、`active_repo_map_reservation_tokens`、`base_prompt_budget_tokens`、`estimated_request_tokens`、`request_over_budget` 和预算来源。

### 6.9 MapEvidenceArtifact

`map-evidence-001.json` 不是 `MapContextEvidence` 的直接序列化，而是由 Coordinator 在 run 级组装的 evidence envelope：

```python
@dataclass(frozen=True)
class MapResultEvidence:
    mode: Literal["broad", "focused"]
    focus_fnames: tuple[str, ...]
    rendered_files: tuple[str, ...]
    rendered_symbols: tuple[str, ...]
    evidence: MapContextEvidence


@dataclass(frozen=True)
class MapEvidenceArtifact:
    schema_version: str
    map_context_id: str
    run_id: str
    branch: Literal["specific", "fuzzy"]
    stage: Literal["execution", "fallback"]
    index_snapshot_id: str
    analysis: PromptAnalysis
    broad_result: MapResultEvidence | None
    active_result: MapResultEvidence
    selection_decision: SelectionDecision | None
    prompt_injection: PromptInjectionEvidence
    repo_map_artifact_path: str
```

分层规则：

- `MapContextEvidence` 只包含 MapEngine 确定性事实，因此不包含 `run_id`、用户确认或 artifact path。
- `MapEvidenceArtifact` 是 run artifact，可以包含 `run_id`、`SelectionDecision`、最终 prompt 注入事实和 repo map artifact path。
- `MapResultEvidence` 从 `MapResult` 复制结构化字段，但不复制完整 `repo_map_text`；实际注入文本只保存在 `repo-map-001.txt`。
- evidence artifact 不在自身 payload 中保存自身路径，避免写入前无法确定路径的循环依赖；其路径由 TaskState、trace 和 report 保存。

### 6.10 TaskState 持久化摘要

`TaskState` 不直接保存完整 `MapContextResult`，只保存可序列化摘要：

```python
map_context_summary: dict = {
    "map_context_id": "...",
    "branch": "specific",
    "stage": "execution",
    "focus_fnames": [],
    "rendered_files": [],
    "index_snapshot_id": "...",
    "repo_map_artifact_path": "...",
    "evidence_artifact_path": "...",
    "selector_model_calls": 0,
}
```

`TaskState` 另新增独立整数计数 `main_model_calls: int = 0` 和 `selector_model_calls: int = 0`。两者是 run 级实际模型调用计数；`map_context_summary.selector_model_calls` 是 MapContext preparation 完成时从 `TaskState.selector_model_calls` 复制的摘要值。具体递增语义见第 11.3 节。

---

## 七、MapEngine 模块职责

### 7.1 `models.py`

`models.py` 是第六章 MapEngine-owned DTO 的唯一代码定义位置，包括：

- `PromptAnalysis`。
- `IndexStatus`。
- `SelectorCandidateCatalog`。
- SymbolIndex records。
- ranking / rendering / file evidence。
- `MapContextEvidence`。
- `MapResult`。

Pico runtime-owned DTO，例如 `SelectionDecision`、`MapContextResult`、`RepoMapSectionRender`、`PromptBuildResult` 和 `MapEvidenceArtifact`，定义在对应 `core/` 模块中，不反向放入 `features/map_engine/`，避免 MapEngine 依赖 Pico runtime。

对应所有权固定为：

- `core/map_selector.py`：`SelectorModelRequest`、`SelectorResult`、`SelectionDecision` 和 `FallbackReason`。
- `core/map_context.py`：`MapContextCoordinator`、`MapContextResult`、`MapResultEvidence` 和 `MapEvidenceArtifact`。
- `core/map_context_prompt.py`：`RepoMapSectionRender`。
- `core/context_manager.py`：`PromptPurpose` 和 `PromptBuildResult`。

### 7.2 `config.py`

唯一预算和索引配置事实源：

```python
FOCUSED_MAP_BUDGET_TOKENS = 4_096
BROAD_MAP_BUDGET_TOKENS = 8_192
SELECTOR_CATALOG_MAX_TOKENS = 4_096
SELECTOR_CATALOG_MAX_FILES = 200
SELECTOR_CATALOG_MAX_DEFS_PER_FILE = 20
MAP_ENGINE_SCHEMA_VERSION = "mapcode.map-engine.v1"
PARSER_VERSION = "mapcode-python-tags-v1"
QUERY_VERSION = "mapcode-python-query-v1"
RANKING_POLICY_VERSION = "mapcode-pagerank-v1"
PAGERANK_ALPHA = 0.85
PAGERANK_MAX_ITER = 100
PAGERANK_TOL = 1e-6
IDENT_BOOST = 10.0
STRUCTURED_IDENT_BOOST = 10.0
PRIVATE_IDENT_PENALTY = 0.1
COMMON_IDENT_PENALTY = 0.1
COMMON_IDENT_DEFINER_THRESHOLD = 5
STRUCTURED_IDENT_MIN_LENGTH = 8
FOCUS_OUTBOUND_BOOST = 50.0
TOP_RANKED_FILES_LIMIT = 5
```

不要在 ContextManager、runtime 和 MapEngine 中分别硬编码不同值。

`SELECTOR_CATALOG_*` 属于 MapEngine `config.py`，因为它们约束 MapEngine 生成的确定性 catalog。以下 selector 输出约束属于 `core/map_selector.py`，因为它们约束模型输出解析，不属于 MapEngine：

```python
SELECTOR_REASONING_MAX_CHARS = 500
MAX_SELECTOR_SUGGESTED_FILES = 5
```

`ModelRequestBudget` 的 provider/model 输入上限和安全余量属于 Pico runtime 配置，不放入 MapEngine `config.py`。v1.3 对未知模型使用可配置的保守 fallback；同一个解析结果同时用于主模型和 selector 请求。

### 7.3 `source_files.py`

职责：

- 以 `workspace.repo_root` 作为 Git 操作目录。
- 通过 `git ls-files --cached -z` 枚举 Git index 中已 tracked 或 staged 的仓库文件。
- 只保留当前工作树中仍存在的普通 `.py` 文件；v1 只支持 Python。
- 非代码文件不进入 `source_files.py` 输出、SymbolIndex、PageRank 或 repo map。
- 统一拒绝 `.git/`、`.pico/`、虚拟环境、缓存和生成目录，即使这些路径被误提交。
- 返回 repo-relative 路径。

范围与降级约束：

- 未 tracked 的 Python 文件不进入 repo map。
- tracked 但已从工作树删除的文件跳过并记录 evidence。
- 当前 workspace 不是 Git repository，或 Git 文件枚举失败时，MapEngine 降级为不可用，Pico 原执行链继续。
- 禁止在 Git 文件枚举失败时回退为文件系统递归扫描。
- Git index 只作为路径枚举来源；MapEngine 实际解析的是当前 working tree 中对应路径的文件内容，不读取 Git index blob。
- Git tracked 不是密钥安全边界；被错误提交的 Python 密钥仍可能进入索引，因此进入 trace/artifact 前仍必须经过 runtime redaction。

不承担：

- AST 解析。
- ranking。
- 非代码文件内容读取或项目级语义判断。

### 7.4 `symbol_index.py`

职责：

- lazy build：首次用户请求到达后才枚举和解析。
- 使用 tree-sitter query 提取 Definition / Reference。
- 维护文件元信息、parser/query version 和 index snapshot id。
- 读取和更新持久索引与 cache metadata。

持久化路径：

```text
.pico/map_engine/index.json#机器可读 symbol/ref/index 存储；仅供 MapEngine 分析、排名和生成候选 map，selector 不直接读取
.pico/map_engine/cache.meta.json#mtime、size、parser/query/schema version、index_snapshot_id
```

索引失效至少考虑：

- repo-relative path。
- mtime。
- file size。
- parser version。
- query version。
- schema version。

SymbolIndex 输出契约：

SymbolIndex lazy build 完成后必须提供以下只读结构，供 PromptAnalyzer、GraphRanker 和 Evidence 复用：

- all_defs: frozenset[str]
  当前索引中所有可识别 symbol 名称，用于计算 effective_symbol_hits。

- definitions_by_symbol: dict[str, tuple[DefinitionRecord, ...]]
  symbol 名称到定义位置的多值映射。不得假设一个 symbol 只对应一个文件。

- definitions_by_file: dict[str, tuple[DefinitionRecord, ...]]
  repo-relative path 到该文件内定义符号的映射，用于 TreeContext 风格渲染。

- references_by_file: dict[str, tuple[ReferenceRecord, ...]]
  repo-relative path 到该文件内引用符号的映射，用于构建文件级 def/ref 图。

- file_records: dict[str, FileRecord]
  文件路径、mtime、size、parser/query/schema version 等元信息。

- index_snapshot_id: str
  当前索引快照标识，必须进入 trace、report 和 evidence。

`index_snapshot_id` 的生成规则：

```text
index_snapshot_id = "sha256:" + sha256(canonical_json({
  "schema_version": MAP_ENGINE_SCHEMA_VERSION,
  "parser_version": PARSER_VERSION,
  "query_version": QUERY_VERSION,
  "files": 按 repo-relative path 排序后的 [{"path", "mtime_ns", "size"}]
}))
```

v1 的 snapshot id 只标识索引输入元数据和索引实现版本，不包含 ranking policy，也不是 working tree 内容的强一致 content hash。`canonical_json` 固定使用 UTF-8、键排序和无多余空白的 JSON 序列化。ranking policy 单独记录在 `RankingEvidence.policy_version` 中。

SymbolIndex 不直接运行 PageRank，不直接生成 repo map，不直接输出 prompt 文本。
GraphRanker 根据 definitions_by_symbol 与 references_by_file 构建：

referencer_file --identifier--> definer_file

形式的文件级引用图。

### 7.5 `prompt_analyzer.py`

职责：

- 从当前用户请求提取准确文件路径、basename、stem 和 Aider-style identifier。
- 用 index 中的 defs 验证 symbol hits。
- 用 indexed file path 验证 path ident hits。
- 生成 `PromptAnalysis`。

不承担：

- LLM 调用。
- PageRank。
- Branch B 文件选择。

PromptAnalyzer 提取规则：

1. mentioned_idents：

- 当前 user_message 使用 re.split(r"\W+", text) 提取。
- 过滤空字符串后，按用户消息中的首次出现顺序稳定去重。
- 保持原始大小写；不额外过滤 Python keyword、纯数字或单字符 token，避免引入未定义的语义判断。
- 保留完整 token 集合作为 graph_ranker 的 ident boost 输入。
- 不要求 token 必须命中文件间引用关系图。

2. mentioned_files：

- 准确路径匹配先提取 prompt 中的 path-like token，去除包裹路径的 Markdown 标记、引号和句尾标点，并将 `\` 统一为 `/`。
- repo-relative path、以 `./` 开头的 repo-relative path，以及位于 `workspace.repo_root` 内的 absolute path，在规范化为 repo-relative path 后，只有精确存在于当前 `SymbolIndex.file_records` 时才进入 `mentioned_files`。
- absolute path 位于 repo root 外、路径规范化后越出 repo root、只命中目录、只命中路径前缀，或未精确命中当前 indexed Python 文件时，不进入 `mentioned_files`。
- 唯一 basename 匹配保留 Aider `get_file_mentions()` 的保守语义：basename 必须按原始大小写精确出现，且在当前 indexed Python 文件集合中唯一命中，才映射为 repo-relative path。
- 唯一 stem 匹配参考 Aider `get_ident_filename_matches()`：使用 `mentioned_idents` 做大小写不敏感匹配，ident 与 stem 长度至少为 5；MapCode 额外要求当前 indexed Python 文件集合中只有一个候选，多个候选时不得猜测。
- path component 不得直接或通过唯一候选规则进入 `mentioned_files`。目录样式片段、普通 path component 和只命中路径前缀的 token 只进入 path ident matching。
- 所有输出必须是 repo-relative path，并按用户消息首次命中顺序稳定去重。

Aider 原生 `get_file_mentions()` 直接比较 repo-relative path，不识别 absolute path 或 `./` 前缀；MapCode 对这两类准确路径执行受 repo root 和当前 SymbolIndex 约束的规范化匹配，是为了让用户明确给出的完整文件路径稳定进入 Branch A，不扩大文件范围。

3. effective_symbol_hits：

- 由 mentioned_idents ∩ symbol_index.all_defs 得到。
- 用于 Branch 判断、trace/evidence、eval，并用于将精确命中的 DefinitionRecord 固定加入 focused map 候选前缀。
- 不直接参与 PPR seed 构造。

4. path_ident_hits：

- 为每个当前 indexed Python 文件构造 path match terms：repo-relative path components、basename 和 stem。
- path match terms 内部按 `term.lower()` 建立 normalized lowercase key；每个 key 映射到命中该 term 的全部 indexed Python 文件。
- 每个 `mentioned_idents` 使用 `ident.lower()` 与 normalized path match terms 做大小写不敏感比较；命中时，保留原始 ident 到 `path_ident_hits`，并在 `path_ident_hit_files[ident]` 中记录全部匹配文件。
- `path_ident_hits` 按 `mentioned_idents` 的首次出现顺序稳定去重；`path_ident_hit_files` 的 key 顺序必须与其一致，每个文件 tuple 按 repo-relative path 升序排列。
- lowercase 只用于 path ident matching。`mentioned_idents`、`path_ident_hits`、`path_ident_hit_files` key 和文件级 evidence 均保留 prompt 中的原始 ident；symbol matching 与 symbol edge boost 继续按原始大小写精确匹配。
- path ident 命中不是目录 scope、不是文件硬过滤、不是 `mentioned_files`、不是 `focus_fnames`、不是 prior-read/read_file 授权。
- 同一个 path ident 可以命中多个文件；这些文件可在 ranking 阶段形成 path personalization，不需要唯一候选。
- 同一文件命中一个或多个 path ident 时，只获得一次 path personalization contribution。
- `path_ident_hits` 用于 Branch 判断、trace/evidence、eval 和 path personalization；它本身不额外触发 ident edge boost，symbol edge boost 始终只由完整 `mentioned_idents` 与 def/ref 图匹配决定。

5. Branch 判断：

   \- specific = mentioned_files 非空 OR effective_symbol_hits 非空 OR path_ident_hits 非空。
   \- fuzzy = mentioned_files 为空 AND effective_symbol_hits 为空 AND path_ident_hits 为空。

Branch 判断使用有效命中结果，不使用 `mentioned_idents` 是否为空作为条件。自然语言请求通常会产生 idents；只有这些 idents 实际命中 symbol 或 indexed file path terms 时，才阻止请求进入 Branch B。


### 7.6 `graph_ranker.py`

图模型：

```text
referencer file --identifier--> definer file
```

v1 固定采用以下 Aider-style 启发式：

- mentioned identifier 边权重增强，匹配 ident 的引用边权重 ×10。
- 长 structured identifier 边权重增强。
- private identifier 与在多个文件中定义的 common identifier 边权重降权。
- focus personalization file 出站引用边增强，明确文件 focus seed 引用外部 def 的边 ×50。
- path ident 命中的文件获得 Aider-style path personalization contribution，但不获得 focus outbound boost。
- 不得通过 Aider chat_fnames 参数路径实现 focus_fnames。
- 所有边权重修改必须发生在 PageRank 前。
- 高频引用平方根降权。
- 将 focus personalization contribution 与 path personalization contribution 合并为 PPR personalization weights，整体提升对应文件 rank。
- PageRank / Personalized PageRank。

这些机制作用层不同，不要混为一谈：

- symbol ident 命中只对对应 def/ref 图边执行 `IDENT_BOOST`。
- structured/private/common symbol 启发式与 prompt 是否命中无关，并与 `IDENT_BOOST` 组合相乘。
- 明确文件 focus 命中产生 focus personalization contribution，并允许对该文件出站引用边执行 `FOCUS_OUTBOUND_BOOST`。
- path ident 命中只产生 path personalization contribution；它不把文件升级为 focus，也不执行 `FOCUS_OUTBOUND_BOOST`。

**`effective_symbol_hits` 的用途边界**：用于 trace 记录信号质量、branch A/B 判断依据、eval 评估输入，并保证精确命中的 DefinitionRecord 固定进入 focused map 候选前缀；它不改变 PageRank/PPR 分数。ranking 始终使用完整 `mentioned_idents`，对齐 Aider 行为。

Ranking 输入语义：

- ident_boost_inputs 必须使用完整 mentioned_idents。
- Branch A 的 focus_fnames 只来自 `analysis.mentioned_files`。
- Branch B confirmed focused 的 focus_fnames 只来自 `selection_decision.confirmed_files`。
- `focus_fnames` 保留调用方要求聚焦的文件；它不包含 path ident 命中的文件。
- `GraphRanker` 在图构建完成后、PageRank/PPR 前，从 `focus_fnames` 过滤得到 `focus_personalization_files`，保持 `focus_fnames` 输入顺序稳定去重。
- `GraphRanker` 从 `analysis.path_ident_hit_files` 的全部匹配文件稳定合并并过滤实际文件图节点，得到按 repo-relative path 升序排列的 `path_personalization_files`；不得重新执行大小写敏感 path matching。
- `personalization_files` 是 `focus_personalization_files` 与 `path_personalization_files` 的稳定有序并集；并集顺序先保留 focus 输入顺序，再追加尚未出现的 path personalization files。
- 每个 focus personalization file 获得一次 focus contribution；每个 path personalization file 获得一次 path contribution；同时属于两者的文件获得两次 contribution。所有 contribution 在调用 PPR 前归一化为 personalization weights，不写死额外常量。
- personalization_files 为空时：
  - 不应用 focus outbound boost。
  - `personalization=None`。
  - PageRank 使用普通 PageRank。
  - mentioned_idents 的 ident boost 仍然生效。
- `RankingEvidence.algorithm` 按实际执行算法填写，而不是按调用的 `generate_broad()` / `generate_focused()` 方法名填写。

执行顺序：

1. 从 SymbolIndex 构建文件级 def/ref 图。
2. 为每个 identifier 计算 Aider-style symbol multiplier，并在 PageRank 前应用到对应引用边。
3. 从 focus_fnames 过滤得到实际存在于文件图节点的 focus_personalization_files。
4. 从 path_ident_hit_files 合并匹配文件并过滤实际文件图节点，得到 path_personalization_files。
5. 合并两类 contribution，生成 personalization_files 和归一化 personalization weights。
6. 仅对 focus_personalization_files 的出站引用边应用 outbound_focus_boost。
7. 在完成所有边权重修改后调用 PageRank / Personalized PageRank。
8. 基于 PageRank 结果计算 Aider-style `(definer_file, identifier)` definition group rank，并生成 top_ranked_files 和 top_rank_contributors。
9. 按 definition group rank 排序现有 `DefinitionRecord`，并将该序列与文件级排序结果交给 ContextRenderer 做预算渲染。
10. focused generation 将 `effective_symbol_hits` 对应的 DefinitionRecord 固定置于渲染候选前缀；即使 symbol 没有引用边或 PageRank 分数较低，也必须优先进入 focused map。

definition group rank 生成后禁止二次加权或伪造排序原因。

固定参数和公式：

```text
base_edge_weight = sqrt(reference_count)
symbol_multiplier = 1.0
identifier 按原始大小写精确命中 mentioned_idents 时：symbol_multiplier *= IDENT_BOOST
identifier 是长度至少 STRUCTURED_IDENT_MIN_LENGTH 的 snake_case、kebab-case 或同时含大小写字母的 camelCase/PascalCase 时：symbol_multiplier *= STRUCTURED_IDENT_BOOST
identifier 以 "_" 开头时：symbol_multiplier *= PRIVATE_IDENT_PENALTY
identifier 的不同 defining files 数量大于 COMMON_IDENT_DEFINER_THRESHOLD 时：symbol_multiplier *= COMMON_IDENT_PENALTY
edge_weight = base_edge_weight * symbol_multiplier
source file 位于 focus_personalization_files 时：edge_weight *= FOCUS_OUTBOUND_BOOST
focus_personalization_files 中的文件获得一次 focus contribution
path_personalization_files 中的文件获得一次 path contribution
各文件 contribution 总和归一化为 PPR personalization weights
edge_contribution = node_pagerank[source_file] * edge_weight / source_file_total_outbound_weight
definition_group_rank[(definer_file, identifier)] = 指向该 (definer_file, identifier) 的 edge_contribution 之和
definition_rank_sum[file] = 该文件所有不同 identifier 的 definition_group_rank 之和
PageRank / PPR 失败或图为空时：DefinitionRecord 按 (path, line, name, kind) 升序稳定排序，definition_rank_sum=0.0
```

上述 multiplier 按列出的顺序组合相乘，不互斥。`snake_case` / `kebab-case` 要求 identifier 分别包含 `_` / `-` 且至少包含一个字母；camelCase/PascalCase 要求同时包含大写与小写字母。common identifier 的 defining file 数量按 `definitions_by_symbol[identifier]` 中不同 repo-relative path 计数，不按 DefinitionRecord 数量计数。

`RankContributorEvidence.weight_multiplier` 是相对于 `sqrt(reference_count)` 的最终组合乘数，包含 symbol multiplier 和可能的 `FOCUS_OUTBOUND_BOOST`。`weight_reason_codes` 按稳定顺序记录实际应用的规则，只允许使用：

```text
prompt_ident_boost
structured_ident_boost
private_ident_penalty
common_ident_penalty
focus_outbound_boost
```

未应用任何 multiplier 时，`weight_multiplier=1.0` 且 `weight_reason_codes=()`。

MapCode v1.3 不移植 Aider 为无引用 definition 添加的 `0.1` 自环；精确 symbol hit 仍通过 focused map 候选前缀保证可见性。本取舍避免在本阶段扩大图拓扑语义。

path-ident-only 流程示例：

```text
prompt = "请你分析一下 pico/目录下的文件都起到了什么作用？"
mentioned_idents = ("请你分析一下", "pico", "目录下的文件都起到了什么作用")
mentioned_files = ()
effective_symbol_hits = ()

# 假设以下三个 indexed Python 文件的 normalized path terms 命中 "pico"，
# 但只有前两个文件实际存在于本次文件图节点。
path_ident_hits = ("pico",)
path_ident_hit_files = {
    "pico": (
        "pico/core/runtime.py",
        "pico/core/session.py",
        "pico/tools/standalone.py",
    )
}
branch = "specific"
focus_fnames = ()
focus_personalization_files = ()
path_personalization_files = (
    "pico/core/runtime.py",
    "pico/core/session.py",
)
personalization_files = (
    "pico/core/runtime.py",
    "pico/core/session.py",
)
algorithm = "personalized_pagerank"
```

该流程不调用 Branch B selector，不把 `pico/` 变成目录 scope，也不把三个命中文件写入 `focus_fnames`。`pico/tools/standalone.py` 保留在 PromptAnalysis 匹配证据中，但由于不是本次文件图节点，不进入 PPR personalization。

`definition_group_rank` 是 GraphRanker 内部计算结果，不新增 DTO。`DefinitionRecord` 先按其 `(path, name)` 对应的 definition group rank 降序排列；group rank 相同时按 `(path, name)` 升序，同一 group 内按 `(line, kind)` 升序。一个文件中同一 identifier 存在多个 `DefinitionRecord` 时，它们共享同一个 group 排序位置，但 `definition_rank_sum` 对该 identifier 只累计一次。

所有参数只从 `config.py` 读取。fallback 使用现有索引文件集合，不引入新的检索来源。

算法记录规则：

- `personalization_files` 非空且 PPR 成功：`algorithm="personalized_pagerank"`。
- `personalization_files` 为空且 PageRank 成功：`algorithm="pagerank"`。
- PageRank/PPR 失败或图为空：`algorithm="stable_path_fallback"`。

MapCode 必须新增：

- 保留 `node_pagerank`，也就是文件节点的 PageRank 原始分数。
- 保留入选 reason codes。
- 保留 top rank contributors。
- 将 focus 排名语义与“已完整进入 prompt，因此排除”语义拆开。

### 7.7 `context_renderer.py`

职责：

- 使用 `grep_ast.TreeContext`，或迁移为 MapCode-owned 的等价 TreeContext 风格逻辑，根据排序后的 `tuple[DefinitionRecord, ...]` 渲染结构摘要。
- 无 definition 的文件按文件级排序结果输出路径或记录 omission。
- 对排序后的 DefinitionRecord 前缀进行预算选择。
- 返回渲染文本和渲染统计。
- focus 文件不得因为 Aider `chat_fnames` 语义被排除。

不保证所有 focus definition 都能完整进入 map。

当预算不足时必须：

- 至少保留 focus 文件路径。
- 尽量保留顶层结构。
- 在 evidence 中记录 `focus_truncated=true`。
- 记录 omitted symbols / files。

### 7.8 `evidence.py`

职责：

- 在 ranking/rendering 过程中同步组装 `MapContextEvidence`。
- 证据不得从最终 repo map 字符串反推。
- 输出 trace/report 可引用的轻量摘要。
- `MapContextEvidence.analysis.path_ident_hit_files` 保存 path ident 到全部 indexed file matches 的全局映射；文件级 `prompt_path_ident_hits` 只是它的反向投影，不能替代该全局证据。

RenderedFileEvidence / OmittedFileEvidence 的共同分数字段：

- node_pagerank：nx.pagerank() 原始文件级分数。
- pagerank_norm：用于人类展示的归一化分数，最高文件接近 1.0。
- definition_rank_sum：该文件所有不同 identifier 的 Aider-style definition group rank 之和；同一 identifier 的多个 DefinitionRecord 不重复累计。
- reason_codes：文件入选或遗漏原因。
- prompt_symbol_hits：prompt 命中且定义在该文件内的符号。
- prompt_path_ident_hits：从 `PromptAnalysis.path_ident_hit_files` 反向投影得到、实际命中该文件 path terms 的原始 `path_ident_hits`；path ident 命中文件时 reason codes 必须包含稳定的 `path_ident_match`。
- top_rank_contributors：对该文件排名贡献最大的引用边，最多 top-3；每项必须记录最终 `weight_multiplier` 和稳定的 `weight_reason_codes`，使 Aider-style symbol multiplier 与 focus outbound boost 可审计。

差异字段：

- `RenderedFileEvidence.render_rank` 是最终进入候选 map body 的 1-based 顺序。
- `RenderedFileEvidence.rendered_symbols` 是最终进入候选 map body 的符号。
- `OmittedFileEvidence.omission_reason` 说明文件未进入候选 map body 的直接原因。

不得再使用含义不明确的 `selected_files` 或 `included_by_budget` 同时表达 rendered 与 omitted 状态。

v1 不定义 selection_score。

### 7.9 `engine.py`

MapEngine 对外接口：

```python
class MapEngine:
    def ensure_index(self) -> IndexStatus:
        ...

    def analyze(self, prompt: str) -> PromptAnalysis:
        ...

    def generate_broad(self, analysis: PromptAnalysis) -> MapResult:
        ...

    def build_selector_catalog(self) -> SelectorCandidateCatalog:
        ...

    def generate_focused(
        self,
        analysis: PromptAnalysis,
        focus_fnames: tuple[str, ...],
    ) -> MapResult:
        ...
```

`ensure_index()` 完成或复用 lazy SymbolIndex，并返回当前 snapshot 的只读 `IndexStatus`。它不执行 prompt analysis、ranking 或 rendering。`analyze()` 和 `generate_*()` 只使用该已就绪 snapshot，不再次触发索引构建。

`generate_broad()` 只用于无有效文件、symbol 或 path ident 命中的 Branch B，使用标准 PageRank，不使用 personalization，不使用 focus outbound boost。
`generate_focused()` 始终返回 `mode="focused"`。它在 `personalization_files` 非空时使用 Personalized PageRank；当 focus 与 path ident 均未形成有效图节点导致 `personalization_files=()` 时，使用标准 PageRank，但 mentioned_idents 的 ident boost 仍然生效。
`build_selector_catalog()` 从同一个已就绪 snapshot 生成全量 `candidate_paths` 和预算受控的 definition 摘要 `rendered_text`，不重新构建索引，不读取完整源码。

调用路径与结果语义固定为：

| 调用路径 | `MapResult.mode` | `focus_fnames` | `personalization_files` | 成功时 `RankingEvidence.algorithm` |
|---|---|---|---|---|
| `generate_broad()` | `broad` | `()` | `()` | `pagerank` |
| `generate_focused()` 且存在有效 focus 或 path personalization | `focused` | 只保存明确文件 focus | 两类 personalization files 的并集 | `personalized_pagerank` |
| `generate_focused()` 且无有效 personalization，包括 symbol-only Branch A | `focused` | 可能为空或非空 | `()` | `pagerank` |

任一路径发生 PageRank/PPR 失败或图为空时，`RankingEvidence.algorithm="stable_path_fallback"`，但 `MapResult.mode` 不改变。

MapEngine 禁止调用：

- `complete_model()` 或任意 selector LLM。
- `runtime.ask_user()`。
- `runtime.emit_trace()`。
- RunStore。
- CLI/TUI 输出。

---

## 八、focused / broad 双预算

### 8.1 两套独立 token budget

```text
focused_map_budget_tokens = 4,096
broad_map_budget_tokens   = 8,192
```

语义：

- `broad`：Branch B selector 前的仓库导航视图。
- `focused`：围绕 prompt hits 或 confirmed focus files 的执行导航视图。
- Branch B 首先使用 broad 的 8,192 token budget；用户确认建议文件并重新生成 focused map 后，active map 改用 focused 的 4,096 token budget。

### 8.2 固定预算选择规则

```python
effective_map_budget_tokens = (
    BROAD_MAP_BUDGET_TOKENS
    if mode == "broad"
    else FOCUSED_MAP_BUDGET_TOKENS
)
```

是否存在 `focus_fnames` 不改变 focused budget。broad map 使用更大的预算尽量覆盖仓库结构；focused map 使用更小预算集中展示确认后的相关文件和符号。

### 8.3 正确的完整性承诺

不得写成“focus 文件一定完整显示”。

v1 的承诺是：

- focus 文件拥有更高 ranking 权重。
- focused map 始终使用 4,096 token budget。
- focus 文件至少保留路径和尽可能多的顶层结构。
- 精确命中的 DefinitionRecord 固定进入 focused map 候选前缀。
- 仍无法容纳时显式记录截断。

### 8.4 双层预算职责

- MapEngine 使用独立 token budget 完成 repo map 结构选择；v1 使用 `ceil(chars / 4)` 作为稳定估算。
- Pico `ContextManager.total_budget` 继续表示原有 base prompt 的字符级软目标，不等同于最终模型输入硬上限。
- `ModelRequestBudget` 提供最终模型输入硬上限。repo map 使用独立预算，但该预算必须从最终模型输入预算中预留，而不是在 base prompt 之外额外叠加。
- ContextManager 不再次裁剪 repo map body；它只在为完整 repo map section 预留空间后，缩减 base prompt 的原有 section。

预算公式：

```python
active_repo_map_reservation_tokens = estimate_tokens(rendered_repo_map_section)

base_prompt_budget_tokens = max(
    0,
    model_input_budget_tokens
    - active_repo_map_reservation_tokens
    - prompt_safety_margin_tokens,
)

effective_base_prompt_budget_chars = min(
    context_manager.total_budget,
    base_prompt_budget_tokens * 4,
)
```

控制规则：

- 先渲染候选 repo map section，再计算 `active_repo_map_reservation_tokens`。该预留必须包含固定导航安全契约、动态状态行、fallback notice 和 map body，而不只是 MapEngine `repo_map_text`。
- base prompt 的 section reduction 和 auto-compaction 只作用于 prefix、memory、skills、relevant_memory、history 和 current_request，但触发阈值必须使用 `base_prompt_budget_tokens`。
- 若 base prompt 在完成 reduction 和允许的 auto-compaction 后仍无法与当前 repo map 同时容纳，Engine 必须清除 `current_map_context` 并重建无 repo map prompt。
- 若无 repo map prompt 仍超过 `ModelRequestBudget`，Engine/runtime 不得发起 provider 调用；必须在本地以超预算错误结束或走 Pico 统一的预请求失败路径。MapCode 不把这种情况伪装成正常模型调用失败。

两层记录各自负责的事实：

- MapEngine `RenderingEvidence`：`target_tokens`、`target_chars`、`used_chars`、`estimated_tokens`、`focus_truncated` 和 `budget_reduction_applied`。
- ContextManager `RepoMapSectionRender`：候选 map body 字符数、实际注入 map body 字符数、完整 section 字符数、hash、是否发生 base prompt reduction 和 omission reason。
- `PromptBuildResult.metadata`：`model_input_budget_tokens`、`prompt_safety_margin_tokens`、`active_repo_map_reservation_tokens`、`base_prompt_budget_tokens`、`estimated_request_tokens`、`request_over_budget` 和预算来源。

不得使用同一个模糊字段同时表示两层裁剪。

---

## 九、Pico Runtime 集成

### 9.1 Runtime 初始化

`Pico.__init__()` 只装配对象，不生成 repo map：

```python
self.map_engine: MapEngine | None = ...
self.map_context_coordinator: MapContextCoordinator | None = ...
self.model_request_budget: ModelRequestBudget = ...
self.current_map_context: MapContextResult | None = None
```

初始化约束：

- feature flag 默认关闭。
- 初始化可加载 cache metadata，但不扫描仓库。
- 不触发 PageRank 或 TreeContext。
- 不创建独立 SessionManager。
- `map_engine_initialized` 只表示对象就绪。
- `model_request_budget` 在 runtime 初始化时一次性解析并挂到 agent 上，供 ContextManager、selector 路径和主模型调用共用。它不是 MapEngine feature 的一部分，因此 child runtime 即使关闭 MapEngine 也仍保留该预算对象。

### 9.2 Engine 接入点

首次 preparation 必须发生在：

```text
Engine.run_turn()
  -> 创建 TaskState / run 目录
  -> emit run_started
  -> 执行 MapContext preparation
  -> 首次 _build_prompt_and_metadata(..., purpose="main_model")
```

禁止在 `ContextManager.build()` 或 `_build_prompt_and_metadata()` 内触发 MapEngine，因为：

- auto-compaction 可能重复调用 prompt build。
- prompt preview、evaluation、step-limit summary 或其他辅助路径可能调用 prompt build。
- MapEngine 会被意外重复运行。

### 9.3 Engine 控制流伪代码

```python
analysis = coordinator.analyze_turn(task_state, user_message)

if analysis.branch == "specific":
    result = coordinator.prepare_specific(task_state, analysis)
else:
    broad = coordinator.prepare_broad(task_state, analysis)
    yield reporter.broad_ready(broad)  # selector LLM 前展示

    if not self._can_confirm_focus():
        decision = SelectionDecision.broad_fallback("one_shot_no_confirm")
    else:
        selector_catalog = coordinator.build_selector_catalog(task_state)
        selector_request = build_selector_request(
            original_user_message=user_message,
            broad_result=broad,
            selector_catalog=selector_catalog,
        )
        if self._selector_request_over_budget(selector_request):
            decision = SelectionDecision.broad_fallback(
                "selector_request_over_budget",
            )
        else:
            runtime.emit_trace(task_state, "map_selector_requested", ...)
            task_state.selector_model_calls += 1
            selector_raw = self._call_selector_model(selector_request)
            allowed_files = frozenset(selector_request.visible_paths)
            selector_result = parse_selector_output(selector_raw, allowed_files)
            valid_files = selector_result.suggested_files

            if not valid_files:
                decision = SelectionDecision.broad_fallback(
                    "selector_no_valid_files",
                    selector_result,
                )
            else:
                answer = runtime.ask_user(
                    question=render_selector_confirmation(valid_files),
                    choices=["接受全部建议", "使用 broad map"],
                )
                decision = SelectionDecision.from_single_choice(selector_result, answer)
                if decision.confirmed_files:
                    runtime.emit_trace(task_state, "map_focus_confirmed", ...)

    result = coordinator.prepare_fuzzy(task_state, broad, decision)

runtime.current_map_context = result
```

伪代码接口约束：

- `self._call_selector_model(selector_request: SelectorModelRequest) -> str` 是 Engine 内部适配点，必须复用 Pico 已有模型 provider/runtime 调用链；它不表示新增模型客户端或新的公共 runtime API。
- selector 调用必须保留 `SelectorModelRequest.system_prompt` 与 `SelectorModelRequest.user_prompt` 的 provider role 边界。provider adapter 将前者映射到协议原生 system/instructions 字段，将后者映射到 user role；不得把两段文本拼接成一个 user prompt 冒充 system prompt。
- 主模型调用继续使用 Pico 已有的单组合 prompt 路径；selector 的双角色请求能力不得改变主模型 prompt 的 provider role 或 `repo-map-001.txt` 证据语义。
- v1.3 selector 暂时复用主 Pico loop 使用的同一模型；后续可以替换为更轻量模型。selector 是否降低总 token 成本必须通过 retrieval eval 验证，不作为 v1.3 的确定性承诺。
- `self._can_confirm_focus() -> bool` 是 Engine 对 Pico 现有 one-shot / 交互能力状态的内部读取，不为 MapEngine 新建第二套交互状态。
- `selector_catalog` 与 broad map 复用同一个已就绪 SymbolIndex snapshot。selector user prompt 包含原始 user message、broad map 和预算受控的 `SelectorCandidateCatalog.rendered_text`，因此可以建议 broad map 中未出现、但在 catalog 可见目录里出现的文件。
- `allowed_files = frozenset(selector_request.visible_paths)`。selector 只允许返回 Broad Repo Map 或 Selector Candidate Catalog 中实际展示的 repo-relative path。
- `self._selector_request_over_budget()` 必须计算完整 `SelectorModelRequest.system_prompt + user_prompt` 的保守估算输入 token 和安全余量。只有完整 selector request 通过 `ModelRequestBudget` 检查后，Engine 才发送 `map_selector_requested`、递增 `selector_model_calls` 并真正发起 selector 调用。
- `selector_request_over_budget` 是正常 broad fallback，不是 `map_context_failed`。
- `render_selector_confirmation(valid_files) -> str` 是 `map_selector.py` 的纯渲染 helper，不调用用户交互。
- `reporter.broad_ready(broad)` 只将已有 evidence 转换为用户事件，不产生新的检索事实。

首次 `purpose="main_model"` 调用完成可能的 auto-compaction、返回实际用于首次主模型请求的 `PromptBuildResult` 并完成 artifact 落盘后，Engine 必须使用 Coordinator 返回的 finalized 对象替换 prepared 对象：

```python
result = coordinator.finalize_prompt_context(...)
runtime.current_map_context = result
```

### 9.4 `current_map_context` 生命周期

`current_map_context` 保存 `MapContextResult` 对象。

正确生命周期：

```text
run 开始前：None
preparation 成功：MapContextResult
首次 main_model build 后：用相同 map_context_id 的 finalized 对象替换 prepared 对象
后续主模型/tool loop：复用 finalized 对象
run completed / failed / stopped：清理为 None
```

要求：

- 不写入 session。
- 不跨 run 恢复。
- 不与 child runtime 共享。
- 所有退出路径必须通过统一清理逻辑执行。

建议为 `Engine.run_turn()` 增加 `try/finally` 或统一 finalize helper，避免多个结束分支遗漏清理。

### 9.5 child runtime

当前 child runtime 会继承父 runtime 的 feature flags。实现阶段必须显式覆盖：

```python
child_feature_flags["map_engine"] = False
```

原因：

- 避免重复扫描。
- 避免重复 selector。
- 避免父子 run 共享或混淆当前 map。

---

## 十、MapContextCoordinator

### 10.1 接口

```python
class MapContextCoordinator:
    def analyze_turn(
        self,
        task_state: TaskState,
        user_message: str,
    ) -> PromptAnalysis:
        ...

    def prepare_specific(
        self,
        task_state: TaskState,
        analysis: PromptAnalysis,
    ) -> MapContextResult:
        ...

    def prepare_broad(
        self,
        task_state: TaskState,
        analysis: PromptAnalysis,
    ) -> MapResult:
        ...

    def build_selector_catalog(
        self,
        task_state: TaskState,
    ) -> SelectorCandidateCatalog:
        ...

    def prepare_fuzzy(
        self,
        task_state: TaskState,
        broad_result: MapResult,
        decision: SelectionDecision,
    ) -> MapContextResult:
        ...

    def finalize_prompt_context(
        self,
        task_state: TaskState,
        result: MapContextResult,
        repo_map_render: RepoMapSectionRender,
    ) -> MapContextResult:
        ...
```

接口参数来源：

- `analyze_turn()` 先调用 `MapEngine.ensure_index()`，使用返回的 `IndexStatus` 发出 `map_index_status`，再调用 `MapEngine.analyze()` 并发出 `map_prompt_analyzed`；`task_state` 不传给 MapEngine。
- `prepare_specific()` 固定调用 `MapEngine.generate_focused(analysis, analysis.mentioned_files)`。
- `prepare_broad()` 返回 selector 前展示和 fallback 可复用的 broad `MapResult`。
- `build_selector_catalog()` 调用 `MapEngine.build_selector_catalog()`，返回同一 index snapshot 的全量来源路径集合和预算受控候选目录文本，供 Engine 构造 `SelectorModelRequest`；selector 输出只使用 request 中的 `visible_paths` 校验。
- `prepare_fuzzy()` 只消费 Engine 已形成的 `SelectionDecision`：有 `confirmed_files` 时生成 focused map，否则复用 broad map 形成 fallback result；它返回 prepared `MapContextResult`，不写最终 prompt artifact。
- `prepare_broad()` 与后续 `prepare_fuzzy()` 复用同一个已就绪 SymbolIndex snapshot，不把 Branch B 的两次 map rendering 实现成两次索引构建。
- `finalize_prompt_context()` 只接收首次主模型 build 返回的 build-local `RepoMapSectionRender`，不接收松散 `dict`，也不从完整 prompt 反推注入事实；只有该方法返回 finalized `MapContextResult`。

### 10.2 preparation 与实际注入 artifact

MapEngine 生成的是已经受独立 token budget 约束的候选 repo map；ContextManager 负责将其与导航安全契约组合为实际注入 section，并在同一 `ModelRequestBudget` 下为完整 repo map section 预留输入空间后缩减 base prompt。

因此 run artifact 必须在首次 `purpose="main_model"` 调用完成可能的 auto-compaction、最终 prompt section 确定后写入：

```text
MapEngine 生成 MapResult
  -> current_map_context 保存 MapContextResult
  -> ContextManager.build(..., purpose="main_model") 返回 PromptBuildResult
  -> Engine 将该 build-local repo_map_render 传给 Coordinator.finalize_prompt_context()
  -> 先写 repo-map-001.txt 并取得稳定路径
  -> 使用该路径组装并写 map-evidence-001.json
  -> Coordinator 取得 evidence artifact 路径并返回 finalized MapContextResult
  -> emit map_generated
  -> 终端打印最终摘要
  -> Engine 发起主模型调用
```

`ContextManager` 不得保留 `last_map_section_render`。每次 build 的 `repo_map_render` 必须随 `PromptBuildResult` 返回，避免 prompt preview、evaluation、step-limit summary 或后续主模型 build 覆盖首次主模型实际注入事实。

`finalize_prompt_context()` 返回与 prepared 对象具有相同 `map_context_id` 的 finalized `MapContextResult`。由于 DTO 不可变，Engine 使用 finalized 新对象替换 runtime 中的 prepared 对象；后续主模型 retry/tool loop 只复用 finalized 对象。

一个 run 内后续 `purpose="main_model"` build 不重复写完整 repo map artifact，只在 `prompt_built` trace 中记录该次 build 的 `repo_map_render` hash、字符数和 omission 状态。

### 10.3 故障处理

Coordinator 捕获 MapEngine 增强层异常：

- 调用 `runtime.emit_trace(..., "map_context_failed", ...)`。
- 设置 `current_map_context=None`。
- Pico 原有主执行链继续。
- 错误信息进入 trace 前必须经过 runtime redaction。

首次主模型 prompt build 完成后，如果 `finalize_prompt_context()` 在写入
`repo-map-001.txt`、组装或写入 `map-evidence-001.json`、更新 run 摘要的任一必要步骤失败，
则该次已经构建的含 repo map prompt 不得发送给主模型。处理流程固定为：

```text
首次 purpose="main_model" build 已返回含 repo map 的 PromptBuildResult
  -> finalize_prompt_context() 发生异常
  -> emit map_context_failed
  -> 设置 current_map_context=None
  -> 将已写入但未形成完整证据链的部分 artifact 视为无效，不在 TaskState / trace / report 中引用
  -> 重新执行 purpose="main_model" prompt build
  -> 因 current_map_context=None，不注入 repo_map section
  -> 使用无 repo map 的 prompt 继续 Pico 原主模型调用
```

该降级同时满足：

- MapEngine 检索或 preparation 失败时，Pico 原流程继续。
- repo map 注入证据落盘失败时，Pico 原流程继续。
- 主模型不得使用无法由完整 `repo-map-001.txt`、`map-evidence-001.json` 和对应 run 摘要共同证明的 repo map。
- 证据落盘失败后的无 repo map 重建不重新运行 MapEngine，不重新调用 selector，也不重新询问用户。

---

## 十一、Branch A 与 Branch B

### 11.1 Branch A：specific prompt

触发：

```text
mentioned_files 非空 OR effective_symbol_hits 非空 OR path_ident_hits 非空
```

流程：

```text
Engine 收到 PromptAnalysis
  -> Coordinator.prepare_specific()
  -> MapEngine.generate_focused()
  -> 返回 MapContextResult
  -> ContextManager 注入
  -> artifact / trace / terminal
  -> 主模型执行
```

Branch A 不调用 selector，不询问用户。

### 11.2 Branch B：fuzzy prompt

触发：

```text
mentioned_files 为空 AND effective_symbol_hits 为空 AND path_ident_hits 为空
```

交互模式流程：

```text
Coordinator.prepare_broad()
  -> broad map 简要状态在 selector LLM 前展示
  -> Coordinator.build_selector_catalog() 生成同一 index snapshot 的全量来源路径集合和预算受控候选目录
  -> Engine 构造 SelectorModelRequest
  ->    system_prompt = 固定 JSON 输出和文件选择规则
  ->    user_prompt = original_user_message + broad map + SelectorCandidateCatalog.rendered_text
  ->    visible_paths = broad.rendered_files + selector_catalog.rendered_paths 的稳定并集
  -> [完整 selector request 超过 ModelRequestBudget]
  ->    不发送 map_selector_requested
  ->    不递增 selector_model_calls
  ->    直接 selector_request_over_budget broad fallback
  -> [完整 selector request 通过预算门禁]
  ->    Engine emit map_selector_requested
  ->    Engine 使用 provider-level system role + user role 发起 selector 模型调用
  ->    MapSelector 校验输出
  ->    无有效建议：直接 broad fallback
  -> 有有效建议：Engine 调 runtime.ask_user(["接受全部建议", "使用 broad map"])
  -> 接受全部建议：Engine emit map_focus_confirmed
  -> Coordinator.prepare_fuzzy()
  -> 接受全部有效建议：MapEngine.generate_focused()
  -> 否则：broad map fallback
```

交互确认约束：

- TUI / CLI 只展示“接受全部建议 / 使用 broad map”两个选项。
- “接受全部建议”确认所有路径校验后的建议文件；v1 不允许调整多个文件或部分接受。
- 用户选择 broad map、Esc 取消、返回未知值、selector 无有效文件或 selector 请求超预算时均使用 broad fallback。
- 所有正常 broad fallback 都复用 `original_user_message` 与已生成的 broad map 进入首次主模型调用；不重新调用 selector、不重新询问用户、不要求用户重新输入 prompt。
- `map_focus_confirmed` 只在用户选择“接受全部建议”且 `confirmed_files` 非空时发送。

one-shot / 不具备交互确认能力：

- 不自动采纳 selector 建议。
- v1 直接使用 broad map fallback。
- 不发送 `map_focus_confirmed`。

### 11.3 模型调用统计

selector call 不计入 `TaskState.attempts`，因为 `attempts` 是主 Agent loop 的停止控制计数。当前 Pico 在进入每次主循环、执行 prompt build 前就递增 `TaskState.attempts`，因此它不等同于实际发起的主模型调用次数。

调用统计固定为：

```text
TaskState.attempts              = 主 Agent loop 已进入的次数
TaskState.main_model_calls      = Engine 主循环实际调用 complete_model() 的次数
TaskState.selector_model_calls  = selector 模型实际调用次数
total_model_calls               = TaskState.main_model_calls + TaskState.selector_model_calls
```

约束：

- `TaskState.main_model_calls` 在 Engine 主循环每次实际调用 `complete_model()` 前递增；若 prompt build、MapContext finalization 或其他前置步骤失败且未调用模型，则不递增。
- Engine 主循环显式重试并再次调用 `complete_model()` 时，`TaskState.main_model_calls` 再递增；provider client 内部未暴露给 Engine 的透明重试不单独计数。
- `TaskState.selector_model_calls` 在每次实际发起 selector 模型调用前递增，且 v1 每个 run 最大为 1。
- 本节 `total_model_calls` 只统计 MapCode 主执行与 selector 路径，不统计 `step_limit_summary`、evaluation 等辅助 purpose 的模型调用。
- report、trace 和测试统一使用 `TaskState.main_model_calls` 与 `TaskState.selector_model_calls` 作为 run 级调用计数事实源。

---

## 十二、ContextManager 集成

### 12.1 读取对象

ContextManager 读取：

```python
map_context = getattr(self.agent, "current_map_context", None)
model_request_budget = getattr(self.agent, "model_request_budget")
repo_map_text = map_context.active_result.repo_map_text if map_context else ""
```

不得只假设 `current_map_context` 是字符串，也不得在 ContextManager 内自行推断 provider 输入上限。

### 12.2 Prompt purpose 与返回契约

```python
def ContextManager.build(
    self,
    user_message: str,
    *,
    purpose: PromptPurpose,
) -> PromptBuildResult:
    ...

def Pico._build_prompt_and_metadata(
    self,
    user_message: str,
    *,
    purpose: PromptPurpose,
) -> PromptBuildResult:
    ...
```

runtime wrapper 与 `ContextManager.build()` 必须显式接收并传递同一个 `purpose`，且均不提供默认值。各调用目的的行为固定为：

| purpose | 注入 repo map | 允许 auto-compaction | 可用于写 `repo-map-001.txt` |
|---|---:|---:|---:|
| `main_model` | 是 | 是 | 仅首次调用最终返回并用于主模型请求的 result 是 |
| `prompt_preview` | 是，保证 preview 与主模型 section 规则一致 | 否 | 否 |
| `evaluation` | 否 | 否 | 否 |
| `step_limit_summary` | 否 | 否 | 否 |

约束：

- `prompt_preview` 可以渲染 repo map，但只用于展示，不产生 artifact 或覆盖主模型注入 evidence。
- `evaluation` 与 `step_limit_summary` 不注入 repo map，避免辅助 prompt 消耗预算或误用导航上下文。
- auto-compaction 只允许由 `purpose="main_model"` 触发，辅助 prompt build 不修改 session。
- `main_model` 与 `prompt_preview` 在存在 MapContext 时都先渲染完整 repo map section，并据此计算 `active_repo_map_reservation_tokens`。
- Pico 原有 base prompt 超预算判断和 auto-compaction 判断必须基于“为当前 repo map 预留空间后的有效 base prompt 预算”，而不是忽略 repo map section。
- Engine 只能使用首次 `purpose="main_model"` 调用完成可能的 auto-compaction 后，最终返回并用于主模型请求的 build-local `repo_map_render` 写入 artifact。
- Pico runtime 中所有 `_build_prompt_and_metadata()` 包装入口，包括现有 `prompt()` 和 `prompt_metadata()` helper，都必须显式传递 `purpose`；不得保留无 `purpose` 的旧调用路径。

### 12.3 Section 顺序

`repo_map` 必须插入 Pico 现有上下文 section 与 `current_request` 之间：

```text
Pico 现有 prefix / memory / history 等上下文 section
  -> repo_map
  -> current_request
```

实现时保留 Pico 当前已有 section key 和相对顺序，只新增 `repo_map` 的插入位置，不为满足本文档而虚构或重命名 Pico 内部 section。

### 12.4 repo_map section

Pico 当前主模型路径将 prefix、memory、history、repo map 和 current request 拼成单个组合 prompt，不为 repo map 导航契约单独发送 provider-level system message。Branch B selector 的 `SelectorModelRequest.system_prompt` 是独立例外，不改变主模型调用路径。

因此 v1 将下列文本定义为 repo_map section 内的固定导航安全契约。它在功能上承担类似 Aider `repo_content_prefix` 的上下文边界说明，但不修改 Pico 全局 prefix：

```text
[Repo Map - Navigation Context Only]
The following repo map shows selected code-structure signatures only, not complete or authoritative file contents.
Use it only to decide which files and symbols to inspect.
Do not treat repo map snippets as authoritative full file content.
Before relying on implementation details or editing any existing file, use read_file to inspect the complete current source.
Repo map content does not satisfy Pico's prior-read or freshness requirement.

Branch: {branch}
Mode: {focused | broad_fallback}
Focus files (read these first): {focus_files_display}
{fallback_notice_if_present}

{active_repo_map_text}
```

固定契约语义：

- `Focus files (read these first)` 是读取优先级提示，不是已读取证明，也不是编辑授权。
- Branch A focused、Branch B confirmed focused 和 Branch B broad fallback 均使用这一份模板；差异只来自 `MapContextResult` 派生出的动态状态与 active result。
- Branch A 和 Branch B confirmed focused 使用 `Mode: focused`，不显示 fallback notice。
- broad fallback 使用 `Mode: broad_fallback`，并显示：

```text
No specific focus files were confirmed. Broad repository context is provided for navigation.
```

- 不使用 `No specific files identified`。selector 可能已经建议了文件，只是 one-shot、校验失败、用户拒绝或确认结果为空，未形成 confirmed focus。
- MapContext 不存在或整体失败时，整个 repo_map section 均不注入。
- 导航安全契约用于降低模型误用 repo map 的概率；Pico 已有 `ToolPolicyChecker` 对 `patch_file` / 已存在文件 `write_file` 的 fresh-read 校验仍是强制安全边界。`ToolPolicyChecker` 定义于 `pico/pico/core/tool_policy.py`。两者互补，不能互相替代。

### 12.5 模板所有权与数据来源

```text
MapContextResult
  ├─ branch / stage
  ├─ active_result.focus_fnames
  ├─ active_result.repo_map_text
  └─ selection_decision.fallback_reason
      -> map_context_prompt.py 生成固定契约和动态状态行
      -> ContextManager 注入，并为完整 repo map section 预留输入空间后缩减 base prompt
```

约束：

- `map_context_prompt.py` 只生成文本，不调用模型、不读取仓库、不写 trace/artifact。
- fallback notice 由结构化 `SelectionDecision` 派生，不能通过搜索 repo map 文本猜测。
- `{focus_files_display}` 只由 `active_result.focus_fnames` 格式化生成：非空时按原顺序使用 `, ` 连接，空 tuple 时固定为 `none`。
- `{active_repo_map_text}` 只接受 `active_result.repo_map_text`。不得使用 `focused_repo_map_string`，因为 Branch B broad fallback 的 active result 是 broad map。
- `focus_fnames_list` 不作为模板变量；`focus_fnames` 是结构化 tuple，`focus_files_display` 才是注入文本。
- 每次 build 的注入 section 摘要进入该次 `PromptBuildResult.metadata.map_context`；只有首次 `purpose="main_model"` 的完整 section 进入 run artifact。

### 12.6 独立预算与注入规则

- `current_request` 永不裁剪。
- `repo_map` 采用“固定契约 + MapEngine 独立 token budget 已裁剪 map body”结构。
- 固定导航安全契约、Branch、Mode、Focus files 和 fallback notice 必须原子保留。
- MapEngine 在 broad 8,192 / focused 4,096 token budget 内完成 head clip；ContextManager 不再次 head clip repo map body，也不复用 history 的 tail clip。
- ContextManager 先渲染完整 repo map section，再以 `ModelRequestBudget` 计算 `active_repo_map_reservation_tokens`，随后仅缩减 Pico 原有 section。
- base prompt 的 reduction order 继续沿用 Pico 既有 section 顺序；repo map section 本身不进入该 reduction order。
- 若预留 repo map 后 base prompt 仍无法容纳，`RepoMapSectionRender.section_rendered=False`，`omission_reason="base_prompt_cannot_fit_with_repo_map_reservation"`，并由 Engine 清除 `current_map_context` 后重建无 repo map prompt。
- 每次 build 的实际注入信息进入该次 `PromptBuildResult.metadata.map_context`，包括 contract 是否注入、fallback notice 是否注入、map body 字符数、是否发生 base prompt reduction、预算来源和 omission reason；只有首次 `purpose="main_model"` 的注入信息进入 evidence artifact。

---

## 十三、Trace 事件体系

### 13.1 写入规则

所有 run 级 MapEngine 事件统一调用：

```python
runtime.emit_trace(task_state, event_name, payload)
```

禁止新增旁路 TraceWriter。

Map 事件应通过 Pico 现有事件 phase 注册点归入 retrieval phase。若当前实现没有集中映射表，则在既有事件标准化路径中扩展，不为 MapEngine 新增旁路 phase 体系。

### 13.2 v1 事件

| 事件 | 触发时机 | 关键事实 |
|---|---|---|
| `map_engine_initialized` | runtime 初始化完成，尚无 run id | feature、预算、cache metadata 状态 |
| `map_index_status` | 当前 run 使用的 index snapshot 就绪 | cache、files、defs/refs、snapshot id |
| `map_prompt_analyzed` | PromptAnalysis 完成 | branch、files、idents、symbol hits、path ident hits、path ident hit files |
| `map_context_ranked` | PageRank/PPR 完成 | algorithm、focus、focus/path personalization files、top files、contributors 及其 weight multiplier/reason codes |
| `map_context_selected` | TreeContext 与预算选择完成 | rendered、omitted、budget、truncation |
| `map_selector_requested` | Engine 发起 selector 模型调用前 | index snapshot id、candidate path count、rendered path count、input chars、call number |
| `map_focus_confirmed` | 用户选择“接受全部建议”且 confirmed files 非空后 | suggested、invalid、confirmed |
| `map_generated` | 首次主模型实际注入 artifact 写入后 | artifact paths、final rendered hash/chars |
| `map_context_failed` | MapContext 增强层异常 | error type、redacted message、fallback |

事件语义约束：

- `map_index_status` 由 Coordinator 在 `MapEngine.ensure_index()` 成功返回后、调用 `MapEngine.analyze()` 与任意 `generate_*()` 前发出。
- 当前 run 后续使用的 `MapContextEvidence.index_snapshot_id` 和 `cache_status` 必须分别等于该次 `IndexStatus.index_snapshot_id` 和 `cache_status`。
- `ensure_index()` 未形成可用 snapshot 时不发出 `map_index_status`；Coordinator 发出 `map_context_failed` 并按 MapContext 整体失败路径降级。
- `map_prompt_analyzed` 必须记录 `mentioned_files`、`mentioned_idents`、`effective_symbol_hits`、`path_ident_hits`、`path_ident_hit_files` 和最终 branch，保证 Branch A/B 决策及 path ident 的全部 indexed file 命中范围可以从 trace 复盘。
- `map_selector_requested` 不能表示 selector 已完成。
- `map_focus_confirmed` 只在用户选择“接受全部建议”且 `confirmed_files` 非空后发送。
- 正常 broad fallback 不等于 `map_context_failed`。
- selector 输出、fallback 和确认事实进入最终 evidence artifact。

---

## 十四、Artifact、Report 与终端输出

### 14.1 路径统一

持久 MapEngine 状态：

```text
.pico/map_engine/index.json
.pico/map_engine/cache.meta.json
.pico/map_engine/repo-map-latest.md
```

`repo-map-latest.md` 是最近一次成功生成的 MapEngine 候选 map body 便捷快照，可能是 broad 或 focused。它不包含当前 run 的导航安全契约、动态状态行或 fallback notice，不触发额外 map 生成，不作为任何 run 的证据，也不能替代 run artifact。

当前 run artifacts：

```text
.pico/runs/<run_id>/artifacts/repo-map-001.txt
.pico/runs/<run_id>/artifacts/map-evidence-001.json
```

全项目只允许使用本节定义的统一路径和命名，不保留旧目录、旧快照名或旧 evidence artifact 名。

`repo-map-001.txt` 保存首次 `purpose="main_model"` 调用完成可能的 base prompt auto-compaction 后，最终返回并用于主模型请求的完整 repo_map section。因此它包含完整导航安全契约、动态状态行、可选 fallback notice和 MapEngine 独立 token budget 已裁剪的 map body。

若当前 run 最终因 repo map 预留导致必须降级为无 repo map prompt，则 `repo-map-001.txt` 保存该次首次主模型请求实际使用的空注入结果，并由 evidence 记录 omission reason。

同一 run 内后续主模型调用不重复写完整 repo map artifact；每次后续 build 的实际 `repo_map_render` hash、字符数和 omission 状态写入对应 `prompt_built` trace。

### 14.2 单一事实层级

```text
map-evidence-001.json   完整检索与控制决策事实源
trace.jsonl             有序事件摘要 + artifact path
report.json             run 最终汇总
terminal / TUI          evidence 的用户可见投影
```

终端输出不得产生 trace/artifact 中不存在的新事实。

### 14.3 RunStore 扩展

当前 RunStore 只有 text artifact 写入能力。v1 增加：

```python
def write_json_artifact(self, task_state, stem: str, payload: dict) -> Path:
    ...
```

要求：

- 复用原子 JSON 写入。
- 使用 UTF-8。
- 自动编号。
- 返回 repo-relative 或可进入 report 的稳定路径。

### 14.4 `map-evidence-001.json`

至少包含：

```json
{
  "schema_version": "mapcode.map-evidence.v1",
  "map_context_id": "mapctx_...",
  "run_id": "run_...",
  "branch": "specific",
  "stage": "execution",
  "index_snapshot_id": "sha256:...",
  "analysis": {},
  "broad_result": null,
  "active_result": {
    "mode": "focused",
    "focus_fnames": [],
    "rendered_files": [],
    "rendered_symbols": [],
    "evidence": {
      "schema_version": "mapcode.map-engine.v1",
      "index_snapshot_id": "sha256:...",
      "analysis": {},
      "ranking": {},
      "rendering": {},
      "rendered_files": [],
      "omitted_files": [],
      "cache_status": {},
      "duration_ms": 0
    }
  },
  "selection_decision": null,
  "prompt_injection": {
    "section_rendered": true,
    "contract_rendered": true,
    "fallback_notice_rendered": false,
    "map_body_raw_chars": 0,
    "map_body_rendered_chars": 0,
    "section_rendered_chars": 0,
    "section_rendered_hash": "sha256:...",
    "base_prompt_reduction_applied": false,
    "omission_reason": null
  },
  "repo_map_artifact_path": ".pico/runs/.../artifacts/repo-map-001.txt"
}
```

该 JSON 是 `MapEvidenceArtifact` 的序列化结果。`run_id`、selection 和 prompt injection 属于 run 级 envelope；MapEngine 确定性事实保留在各结果的 `evidence` 中。JSON 不保存完整 repo map 文本，也不保存自身 artifact path。

### 14.5 report

`report.json` 保存轻量汇总，不复制完整 evidence：

```json
{
  "map_context": {
    "enabled": true,
    "map_context_id": "mapctx_...",
    "branch": "specific",
    "stage": "execution",
    "focus_fnames": [],
    "rendered_files": [],
    "index_snapshot_id": "sha256:...",
    "selector_model_calls": 0,
    "repo_map_artifact_path": "...",
    "evidence_artifact_path": "..."
  },
  "model_calls": {
    "main_model_calls": 0,
    "selector_model_calls": 0,
    "total_model_calls": 0
  }
}
```

不要只依赖 `last_prompt_metadata` 保存完整 evidence，因为它会被后续主模型调用覆盖。首次主模型注入事实以 `repo-map-001.txt` 和 `map-evidence-001.json` 为准，后续主模型 build 以对应 `prompt_built` trace 摘要为准。

### 14.6 终端打印时机

必须在对应 LLM 调用前打印：

| 场景 | 打印时机 |
|---|---|
| 首次 lazy index cache miss | index 完成后 |
| Branch A final focused map | 主模型调用前 |
| Branch B broad map | selector LLM 调用前 |
| Branch B confirmed focused map | 主模型调用前 |
| Branch B broad fallback | 主模型调用前 |
| MapEngine 失败 | Pico 原主模型调用前 |

`MapEngineConsoleReporter` 只返回可展示文本或用户事件 payload。CLI/TUI 决定如何显示。

MapEngineConsoleReporter 最低展示内容：

- index 状态：cache hit/miss、files、defs/refs、graph stats。
- turn retrieval：branch、mode、focus、focus/path personalization files、symbol hits、path ident hits、path ident matched file count、top ranked files、rendered/omitted、budget，以及在 artifact 已落盘后可用的 evidence path。
- Branch B：selector 前展示 broad retrieval；confirmed 后展示 focused retrieval；fallback 时展示 broad fallback。
- Branch B selector 前的 broad 状态发生在 run artifact 落盘前，因此不得展示或伪造尚不存在的 evidence path。
- 终端不得展示 evidence 中不存在的推理理由。

---

## 十五、Aider 能力迁移策略

### 15.1 基本规则

禁止：

```python
from aider.repomap import RepoMap
import aider
```

允许：

- 阅读和参考本地 `aider/` 源码。
- 将必要算法、query 文件和小段实现复制到 `features/map_engine/` 后改造成 MapEngine-owned code。
- 抽象 Aider Repo Map 的行为并编写 MapCode 自有接口。
- 使用 Aider 已依赖的通用第三方库。

### 15.2 不整体复制 `RepoMap`

Aider `RepoMap` 深度耦合：

- Aider IO / Spinner。
- Aider Coder 和 chat/read-only 文件语义。
- 模型 tokenizer。
- Aider cache 路径和 refresh 策略。
- prompt prefix。
- `filter_important_files()`。

MapCode 应迁移能力，而不是迁移产品控制流。

`filter_important_files()` 在此只作为 Aider 产品耦合示例；v1 不迁移该能力，不因此将 README、配置或其他非 Python 文件加入 repo map。

### 15.3 可迁移能力

- tree-sitter Definition / Reference query。
- 文件级引用图。
- PageRank/PPR 启发式。
- TreeContext 风格渲染。
- 按 definition group rank 排序后的 DefinitionRecord 前缀预算选择。
- tag/tree/map 分层缓存思想。

### 15.4 必须修正的 Aider 语义

- 不直接继承 Aider `chat_fnames` 的混合语义。
- Aider path component personalization 使用大小写敏感集合交集；MapCode path ident matching 改用 normalized lowercase key，同时在 evidence 中保留原始 ident。
- v1.3 不迁移 Aider 为无引用 definition 添加的 `0.1` 自环，继续通过 focused map 候选前缀保证精确 symbol hit 可见。
- focus 文件不因排除语义从 map 消失。
- ranking 分数与入选原因必须保留。
- mtime-only cache 增加 parser/query/schema version。
- MapEngine 输出结构化结果，不只输出字符串。
- MapEngine 独立 token budget 与 Pico base prompt budget 分开记录。

v1 只实现 `focus_fnames`，不实现 `files_already_in_prompt`。未来如需表达“文件全文已进入 prompt”，必须使用独立字段；不得复用 `focus_fnames`，也不得复刻 Aider“chat 文件已完整进入 prompt，因此从 repo map 排除”的控制语义。

### 15.5 依赖与许可证

可继续使用的通用依赖包括：

- `networkx`
- `grep-ast`
- `tree-sitter-language-pack`
- `tree-sitter`
- `diskcache`
- `pygments`

从 Aider 复制或修改代码时，必须遵守 Apache License 2.0 的许可证和归属要求，并标注修改。

---

## 十六、错误处理与降级

MapEngine 是增强层，不能成为 Pico 主执行链路的单点故障。

| 错误 | v1 行为 | 证据 |
|---|---|---|
| 单文件解析失败 | 跳过该文件并继续 | skipped files |
| cache 读取失败 | 降级为重建或内存状态 | `map_index_status` |
| cache 写入失败 | 当前 run 继续，不阻断主模型 | `map_index_status` |
| 空图 / PageRank 失败 | 退化为稳定文件列表 | fallback reason |
| TreeContext 单文件失败 | 输出路径或跳过文件 | rendering evidence |
| selector 请求超出 `ModelRequestBudget` | 不发起 selector，直接 broad fallback | `selector_request_over_budget` |
| selector JSON 无效 | `selector_no_valid_files` broad fallback，具体错误保存在 `SelectorResult.parse_error` | selection decision |
| selector 无有效文件 | broad map fallback | `selector_no_valid_files` |
| 用户选择 broad map | broad map fallback | `user_selected_broad` |
| 用户 Esc 取消 | broad map fallback | `user_cancelled` |
| ask_user 返回未知值 | broad map fallback | `invalid_confirmation` |
| one-shot 无交互 | broad map fallback | `one_shot_no_confirm` |
| 非 Git workspace / Git 文件枚举失败 | MapEngine 不可用，Pico 原流程继续 | `map_context_failed` |
| tracked 文件已从工作树删除 | 跳过该文件并继续 | skipped files |
| 整体 MapContext preparation 异常 | `current_map_context=None`，Pico 原流程继续 | `map_context_failed` |
| 预留 repo map 后 base prompt 无法容纳 | 清除 `current_map_context`，重建无 repo map prompt | repo map omission reason |
| 无 repo map prompt 仍超出 `ModelRequestBudget` | 不发起 provider 调用，走本地超预算失败路径 | prompt metadata / trace |

所有 broad map fallback 在主模型 repo_map section 中使用同一条准确状态提示：

```text
No specific focus files were confirmed. Broad repository context is provided for navigation.
```

具体 fallback reason 继续保存在 evidence / trace / report 中，不把内部错误细节拼入主模型提示。

所有错误进入 trace/report/artifact 前必须经过 runtime redaction。

---

## 十七、测试策略

### 17.1 MapEngine 单元测试

- Python fixture repo 可提取预期 def/ref。
- tracked Python 文件进入索引。
- staged 新 Python 文件进入索引。
- untracked Python 文件不进入索引。
- tracked 非代码文件不进入索引。
- tracked 但已从工作树删除的文件被跳过并记录。
- 非 Git workspace 或 Git 文件枚举失败时不回退为递归扫描。
- 从仓库子目录启动时仍以 Git repo root 为边界。
- `.pico/`、虚拟环境、缓存和生成目录即使被误提交也不进入索引。
- cache hit 时未修改文件不重复解析。
- parser/query/schema version 变化使缓存失效。
- Git index 只枚举路径，解析内容来自 working tree。
- 相同有序文件元数据和版本生成相同 `index_snapshot_id`。
- repo-relative、`./` repo-relative 和 repo-root 内 absolute path 只有规范化后精确命中当前 indexed Python 文件时才进入 `mentioned_files`；目录、路径前缀和 repo root 外路径不得进入。
- 同一准确文件分别通过 repo-relative path、`./` path 和 repo-root 内 absolute path 提及时，均规范化为同一个 repo-relative `mentioned_files` 值。
- basename 只有按原始大小写唯一命中时才进入 `mentioned_files`；stem 使用大小写不敏感且长度至少为 5 的匹配，并仅在唯一候选时进入 `mentioned_files`。
- 重复 basename、重复 stem、长度小于 5 的 stem、repo root 外 absolute path、目录路径和仅路径前缀均不产生错误 `mentioned_files`。
- path component 不进入 `mentioned_files`；目录样式片段被切成 ident，并在命中 indexed file path terms 时形成 `path_ident_hits`。
- path ident matching 使用 normalized lowercase path term key，大小写不同的 prompt ident 可以命中同一 path term，而 `path_ident_hits`、`path_ident_hit_files` key 和文件级 evidence 保留原始 ident。
- `path_ident_hit_files` 的 key 顺序与 `path_ident_hits` 一致，value 包含全部匹配 indexed Python 文件并按 repo-relative path 排序；它不受文件图节点或渲染预算过滤。
- 多文件 path ident 命中不猜测 focus 文件、不形成目录 scope；只有 `path_ident_hit_files` value 中实际存在于文件图的稳定有序并集进入 `path_personalization_files`。
- 同一文件命中多个 path ident 或同一 normalized lowercase ident 的多个原始大小写变体时，只获得一次 path personalization contribution。
- Branch A 的 `focus_fnames` 只来自 `mentioned_files`；symbol-only 与 path-ident-only Branch A 的 `focus_fnames=()`。
- symbol-only Branch A 返回 `MapResult.mode="focused"`，成功时 `personalization_files=()` 且 `RankingEvidence.algorithm="pagerank"`。
- path-ident-only Branch A 返回 `MapResult.mode="focused"`；存在有效 `path_personalization_files` 时使用 Personalized PageRank，但不执行 `FOCUS_OUTBOUND_BOOST`。
- `focus_fnames` 中未形成文件图节点的文件不会进入 `focus_personalization_files`；focus 和 path ident 均未形成有效 personalization 时，focused generation 使用标准 PageRank。
- Aider-style symbol multiplier 在 PageRank 前组合应用：prompt ident boost、structured ident boost、private ident penalty 和 common ident penalty 均有独立覆盖，并验证 symbol matching 保持大小写敏感。
- structured ident 的长度边界 `>= STRUCTURED_IDENT_MIN_LENGTH`、common ident 的 defining file 边界 `> COMMON_IDENT_DEFINER_THRESHOLD` 与 Aider 语义一致，并覆盖 multiplier 组合相乘场景。
- 只有 focus personalization files 的出站边增强发生在 PageRank 前；path personalization files 不获得该增强。
- `RankContributorEvidence` 准确记录相对于 `sqrt(reference_count)` 的最终 `weight_multiplier` 和稳定 `weight_reason_codes`，包括与 `FOCUS_OUTBOUND_BOOST` 的组合结果。
- `RenderedFileEvidence` / `OmittedFileEvidence` 从 `path_ident_hit_files` 准确反向记录每个文件的原始 `prompt_path_ident_hits` 和 `path_ident_match` reason code。
- PageRank/PPR 参数、边权公式和空图稳定路径 fallback 符合 `config.py` 与本 SPEC。
- `top_ranked_files` 在预算渲染前生成，数量不超过 `TOP_RANKED_FILES_LIMIT`，排序和稳定 fallback 规则符合本 SPEC。
- `GraphRanker` 向 `ContextRenderer` 提供排序后的现有 `DefinitionRecord` 和文件级排序结果，不新增无公式依据的 definition rank DTO。
- `ensure_index()` 返回的 `IndexStatus` 计数、cache 状态和 `index_snapshot_id` 与当前已就绪 SymbolIndex 一致。
- focus 文件不会被输出排除。
- 精确命中的 DefinitionRecord 即使没有引用边，也固定进入 focused map 候选前缀。
- ranking result 保留分数、reason codes 和 contributors。
- focused / broad 预算选择正确。
- broad map 使用 8,192 token budget，focused map 使用 4,096 token budget。
- focus 仍无法容纳时记录 truncation。
- selector catalog 的 `candidate_paths` 包含当前 SymbolIndex snapshot 的全部已索引 Python 文件路径，且按 repo-relative path 升序稳定排序。
- selector catalog 的 `rendered_text` 受 `SELECTOR_CATALOG_MAX_TOKENS`、`SELECTOR_CATALOG_MAX_FILES` 和 `SELECTOR_CATALOG_MAX_DEFS_PER_FILE` 约束。
- `rendered_paths` 始终是 `candidate_paths` 的有序子集。
- 每个文件展示的 DefinitionRecord 按 `(line, name, kind)` 升序稳定排序。

### 17.2 Coordinator 测试

- Branch A 命令只调用 focused generation。
- Branch B `prepare_broad()` 和 `prepare_fuzzy()` 分为两个明确调用。
- Coordinator 不调用模型、不调用 `ask_user()`。
- `analyze_turn()` 不把 `task_state` 传给 MapEngine。
- `analyze_turn()` 按 `ensure_index() -> map_index_status -> analyze() -> map_prompt_analyzed` 顺序执行，且一个 run 只发出一次 `map_index_status`；`map_prompt_analyzed` 包含完整 `path_ident_hit_files`。
- `map_index_status` 使用的 `IndexStatus.index_snapshot_id`、`cache_status` 与后续 `MapContextEvidence` 一致。
- `prepare_specific()` 和 `prepare_fuzzy()` 只返回 prepared `MapContextResult`。
- `finalize_prompt_context()` 只接收 build-local `RepoMapSectionRender`，并返回 finalized `MapContextResult`。
- repo map artifact 先写入，evidence artifact 后写入且 payload 不包含自身路径。
- 所有 map trace 通过 `runtime.emit_trace()`。
- 首次主模型实际注入文本和 evidence 写入当前 run artifact。
- MapEngine 异常时发出 `map_context_failed` 并不中断 Pico。

### 17.3 Engine 集成测试

- 每个 run 只执行一次 MapContext preparation；首次主模型 build 后只用 finalized 对象替换 prepared 对象，不重新运行 MapEngine。
- Branch A 不调用 selector。
- 仅存在 `path_ident_hits` 的 Branch A 不调用 selector，`focus_fnames=()`，并直接使用 path-personalized focused map。
- 只有 `mentioned_files`、`effective_symbol_hits` 和 `path_ident_hits` 均为空时才进入 Branch B。
- Branch B 交互模式由 Engine 调用一次 selector 和一次确认。
- selector 调用使用独立的 provider-level system role 和 user role；主模型调用仍使用 Pico 现有单组合 prompt。
- selector system prompt 固定包含合法 JSON object 输出格式、可见文件限制和渲染后的最大建议文件数；目录样式输入不再由 selector 目录偏好规则承担主路径处理。
- `SelectorModelRequest.user_prompt` 固定包含 `original_user_message`、Broad Repo Map 和 Selector Candidate Catalog 三个分段。
- 完整 `SelectorModelRequest.system_prompt + user_prompt` 参与 `ModelRequestBudget` 门禁。
- `map_selector_requested` 只在 selector 实际调用前发送；selector 请求超预算时不发送。
- selector 请求超预算时不递增 `selector_model_calls`，并形成 `selector_request_over_budget` broad fallback。
- selector 无有效建议时不调用 `ask_user()` 并使用 broad fallback。
- `SelectorModelRequest.visible_paths` 等于 broad map 实际展示路径与 `SelectorCandidateCatalog.rendered_paths` 的稳定并集。
- selector 只接受 `visible_paths` 中的路径，包括未进入 broad map、但实际展示在 Selector Candidate Catalog 中的文件；只存在于 `candidate_paths` 的隐藏路径不得被接受。
- “接受全部建议”确认所有有效建议文件，不包含 invalid files。
- 超过 `MAX_SELECTOR_SUGGESTED_FILES` 的额外有效路径进入 `excess_files`，不进入 `suggested_files`。
- “使用 broad map”、Esc 和未知返回值分别形成准确的 broad fallback reason。
- v1 不支持部分接受、增删或调整建议文件。
- `map_focus_confirmed` 只在“接受全部建议”且 confirmed files 非空后发送。
- one-shot 跳过确认并使用 broad fallback。
- selector 无有效建议或用户选择 broad fallback 时，不重新调用 selector、不重新询问用户、不要求用户重新输入 prompt。
- selector calls 不改变 `TaskState.attempts`。
- prompt build 或 MapContext finalization 在调用主模型前失败时，`TaskState.attempts` 可以增加，但 `main_model_calls` 不增加。
- Engine 主循环每次实际调用 `complete_model()` 前增加 `main_model_calls`；显式主循环重试再次调用时再次增加。
- 若本地已判定无 repo map prompt 仍 `request_over_budget=True`，则不得发送 `model_requested`，也不得调用 provider。
- `total_model_calls = main_model_calls + selector_model_calls`，且 report 使用相同的完整字段名。
- 所有结束路径清理 `current_map_context`。

### 17.4 ContextManager 测试

- feature 禁用时 Pico 原行为不变。
- `current_map_context` 是对象。
- 所有 prompt build 调用点必须显式提供 purpose。
- `main_model` 与 `prompt_preview` 注入 repo map；`evaluation` 与 `step_limit_summary` 不注入。
- 只有 `main_model` 允许 auto-compaction；辅助 prompt build 不修改 session。
- 每次 build 返回独立 `PromptBuildResult.repo_map_render`，ContextManager 不保存 `last_map_section_render`。
- `RepoMapSectionRender` 到 `PromptInjectionEvidence` 的字段映射一致。
- section 未注入时使用空文本稳定 hash，并记录非空 omission reason。
- preview、evaluation、step-limit summary 和后续主模型 build 不覆盖首次主模型注入 evidence。
- repo_map section 顺序正确。
- `purpose` 为 `main_model` 或 `prompt_preview` 且存在 MapContext 时，repo_map section 始终包含完整导航安全契约。
- Branch A focused、Branch B confirmed focused 和 Branch B broad fallback 使用同一份导航契约模板。
- `focus_files_display` 只由 `active_result.focus_fnames` 格式化生成，`active_repo_map_text` 只来自 `active_result.repo_map_text`。
- 导航契约不得使用 `focused_repo_map_string` 或 `focus_fnames_list` 这类与结构化来源或 broad fallback 不一致的模板变量。
- MapContext 不存在时，不注入导航安全契约或空 repo_map section。
- focused 模式不显示 fallback notice。
- broad fallback 显示统一 fallback notice。
- selector 建议存在但用户拒绝时，提示不能错误声称没有识别出文件。
- base prompt reduction 和 auto-compaction 使用“预留 repo map 后的有效 base prompt 预算”而不是忽略 repo_map section。
- ContextManager 不再次 head clip MapEngine 已按独立 token budget 生成的 repo map。
- 预留 repo map 后 base prompt 无法容纳时，`RepoMapSectionRender` 使用稳定 omission reason，Engine 清除 `current_map_context` 并重建无 repo map prompt。
- current request 不裁剪。
- repo map 不写入 `file_summaries`。
- 最终 render metadata 可用于写实际注入 artifact。

### 17.5 Runtime / RunStore 测试

- JSON artifact 原子写入和编号正确。
- artifact 路径符合统一约定。
- `repo-map-001.txt` 只保存首次主模型请求实际使用 prompt 的 repo map 注入 section。
- 后续主模型 build 不重复写完整 repo map artifact，并在 `prompt_built` trace 记录 render hash、字符数和 omission 状态。
- retrieval 事件 phase 正确。
- report 只保存摘要和 artifact path。
- child runtime 强制关闭 MapEngine。
- 无 repo map prompt 仍超出 `ModelRequestBudget` 时，provider 不得被调用。

### 17.6 最小 retrieval eval

固定 Python fixture：

```json
{
  "request": "fix token validation in JWTAuth",
  "ground_truth_files": ["auth.py"]
}
```

v1 评估：

- ground-truth 文件是否进入 rendered files。
- 首个 `read_file` 是否命中 ground-truth。
- 文件、symbol 和 path ident 有效命中率。
- path-ident-only 请求是否进入 Branch A，且不产生 `mentioned_files` 或 `focus_fnames`。
- path ident 使用 normalized lowercase key 后，大小写不同的 prompt ident 是否仍命中 ground-truth 文件，同时 evidence 是否保留原始 ident。
- `path_ident_hit_files` 是否完整记录每个 path ident 命中的 ground-truth indexed files，并能解释其到 `path_personalization_files` 的图节点过滤。
- path ident 命中的 ground-truth 文件是否进入 `path_personalization_files` 和 rendered files。
- top rank contributor 的 multiplier/reason codes 是否准确反映 Aider-style symbol 权重规则。
- broad / focused repo map 使用 token 数。
- 完整 selector request token 数，包含 system prompt 与 user prompt。
- focus truncation。
- selector 调用数。
- broad fallback 比例。
- selector_request_over_budget 比例。

---

## 十八、实施阶段

| 阶段 | 内容 | 门禁 |
|---|---|---|
| Step 0 | 固定文档、目录和 DTO | SPEC / FuncFlow 无冲突 |
| Step 1 | Git tracked Python-only `source_files.py` + `symbol_index.py` + cache | Git 范围、无递归 fallback 和 fixture index 测试通过 |
| Step 2 | `prompt_analyzer.py` + `graph_ranker.py` | Branch 判断与 ranking evidence 测试通过 |
| Step 3 | `context_renderer.py` + 双预算 | broad/focused/truncation 测试通过 |
| Step 4 | `MapEngine` + `MapResult` / `MapContextEvidence` | 纯确定性单元测试通过 |
| Step 5 | `MapContextCoordinator` + RunStore JSON artifact | 无模型/无交互 adapter 测试通过 |
| Step 6 | `map_context_prompt.py` + Engine Branch A + prompt purpose + ContextManager 注入 | 导航安全契约、build-local render 和单 run prepare-once 通过 |
| Step 7 | Engine Branch B `SelectorModelRequest` + provider 双角色 selector + 整组二选一 confirm + fallback | system/user role、可见路径校验、事件顺序、单选语义和调用统计通过 |
| Step 8 | trace/report/terminal + child runtime 禁用 | 证据链一致 |
| Step 9 | retrieval eval | ground-truth 指标可输出 |

### 18.1 架构行数门禁调整政策

Pico 现有架构行数门禁是维护性预警，不是不可修改的固定功能约束。MapEngine 完整接入优先于保持原有行数阈值。

- 新增控制流属于现有模块内聚职责并导致超限时，优先提高 `test_architecture_boundaries.py` 中对应模块的行数门禁，而不是为了迎合原有阈值强行拆分。
- 不允许仅为了通过行数门禁，将连续控制流程强行拆成没有独立职责、复用价值或测试边界的转发模块。
- ranking、selector parsing、prompt rendering、evidence 等具有明确职责和独立测试边界的逻辑仍必须保留在独立模块中，不能全部塞入 `engine.py` 或 `runtime.py`。
- 调整门禁时必须记录受影响模块、增加的职责和调整原因；功能正确性、可读性和控制流完整性优先于原有阈值。

---

## 十九、验收标准

v1 完成必须同时满足：

1. MapEngine 通过 feature flag 启用或禁用。
2. 启动只初始化对象，不立即扫描或生成 repo map。
3. MapEngine 不调用 LLM、不询问用户、不写 trace/RunStore。
4. Engine 拥有 Branch A/B、selector 调用和用户确认编排。
5. Coordinator 只作为确定性 MapEngine 与 Pico runtime 的数据面 adapter。
6. `current_map_context` 保存 `MapContextResult` 对象。
7. 一个 run 内 retry/tool loop 复用同一个 map context。
8. 所有结束路径清理 current map。
9. focused / broad 两套预算生效。
10. broad map 固定使用 8,192 token budget，focused map 固定使用 4,096 token budget。
11. 无法完整容纳 focus 结构时显式记录 truncation。
12. Repo map 只作为导航上下文，不改变 prior-read/edit safety。
13. Pico 后续必须通过 `read_file` 后再编辑。
14. `map_selector_requested`、`map_focus_confirmed`、`map_context_failed` 语义正确。
15. selector模型能正确接收system prompt，prompt中能够将模型自己定位认知为不能修改不能测试专注文件检索。
16. 所有 run 级 map trace 经 `runtime.emit_trace()`。
17. artifact 路径完全符合统一约定。
18. `repo-map-001.txt` 表示首次主模型请求实际使用 prompt 中注入的 repo map section 内容。
19. `map-evidence-001.json` 可回答为什么选择文件、使用什么分数和是否发生裁剪。
20. Branch B broad 状态在 selector LLM 前展示。
21. final focused/fallback 状态在主 LLM 前展示。
22. child runtime 默认禁用 MapEngine。
23. 不存在 `import aider.*`。
24. Pico 原有测试在 MapEngine 禁用时保持通过。
25. 存在 MapContext 时，主模型收到完整 repo map 导航安全契约。
26. broad fallback 显示统一 notice，且不错误声称 selector 没有识别出文件。
27. 导航安全契约不进入 Pico 全局 prefix；MapContext 不存在时不注入。
28. repo map body 不参与原有 section reduction，但完整 repo map section 预留必须计入最终 `ModelRequestBudget`。
29. MapEngine v1 只索引 Git tracked 或 staged、当前存在且未命中 denylist 的 Python 文件。
30. 非代码文件、untracked Python 文件不进入 SymbolIndex、PageRank 或 repo map。
31. 非 Git workspace 或 Git 文件枚举失败时不回退为文件系统递归扫描，Pico 原执行链继续。
32. Branch B 只支持“接受全部建议 / 使用 broad map”，不支持部分接受或调整文件。
33. `map_focus_confirmed` 只在用户接受全部有效建议且 confirmed files 非空时发送。
34. 每个 prompt build 调用点显式提供 purpose；evaluation 和 step-limit summary 不注入 repo map。
35. ContextManager 返回 build-local repo map render，不保存 `last_map_section_render`。
36. 辅助 prompt build 不覆盖首次主模型注入 evidence；后续主模型 build 只在 trace 中记录 render 摘要。
37. symbol-only Branch A 返回 `MapResult.mode="focused"`，但成功时 `RankingEvidence.algorithm="pagerank"`。
38. `focus_fnames` 只记录明确文件 focus；`focus_personalization_files` 是其有效图节点子集，`path_personalization_files` 只来自 path ident 命中，`personalization_files` 是两者实际用于 PPR 的稳定并集。
39. `GraphRanker -> ContextRenderer` 使用现有 `DefinitionRecord` 和文件级排序结果完成渲染，definition group rank 仅作为 GraphRanker 内部排序依据，不新增 definition rank DTO。
40. `prepare_specific()` 和 `prepare_fuzzy()` 返回 prepared `MapContextResult`；只有 `finalize_prompt_context()` 返回 finalized `MapContextResult`。
41. `TaskState.attempts`、`main_model_calls` 和 `selector_model_calls` 按第 11.3 节分别统计，不互相替代。
42. symbol-only Branch A 中精确命中的 DefinitionRecord 即使没有引用边，也固定进入 focused map 候选前缀。
43. Branch B selector 使用固定 system prompt、动态 user prompt 和 `visible_paths`；只接受 broad map 或 `rendered_text` 中实际展示的路径，`candidate_paths` 只证明 catalog 来源属于当前 SymbolIndex snapshot。
44. selector 请求超预算时不实际调用 selector，直接形成 `selector_request_over_budget` broad fallback。
45. 预留 repo map 后若 base prompt 仍无法容纳，Engine 必须清除 `current_map_context` 并重建无 repo map prompt。
46. 无 repo map prompt 仍超出 `ModelRequestBudget` 时，provider 不得被调用。
47. Branch A focused、Branch B confirmed focused 和 Branch B broad fallback 使用同一份主模型 repo_map 导航契约模板。
48. 主模型导航契约使用 `focus_files_display` 和 `active_repo_map_text`，且两者分别只派生自 `active_result.focus_fnames` 和 `active_result.repo_map_text`。
49. 所有正常 broad fallback 复用 `original_user_message` 与已生成 broad map，不重新调用 selector、不重新询问用户、不要求用户重新输入 prompt。
50. PromptAnalyzer 使用 `re.split(r"\W+", text)` 形成稳定去重的 `mentioned_idents`，并分别用于 symbol matching、唯一 stem 匹配和 path ident matching。
51. 目录样式片段不形成 `mentioned_dirs`、`mentioned_files`、`focus_fnames` 或目录过滤；有效 path ident 命中用于 Branch 判断、trace/evidence/eval 和 ranking personalization，不直接形成文件 focus。
52. Branch B 仅在 `mentioned_files`、`effective_symbol_hits` 和 `path_ident_hits` 均为空时触发。
53. path personalization files 不获得 `FOCUS_OUTBOUND_BOOST`，且 trace/evidence/eval 可以区分 focus personalization 与 path personalization。
54. path ident matching 使用 normalized lowercase path term key，evidence 保留原始 ident；`path_ident_hit_files` 完整证明每个 path ident 命中的全部 indexed Python 文件。
55. `path_personalization_files` 只由 `path_ident_hit_files` 中实际存在于文件图的文件构成，`personalization_files` 是 focus/path personalization files 的稳定并集，同一文件每类 contribution 最多一次。
56. Aider-style prompt、structured、private 和 common symbol multiplier 在 PageRank 前组合应用，symbol matching 保持大小写敏感，top rank contributor evidence 可解释最终 multiplier。
57. MapCode v1.3 不添加 Aider 的无引用 definition `0.1` 自环；精确 symbol hit 继续通过 focused map 候选前缀保证可见性。

---

## 二十、关键风险与定稿取舍

### 风险 1：Branch B 增加 LLM 成本和不确定性

取舍：

- 仅 fuzzy prompt 进入 Branch B。
- selector calls 单独统计。
- v1.3 暂时复用主模型，后续允许替换为轻量 selector 模型。
- selector 是否降低总 token 成本由 retrieval eval 验证。
- one-shot 直接 broad fallback。
- 交互模式只允许整组接受所有有效建议，或使用 broad map。
- selector/确认不进入 MapEngine。

### 风险 2：focused budget 仍无法保证完整

取舍：

- 不做绝对完整承诺。
- 保证路径和尽可能多的顶层结构。
- 精确命中的 DefinitionRecord 固定进入 focused map 候选前缀。
- 使用 evidence 记录 truncation。

### 风险 3：MapEngine 原始输出与实际 prompt 内容可能不同

取舍：

- 在首次 `purpose="main_model"` 的 ContextManager 最终渲染后写 run repo-map artifact。
- evidence 同时记录 MapEngine 独立 token budget 和首次主模型实际注入字符数。
- 后续主模型 build 只在 trace 中记录 render 摘要。
- build-local render 随 `PromptBuildResult` 返回，辅助 build 不得覆盖首次主模型注入事实。

### 风险 4：Coordinator 膨胀为第二个 Engine

取舍：

- Branch、selector 和确认只在 Engine。
- selector request builder/parser 使用纯 helper。
- Coordinator 只接受明确命令与决策。

### 风险 5：直接复制 Aider 继承产品耦合

取舍：

- 迁移算法和 query，不整体复制 `RepoMap`。
- 使用 MapCode 自有 DTO、cache 和 evidence。
- 保留许可证归属。
