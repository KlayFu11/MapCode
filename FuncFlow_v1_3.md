# MapCode v1 功能数据流程说明

- 版本：v1.3
- 文档职责：功能流程与数据走向说明
- 范围：单会话、单用户轮次、基础 MapEngine 检索与 Pico 执行闭环
- 当前实现底座：Pico runtime

---

## 一、文档定位

本文档只解释：

- 用户请求如何经过 MapEngine 和 Pico。
- 模块之间传递什么数据。
- Branch A / Branch B 如何流转。
- trace、artifact、report 和终端输出在何时产生。
- 正常、fallback 和失败路径对用户有什么影响。

目录结构、代码文件、接口签名、测试策略和实现阶段查阅 `SPEC_v1_3.md`。

---

## 二、v1 最小心智模型

MapCode v1 是一条“先导航、再执行”的链路：

```text
用户请求
  -> MapEngine 生成仓库导航上下文
  -> Pico 主模型根据导航选择要读取的文件
  -> Pico 使用 read_file 获取完整源码
  -> Pico 执行分析、修改或其他任务
```

其中：

- MapEngine 负责“去哪里看”。
- Pico runtime 负责“如何执行”。
- Repo map 是导航上下文，不是完整源码。
- MapEngine 不授权编辑文件。
- Pico 在依赖或修改文件前仍必须调用 `read_file`等相关代码操作工具。

---

## 三、模块关系

### 3.1 控制面

Engine 是当前 run 的控制面：

- 创建和结束当前 run。
- 判断进入 Branch A 或 Branch B。
- 决定何时调用 selector LLM。
- 决定何时调用用户确认。
- 决定 selector 与主模型请求是否通过 `ModelRequestBudget` 门禁。
- 直接发送由控制决策产生的 `map_selector_requested` 和 `map_focus_confirmed` trace。
- 决定何时进入 Pico 主模型/tool loop。

selector 模型能力和用户交互能力由 runtime/provider 提供，Engine 只负责编排。selector 请求必须保持 provider 原生的 `system` / `user` 角色分离；Pico 主模型仍接收 ContextManager 构造的单一组合 prompt，不新增 provider-level system prompt。
v1.3 selector 暂时复用主 Pico loop 的同一模型，后续可以替换为更轻量模型；是否降低总 token 成本由 retrieval eval 验证。

### 3.2 数据面

`MapContextCoordinator` 是 MapEngine 与 Pico runtime 之间的数据面 adapter：

- 接收 Engine 已经形成的命令或决策。
- 调用 MapEngine。
- 接收 `MapResult` 和 `MapContextEvidence`。
- 写 run artifact。
- 为 MapEngine 确定性处理、artifact 和失败结果调用 `runtime.emit_trace()`。
- 组装当前 run 的 `MapContextResult`。

Coordinator 不决定 Branch、不调用 selector、不询问用户。

### 3.3 确定性检索层

MapEngine 负责：

```text
索引
  -> prompt 信号分析
  -> 图排名
  -> 结构摘要渲染
  -> MapResult + MapContextEvidence
```

MapEngine 不写 trace、不写 RunStore、不调用 LLM、不直接打印终端。

### 3.4 Prompt 与执行层

ContextManager：

- 读取当前 `MapContextResult` 对象。
- 读取 runtime 持有的 `ModelRequestBudget`。
- 根据显式 `PromptPurpose` 决定是否注入 repo map。
- 调用 `map_context_prompt` 将结构化状态渲染为导航安全契约和动态状态行。
- 将 active repo map 注入独立 `repo_map` section。
- 先为完整 repo map section 预留输入空间，再缩减 Pico 原有 base prompt section。
- 返回当前 build 独立的 `PromptBuildResult.repo_map_render`，不保存共享 render 状态。

`map_context_prompt` 不属于 MapEngine，也不修改 Pico 全局 prefix。它只在当前 run 存在 MapContext 时参与主 prompt 组装。

Pico 主模型/tool loop：

- 消费 repo map 导航上下文。
- 决定调用哪些工具。
- 必须通过 `read_file` 获取完整文件。
- 按 Pico 原有审批和 freshness 规则执行修改。

---

## 四、核心数据对象与流向

### 4.1 PromptAnalysis

来源：

```text
用户请求 -> MapEngine prompt analysis -> PromptAnalysis
```

包含：

- prompt 命中的文件。
- prompt 中可用于排名的 identifier。
- index 中实际存在的 symbol hits。
- Branch A / Branch B 判断结果。

`PromptAnalysis` 不保存 focus 文件或 index snapshot id：

- Branch A 的 focus 只来自 `mentioned_files`。
- Branch A 仅命中 symbol 时，focus 为空，完整 `mentioned_idents` 仍用于 ident boost。
- Branch B 的 focus 只来自用户接受后的 `SelectionDecision.confirmed_files`。
- 最终实际 focus 只保存在 `MapResult.focus_fnames`。

### 4.2 MapResult

来源：

```text
PromptAnalysis + focus/budget -> MapEngine -> MapResult
```

包含：

- broad 或 focused repo map 文本。
- 调用方要求聚焦的 `focus_fnames`。
- 实际 TreeContext 渲染的文件和符号。
- 确定性 `MapContextEvidence`。

`MapResult.mode` 表示该结果在 MapContext 控制流中的使用意图，不表示实际执行了 PageRank 还是 Personalized PageRank。实际算法只由 `MapContextEvidence.ranking.algorithm` 表示。

每个结果必须满足：

```text
MapResult.focus_fnames == MapResult.evidence.ranking.focus_fnames
```

### 4.3 MapContextEvidence

它只描述 MapEngine 自己能证明的事实：

- 使用了哪个 index snapshot。
- prompt 命中了什么。
- PageRank/PPR 如何排名。
- 哪些文件和符号进入 map。
- 哪些内容因预算被省略。
- 是否发生 focus truncation。
- cache 和耗时信息。

它不包含 selector、用户确认、run id、artifact path 或终端展示文本。

其中必须区分：

- `focus_fnames`：调用方要求聚焦的文件。
- `personalization_files`：`focus_fnames` 中实际存在于本次文件图节点、并用于 PPR personalization 的有序子集。
- `algorithm`：实际执行的 `pagerank`、`personalized_pagerank` 或 `stable_path_fallback`。
- `node_pagerank`：机器和 eval 使用的原始文件级 PageRank 分数。
- `pagerank_norm`：人类展示使用的归一化分数。
- `DefinitionRecord` 有序序列：`GraphRanker` 按 Aider-style `(definer_file, identifier)` definition group rank 排序后交给 `ContextRenderer`；无 definition 文件使用文件级排序结果，不为单个 definition 建立分数字段。
- `definition_rank_sum`：文件内所有不同 identifier 的 definition group rank 之和，同一 identifier 的多个 DefinitionRecord 不重复累计。
- `prompt_symbol_hits`：prompt 命中且定义在该文件中的符号。
- `rendered_symbols`：最终进入候选 map body 的符号。
- `top_rank_contributors`：对文件排名贡献最大的引用边。
- `top_ranked_files`：预算渲染前排名最高的最多 `TOP_RANKED_FILES_LIMIT=5` 个不同文件。

v1 不定义含义不明确的 `selection_score`。

### 4.4 SelectorCandidateCatalog 与 SelectionDecision

只在 Branch B 出现。

来源：

```text
当前 SymbolIndex snapshot
  -> MapEngine 生成完整 snapshot provenance 路径 + 预算受控 definition 摘要
  -> SelectorCandidateCatalog
  -> Engine 组装 SelectorModelRequest
       system_prompt = 固定 JSON 输出和文件选择约束
       user_prompt = original_user_message + broad repo map + rendered candidate catalog
       visible_paths = stable union(broad rendered files, catalog rendered paths)
  -> runtime/provider 按 system / user 角色调用 selector
  -> selector 输出
  + 对 visible_paths 做路径校验
  + 用户确认或 fallback
  -> Engine
  -> SelectionDecision
```

包含：

- `candidate_paths`：当前 snapshot 中全部已索引 Python 文件路径，只证明候选目录来自当前 snapshot，不表示 selector 看见了这些路径，也不直接作为 selector 输出白名单。
- `rendered_text`：受 `SELECTOR_CATALOG_MAX_TOKENS`、`SELECTOR_CATALOG_MAX_FILES` 和 `SELECTOR_CATALOG_MAX_DEFS_PER_FILE` 约束的候选目录文本。
- `rendered_paths`：实际出现在 `rendered_text` 中的路径，是 `candidate_paths` 的有序子集。
- `SelectorModelRequest.system_prompt`：固定 selector system prompt，要求只返回精确 JSON 对象并限制选择规则。
- `SelectorModelRequest.user_prompt`：按 `[User Request]`、`[Broad Repo Map]`、`[Selector Candidate Catalog]` 三段组装的动态输入。
- `SelectorModelRequest.visible_paths`：`broad_result.rendered_files` 与 `selector_catalog.rendered_paths` 的稳定有序并集，是 selector 输出唯一允许集合。
- 路径校验后保存在 `SelectorResult.suggested_files` 中的有效建议文件。
- 超过 `MAX_SELECTOR_SUGGESTED_FILES` 的额外有效路径进入 `SelectorResult.excess_files`。
- 无效建议路径。
- 用户确认文件。
- 是否使用 broad fallback。
- fallback 原因。

`SelectorModelRequest.system_prompt`、`user_prompt` 的精确文本与 `{max_selector_suggested_files}` 替换规则以 `SPEC_v1_3.md` 第 5.3 节为唯一权威；本 FuncFlow 只描述角色边界、数据来源和流转顺序，避免复制两份 prompt 后产生漂移。

`original_user_message` 表示当前 turn 的原始 `user_message` 输入值，在 selector 和 normal broad fallback 中保持不变；它不是新的 DTO，也不表示要求用户再次输入。

Branch B v1 只允许：

```text
接受全部建议
使用 broad map
```

不支持部分接受、增删或调整 selector 建议文件。fallback reason 固定为：

```text
one_shot_no_confirm
selector_request_over_budget
selector_no_valid_files
user_selected_broad
user_cancelled
invalid_confirmation
```

### 4.5 MapContextResult

来源：

```text
MapResult
  + Branch 信息
  + SelectionDecision
  -> Coordinator
  -> MapContextResult
```

它是当前 run 中供 ContextManager 使用的完整导航对象。

`current_map_context` 保存完整 `MapContextResult` 对象，而不是只保存 repo map 字符串。

它存在两个不可变状态：

- prepared：active result 已确定，但 `prompt_injection` 和两个 artifact path 为空。
- finalized：`finalize_prompt_context()` 根据首次 `purpose="main_model"` 实际注入结果完成 artifact 落盘后返回，`prompt_injection` 和两个 artifact path 均已确定。

`prepare_specific()` 和 `prepare_fuzzy()` 只返回 prepared 对象；只有 `finalize_prompt_context()` 返回 finalized 对象。prepared 与 finalized 使用同一个 `map_context_id`。Branch B 的 broad 与 focused 结果必须复用同一个 `index_snapshot_id`。

关键状态语义：

- Branch A：`branch=specific`、`stage=execution`、active result 为 focused、没有 broad result 和 selection decision。
- Branch B 接受全部建议：`branch=fuzzy`、`stage=execution`、保留 broad result，active result 为 focused。
- Branch B broad fallback：`branch=fuzzy`、`stage=fallback`、active result 复用 broad result。
- Branch A 的 `selector_model_calls=0`；Branch B 实际调用过 selector 时为 1，one-shot fallback 和 `selector_request_over_budget` 为 0。
- `MapContextResult.selector_model_calls` 是 preparation 完成时 `TaskState.selector_model_calls` 的不可变快照。

### 4.6 PromptBuildResult 与 RepoMapSectionRender

来源：

```text
prepared MapContextResult
  + user_message
  + PromptPurpose
  -> ContextManager
  -> PromptBuildResult
```

`PromptBuildResult.repo_map_render` 是当前单次 build 独立的 `RepoMapSectionRender`，记录：

- 实际 section 文本。
- 完整导航安全契约和 fallback notice 是否注入。
- 候选和最终 map body 字符数。
- 完整 section 字符数与 hash。
- 是否完成实际 repo_map section 注入；v1.3 正常路径不执行 ContextManager 二次裁剪。
- 整个 section 未注入时的 omission reason。

ContextManager 不保存 `last_map_section_render` 或其他可被后续 build 覆盖的共享 render 状态。

正常路径完整注入导航安全契约和 MapEngine 已按独立 token budget 生成的 map body；当注入渲染本身失败，或为了满足 `ModelRequestBudget` 必须整段省略 repo map 时，使用 `section_rendered=False`、空文本 SHA-256 hash 和非空 omission reason。

### 4.7 PromptInjectionEvidence 与 MapEvidenceArtifact

首次 `purpose="main_model"` 最终返回并用于主模型请求的 `RepoMapSectionRender`，由 Coordinator 逐字段转换为 `PromptInjectionEvidence`。

```text
MapResult 中的确定性 evidence
  + SelectionDecision
  + PromptInjectionEvidence
  + run / artifact path
  -> MapEvidenceArtifact
  -> map-evidence-001.json
```

`MapEvidenceArtifact` 是 run 级完整证据 envelope；它不复制完整 repo map 文本，也不在自身 payload 中保存自身 artifact path。

---

## 五、完整主流程

本章按一次用户请求的真实时间顺序，展开模块操作、数据对象、事件、artifact 和用户可见输出。后续章节分别解释其中各阶段的规则和边界。

### 5.1 端到端时间线

```text
启动 Pico
  -> 初始化 MapEngine / Coordinator 对象
  -> 等待用户请求
  -> 用户提交请求
  -> Engine 创建 TaskState 和 run 目录
  -> Coordinator 驱动 MapEngine 完成 lazy index / prompt analysis
  -> Engine 选择 Branch A 或 Branch B
  -> Coordinator 取得 active MapResult，组装 prepared MapContextResult
  -> ContextManager 执行首次 purpose="main_model" build，返回 build-local repo_map render
  -> Coordinator 写实际注入 artifact 和 evidence，返回 finalized MapContextResult
  -> [落盘成功] 终端展示最终 repo map 简要状态
  -> [证据落盘失败] 清除 current_map_context，展示失败提示并重建无 repo map prompt
  -> Engine 发起 Pico 主模型调用
  -> Pico 使用 read_file / search / tools 执行任务
  -> run 完成、失败或停止
  -> report 落盘并清理 current_map_context
```

### 5.2 启动阶段详细操作流

```text
启动 Pico runtime
  │
  ├─ runtime 创建 Pico 原有 session / provider / RunStore / event 能力
  │
  ├─ runtime 装配 MapEngine
  │    ├─ 读取 feature flag 和 focused / broad budget
  │    ├─ 可加载 .pico/map_engine/cache.meta.json 的轻量元信息
  │    └─ 不枚举仓库、不解析 AST、不生成 repo map
  │
  ├─ runtime 装配 MapContextCoordinator
  │    └─ 注入 MapEngine、RunStore 和 runtime trace 能力
  │
  ├─ runtime.current_map_context = None
  │
  ├─ SessionEventBus 记录 map_engine_initialized
  │    └─ 只表示对象和配置就绪，不表示 index 已构建
  │
  └─ CLI / TUI 等待用户输入
```

启动阶段的数据状态：

| 数据 | 状态 |
|---|---|
| `current_map_context` | `None` |
| index/cache | 可能存在旧持久数据，但尚未为当前请求校验 |
| run id / TaskState | 尚不存在 |
| repo map | 尚未生成 |
| selector / 主模型调用 | 均未发生 |

### 5.3 公共 preparation 详细操作流

Branch A 和 Branch B 在分支判断前共用以下流程：

```text
用户提交 user_message
  │
  └─ Engine.run_turn()
       │
       ├─ 创建 TaskState
       ├─ 创建 .pico/runs/<run_id>/
       ├─ 保存原始用户请求
       ├─ emit run_started
       │
       └─ Engine 向 Coordinator 发出 analyze_turn 命令
            │
            └─ Coordinator 编排确定性分析
                 │
                 ├─ Coordinator 调 MapEngine 完成 Lazy Index 检查
                 │    ├─ 以 Git repo root 为边界，通过 Git index 枚举 tracked / staged 路径
                 │    ├─ 只保留当前工作树存在、未命中 denylist 的普通 `.py` 文件
                 │    ├─ 不纳入 untracked Python 和非代码文件
                 │    ├─ 非 Git workspace 或 Git 枚举失败时不递归扫描，MapContext 整体降级
                 │    ├─ 校验 .pico/map_engine/cache.meta.json
                 │    ├─ 未变化文件复用 .pico/map_engine/index.json
                 │    ├─ 新增或变化文件重新解析 def / ref
                 │    ├─ 更新当前 index snapshot
                 │    └─ MapEngine 返回 index facts
                 │
                 ├─ Coordinator 根据返回的 index facts
                 │    └─ 调 runtime.emit_trace(map_index_status)
                 │
                 ├─ Coordinator 调 MapEngine 分析 user_message
                 │    ├─ 提取路径 / basename / stem 命中
                 │    ├─ 提取 mentioned identifiers
                 │    ├─ 与 index definitions 对齐
                 │    └─ MapEngine 返回 PromptAnalysis
                 │
                 ├─ Coordinator 根据返回的 PromptAnalysis
                 │    └─ 调 runtime.emit_trace(map_prompt_analyzed)
                 │
                 └─ Coordinator 将 PromptAnalysis 返回 Engine
```

公共 preparation 的数据输出：

```text
PromptAnalysis
  ├─ mentioned_files
  ├─ mentioned_idents
  ├─ effective_symbol_hits
  └─ branch = specific | fuzzy
```

当前 `index_snapshot_id` 由 SymbolIndex 提供，进入 MapContextEvidence、trace、report 和最终 run evidence，不进入 `PromptAnalysis`。

Engine 只读取 `PromptAnalysis.branch` 决定下一条控制路径，不参与文件解析、图排名或 repo map 渲染。

### 5.4 Branch A 完整操作数据流

触发条件：

```text
mentioned_files 非空
OR
effective_symbol_hits 非空
```

完整流程：

```text
Engine 读取 PromptAnalysis(branch=specific)
  │
  └─ Engine 向 Coordinator 发出 prepare_specific 命令
       │
       └─ Coordinator 调 MapEngine 生成 focused map
            │
            ├─ 将 mentioned_files 保存为 focus_fnames
            ├─ 从 focus_fnames 中过滤出实际存在于文件图节点的 personalization_files
            ├─ personalization_files 用于 focus outbound boost 和 PPR personalization
            ├─ 将完整 mentioned_idents 用作 ident edge boost 输入
            ├─ effective_symbol_hits 用于 Branch 判断、trace、evidence、eval，并将精确命中的 DefinitionRecord 固定加入 focused map 候选前缀
            ├─ personalization_files 非空时执行 Personalized PageRank
            ├─ personalization_files 为空时执行标准 PageRank
            ├─ 始终返回 mode=focused；algorithm 记录实际执行算法
            ├─ 产生 ranking facts
            ├─ 生成 top_ranked_files 和排序后的 tuple[DefinitionRecord, ...]
            ├─ 使用固定 focused token budget = 4,096
            ├─ TreeContext 渲染候选 focused repo map
            ├─ 记录 omitted files / truncation / used chars
            ├─ 产生 selection facts
            └─ MapEngine 返回
                 ├─ focused MapResult
                 └─ MapContextEvidence（确定性检索事实）
       │
       ├─ Coordinator 根据返回的 ranking facts
       │    └─ 调 runtime.emit_trace(map_context_ranked)
       ├─ Coordinator 根据返回的 selection facts
       │    └─ 调 runtime.emit_trace(map_context_selected)
       ├─ Coordinator 将 focused MapResult 设为 active result
       ├─ Coordinator 组装 prepared MapContextResult
       │    ├─ branch = specific
       │    ├─ active_result = focused MapResult
       │    ├─ selection_decision = None
       │    └─ artifact / final injection 字段尚未完成
       │
       └─ Engine 设置 runtime.current_map_context = prepared MapContextResult
            └─ 进入“最终注入与 artifact 操作流”
```

Branch A 不调用 selector LLM，也不调用 `runtime.ask_user()`。

### 5.5 Branch B 交互模式完整操作数据流

触发条件：

```text
mentioned_files 为空
AND
effective_symbol_hits 为空
AND
Engine._can_confirm_focus() = True
```

阶段一先生成供 selector 使用的 broad map：

```text
Engine 读取 PromptAnalysis(branch=fuzzy)
  │
  └─ Engine 向 Coordinator 发出 prepare_broad 命令
       │
       └─ Coordinator 调 MapEngine 生成 broad map
            │
            ├─ 对当前 index snapshot 构建全仓引用图
            ├─ focus_fnames=()，personalization_files=()
            ├─ 执行标准 PageRank，不使用 personalization 或 focus outbound boost
            ├─ mode=broad；PageRank 成功时 algorithm=pagerank，失败或空图时 algorithm=stable_path_fallback
            ├─ 产生 broad ranking facts
            ├─ 使用 broad budget 执行 TreeContext 渲染
            │    └─ broad token budget = 8,192
            ├─ 产生 broad selection facts
            └─ MapEngine 返回 broad MapResult + MapContextEvidence
       │
       ├─ Coordinator 根据返回的 broad ranking facts
       │    └─ 调 runtime.emit_trace(map_context_ranked, stage=broad)
       ├─ Coordinator 根据返回的 broad selection facts
       │    └─ 调 runtime.emit_trace(map_context_selected, stage=broad)
       └─ Coordinator 将 broad MapResult 返回 Engine
```

broad map 就绪后，控制权回到 Engine：

```text
Engine 收到 broad MapResult
  │
  ├─ MapEngineConsoleReporter 将 broad evidence 转成展示摘要
  ├─ Engine yield broad_ready 用户事件
  ├─ CLI / TUI 在 selector LLM 前展示 broad 摘要
  │    └─ 此时 artifact 尚未落盘，不展示 evidence artifact path
  │
  ├─ Coordinator 调 MapEngine.build_selector_catalog()
  │    └─ 从同一 SymbolIndex snapshot 生成完整 provenance 路径和预算受控候选目录
  │
  ├─ Engine 构造 SelectorModelRequest
  │    ├─ system_prompt = 固定 JSON 输出和文件选择约束
  │    ├─ user_prompt = [User Request] + [Broad Repo Map] + [Selector Candidate Catalog]
  │    └─ visible_paths = stable union(
  │         broad_result.rendered_files,
  │         selector_catalog.rendered_paths
  │       )
  │
  ├─ [完整 SelectorModelRequest 超过 ModelRequestBudget]
  │    ├─ 不发送 map_selector_requested
  │    ├─ 不递增 TaskState.selector_model_calls
  │    └─ Engine 形成 SelectionDecision.broad_fallback(selector_request_over_budget)
  │
  └─ [完整 SelectorModelRequest 通过预算门禁]
       ├─ Engine 直接调 runtime.emit_trace(map_selector_requested)
       ├─ TaskState.selector_model_calls += 1
       ├─ Engine 使用 runtime/provider 按 system_prompt / user_prompt 角色发起 selector LLM 调用
  │
       ├─ MapSelector helper 解析并校验结构化输出
       │    ├─ 只允许返回 SelectorModelRequest.visible_paths 中存在的 repo-relative path
       │    ├─ 可建议未进入 broad map、但实际出现在 Selector Candidate Catalog 中的文件
       │    ├─ suggested_files（前 `MAX_SELECTOR_SUGGESTED_FILES` 个有效建议）
       │    ├─ excess_files
       │    ├─ invalid_files
       │    └─ reasoning / parse status
       │
       ├─ [suggested_files 非空]
       │    ├─ Engine 调 runtime.ask_user(
       │    │    choices=["接受全部建议", "使用 broad map"]
       │    │  )
       │    ├─ “接受全部建议”
       │    │    ├─ confirmed_files = suggested_files
       │    │    ├─ Engine 直接调 runtime.emit_trace(map_focus_confirmed)
       │    │    └─ Engine 形成 confirmed SelectionDecision
       │    ├─ “使用 broad map”
       │    │    └─ Engine 形成 user_selected_broad fallback
       │    ├─ Esc / 空字符串
       │    │    └─ Engine 形成 user_cancelled fallback
       │    └─ 未知返回值
       │         └─ Engine 形成 invalid_confirmation fallback
       │
       └─ [selector 无法解析或 suggested_files 为空]
            ├─ 不调用 runtime.ask_user()
            └─ Engine 形成 SelectionDecision.broad_fallback(selector_no_valid_files)
```

Branch B v1 不允许用户部分接受、增加、删除或调整建议文件。只要 selector 实际调用过，最终 `SelectionDecision.selector_result` 就保留该次解析和校验结果。selector 没有有效建议或用户拒绝建议时，Engine 直接复用 `original_user_message` 和已经生成的 broad map 继续主模型流程，不重跑 selector、不重新询问用户，也不要求用户重新输入 prompt。

阶段二由 Engine 把已经形成的 `SelectionDecision` 交给 Coordinator：

```text
Engine 向 Coordinator 发出 prepare_fuzzy 命令
  │
  └─ Coordinator 检查 SelectionDecision
       │
       ├─ [confirmed files 非空]
       │    └─ Coordinator 调 MapEngine 生成 focused map
       │         ├─ confirmed files 保存为 focus_fnames
       │         ├─ 从 focus_fnames 中过滤出实际存在于文件图节点的 personalization_files
       │         ├─ personalization_files 用于 focus outbound boost 和 PPR personalization
       │         ├─ 复用 broad map 已使用的 SymbolIndex snapshot，不重新枚举或刷新索引
       │         ├─ 使用固定 focused token budget = 4,096
       │         ├─ personalization_files 非空时执行 PPR，否则执行标准 PageRank
       │         ├─ mode 保持 focused，algorithm 记录实际执行算法
       │         ├─ 使用排序后的 tuple[DefinitionRecord, ...] 执行 TreeContext 渲染
       │         └─ 返回 focused MapResult + MapContextEvidence
       │    ├─ Coordinator 根据返回的 focused ranking facts
       │    │    └─ 调 runtime.emit_trace(map_context_ranked, stage=focused)
       │    ├─ Coordinator 根据返回的 focused selection facts
       │    │    └─ 调 runtime.emit_trace(map_context_selected, stage=focused)
       │    └─ focused MapResult 成为 active result
       │
       └─ [未确认或无有效文件]
            ├─ 不再次运行 focused ranking / rendering
            ├─ broad MapResult 成为 active result
            └─ fallback reason 进入最终 evidence
  │
  ├─ Coordinator 组装 prepared MapContextResult
  │    ├─ branch = fuzzy
  │    ├─ broad_result = broad MapResult
  │    ├─ active_result = focused MapResult | broad MapResult
  │    ├─ selection_decision = SelectionDecision
  │    └─ artifact / final injection 字段尚未完成
  │
  └─ Engine 设置 runtime.current_map_context = prepared MapContextResult
       └─ 进入“最终注入与 artifact 操作流”
```

### 5.6 Branch B broad fallback / one-shot 完整操作数据流

broad fallback 是可预期的正常控制结果，不是 MapContext 异常。

```text
Branch B broad MapResult 已生成
  │
  ├─ [Engine._can_confirm_focus() = False]
  │    ├─ 不调用 selector LLM
  │    ├─ 不调用 runtime.ask_user()
  │    ├─ 不发送 map_selector_requested
  │    ├─ 不发送 map_focus_confirmed
  │    └─ Engine 形成 SelectionDecision.broad_fallback(
  │         reason=one_shot_no_confirm
  │       )
  │
  ├─ [selector 请求超预算]
  │    ├─ 不发送 map_selector_requested
  │    ├─ 不递增 selector_model_calls
  │    └─ Engine 形成 SelectionDecision.broad_fallback(
  │         reason=selector_request_over_budget
  │       )
  │
  └─ [交互模式 selector / confirmation 未得到有效 focus]
       ├─ selector 实际发起过时已记录 map_selector_requested
       ├─ 只有用户选择“接受全部建议”且 confirmed files 非空时才记录 map_focus_confirmed
       └─ Engine 形成带具体 reason 的 broad fallback decision
  │
  └─ Coordinator.prepare_fuzzy()
       ├─ 直接复用 broad MapResult
       ├─ 不再次生成 broad map
       ├─ 不生成 focused map
       ├─ 不发送 map_context_failed
       ├─ 保留结构化 fallback reason
       └─ 组装 prepared MapContextResult
```

fallback 的最终用户可见摘要必须在主模型调用前展示，明确标记 `active result = broad` 和 fallback reason。

所有正常 broad fallback 都复用 `original_user_message` 和已经生成的 broad map：不重跑 selector、不重新询问用户，也不要求用户重新输入 prompt。

进入主模型 prompt 时，所有 broad fallback 使用同一条准确状态提示：

```text
No specific focus files were confirmed. Broad repository context is provided for navigation.
```

该提示表示“没有形成 confirmed focus”，不表示 selector 一定没有建议出文件。具体原因仍进入 evidence / trace / report，不把内部错误细节直接注入主模型。

### 5.7 最终注入与 artifact 操作流

Branch A、Branch B focused 和 Branch B broad fallback 最终都汇入同一条流程：

```text
runtime.current_map_context = prepared MapContextResult
  │
  └─ Engine 请求首次 purpose="main_model" prompt build
       │
       └─ ContextManager.build(..., purpose="main_model")
            ├─ 读取 current_map_context.active_result.repo_map_text
            ├─ 从 active_result.focus_fnames 派生 focus_files_display
            ├─ 从 active_result.repo_map_text 派生 active_repo_map_text
            ├─ 读取 runtime.model_request_budget
            ├─ 构造独立 repo_map section
            │    ├─ map_context_prompt 生成固定导航安全契约
            │    ├─ 根据 Branch / Mode / focus 生成状态行
            │    ├─ broad fallback 时加入统一 fallback notice
            │    └─ 拼接 active_repo_map_text
            ├─ 估算完整 repo_map section token
            ├─ 为 repo_map section 预留输入空间
            ├─ 仅缩减 prefix / memory / history / current_request 等原有 section
            ├─ 不再次裁剪 repo map body
            ├─ 导航安全契约完整保留或整段省略
            └─ 返回 PromptBuildResult
                 └─ repo_map_render 是当前 build 独立的 RepoMapSectionRender
                      ├─ 实际注入文本
                      ├─ contract / fallback notice 是否注入
                      ├─ map body 原始和最终字符数
                      ├─ section 最终字符数 / hash
                      ├─ base prompt 是否发生 reduction
                      ├─ omission reason
                      └─ request_over_budget metadata
       │
       └─ Engine 将 build-local repo_map_render 交给 Coordinator.finalize_prompt_context()
            │
            ├─ [完整证据链落盘成功]
            │    ├─ 写 .pico/runs/<run_id>/artifacts/repo-map-001.txt
            │    │    └─ 内容是首次主模型 prompt 实际注入的 repo_map section
            │    ├─ 组装 PromptInjectionEvidence 和 MapEvidenceArtifact
            │    ├─ 写 .pico/runs/<run_id>/artifacts/map-evidence-001.json
            │    ├─ 更新 .pico/map_engine/repo-map-latest.md 便捷快照
            │    │    └─ 不额外触发 broad map 生成，不作为 run 证据
            │    ├─ 更新 TaskState / report 可消费摘要
            │    ├─ 返回相同 map_context_id 的 finalized MapContextResult
            │    └─ Coordinator 调 runtime.emit_trace(map_generated)
            │
            └─ [任一必要证据落盘步骤失败]
                 ├─ Coordinator 调 runtime.emit_trace(map_context_failed)
                 ├─ 设置 runtime.current_map_context = None
                 ├─ 部分 artifact 视为无效，不进入 TaskState / trace / report 引用
                 ├─ 丢弃本次已经构建的含 repo map prompt
                 ├─ 不重新运行 MapEngine、不重新调用 selector、不重新询问用户
                 └─ Engine 重新执行 purpose="main_model" build
                      └─ 因 current_map_context=None，返回无 repo_map section 的 prompt
       │
       ├─ [落盘成功但预留 repo map 后 base prompt 仍无法容纳]
       │    ├─ Engine 清除 runtime.current_map_context
       │    ├─ 丢弃含 repo map prompt
       │    ├─ 重新执行 purpose="main_model" build
       │    ├─ 因 current_map_context=None，返回无 repo_map section 的 prompt
       │    └─ 若仍超出 ModelRequestBudget，则本地超预算失败；不发起 provider 调用，也不发送 model_requested
       │
       ├─ [落盘成功] Engine 用 finalized 对象替换 prepared 对象
       │    ├─ runtime.current_map_context = finalized MapContextResult
       │    ├─ MapEngineConsoleReporter 将 finalized evidence 转成最终摘要
       │    ├─ Engine yield 最终摘要用户事件
       │    └─ CLI / TUI 在主模型调用前展示最终摘要
       ├─ Engine 发送当前实际将使用的 prompt_built trace
       ├─ TaskState.main_model_calls += 1
       └─ Engine 发起 Pico 主模型调用
```

这里存在两个必须区分的文本：

| 文本 | 含义 | 保存位置 |
|---|---|---|
| MapEngine 候选 repo map | 在 MapEngine 独立 token budget 内生成 | `MapResult.repo_map_text` |
| 导航安全契约 | 告诉主模型 repo map 只用于导航、必须 `read_file` 完整文件、不满足 freshness；Branch A、Branch B focused 和 Branch B broad fallback 共用同一模板 | `map_context_prompt` 生成，随 repo_map section 注入 |
| 最终实际注入 repo map section | 完整导航安全契约 + 动态状态行 + MapEngine 独立 token budget 已裁剪的 map body；若因预算降级被整段省略，则为空文本并由 evidence 解释原因 | `repo-map-001.txt` 与 finalized `MapContextResult` |

只有完整证据链落盘成功后，含 repo map 的 prompt 才能发送给主模型。`map_generated` trace 在 artifact 成功写入后发送；`prompt_built` trace 随后记录当前真正将用于主模型请求的 prompt，因此 trace 顺序可以是 `map_generated -> prompt_built -> model_requested`，但 prompt build 操作本身发生在 artifact 写入之前。

### 5.8 Pico tool loop、run 结束与清理操作流

```text
Pico 主模型收到 prompt + repo_map section
  │
  ├─ 根据 repo map 判断可能相关文件
  ├─ 调 read_file / search 获取完整当前源码
  ├─ 基于完整源码分析
  ├─ 按 Pico 原有规则调用 patch_file / write_file / 其他工具
  │
  ├─ [需要再次调用主模型]
  │    ├─ 复用 finalized current_map_context
  │    ├─ ContextManager 使用 purpose="main_model" 可再次注入同一 active map
  │    ├─ 后续 build 只在 prompt_built trace 记录 render hash、字符数和 omission 状态
  │    ├─ 不重复写完整 repo map artifact
  │    ├─ 不重新运行 MapEngine
  │    ├─ 不重新调用 selector
  │    └─ 不重新询问用户
  │
  └─ [完成 / 失败 / 用户停止 / step limit]
       ├─ emit run_finished 或对应退出事件
       ├─ 写 report.json 轻量摘要
       ├─ 保留已落盘 trace 和 artifacts
       └─ 在统一清理路径设置 current_map_context = None
```

repo map 只提供导航。主模型不能把 map 中的结构摘要当成完整源码，也不能绕过 `read_file` freshness 规则直接编辑。

### 5.9 MapContext 整体失败操作流

单文件解析失败、cache miss、selector 无效等可局部降级问题不进入本流程。只有 MapContext preparation 或完整注入证据落盘出现未能局部处理的增强层异常时，才进入整体失败。

preparation 失败：

```text
MapContext preparation 出现未局部处理异常
  │
  └─ Coordinator 捕获异常
       ├─ 对错误信息执行 runtime redaction
       ├─ 调 runtime.emit_trace(map_context_failed)
       ├─ 设置 runtime.current_map_context = None
       └─ 将失败状态返回 Engine
  │
  └─ Engine 继续 Pico 原有主流程
       ├─ ContextManager 不注入 repo_map section
       ├─ CLI / TUI 在主模型前展示增强层失败提示
       └─ 主模型仍可使用 Pico 原有 context 和 tools 执行
```

完整注入证据落盘失败：

```text
含 repo map 的首次 main_model PromptBuildResult 已生成
  -> finalize_prompt_context() 失败
  -> Coordinator emit map_context_failed
  -> current_map_context = None
  -> 部分 artifact 不作为有效证据引用
  -> 丢弃含 repo map 的 prompt
  -> Engine 重建无 repo map prompt
  -> Pico 原主模型调用继续
```

`map_context_failed` 只表示增强层异常，不能用于表示正常 broad fallback。

### 5.10 数据对象状态转换

| 时间点 | 主要数据对象 | 数据去向 |
|---|---|---|
| 用户请求前 | `current_map_context=None` | runtime 临时状态 |
| 公共 preparation 后 | `PromptAnalysis` | Coordinator 返回 Engine，供 Engine 选择 Branch |
| Branch A ranking 后 | focused `MapResult` + `MapContextEvidence` | MapEngine 返回 Coordinator |
| Branch B 阶段一后 | broad `MapResult` + `MapContextEvidence` | Coordinator 返回 Engine，供 selector/fallback 使用 |
| Branch B 控制流后 | `SelectionDecision` | Engine 返回 Coordinator，Coordinator 不自行决定 |
| active result 确定后 | prepared `MapContextResult` | 写入 `runtime.current_map_context`，供 ContextManager 使用 |
| 首次 main_model build 后 | `PromptBuildResult.repo_map_render` | Engine 立即传给 Coordinator，不进入共享状态或 session |
| artifact 落盘后 | finalized `MapContextResult` | 替换 prepared 对象，供主模型 retry/tool loop 复用 |
| artifact 落盘失败后 | `current_map_context=None` + 无 repo map `PromptBuildResult` | 丢弃含 map prompt，重建后继续 Pico |
| run 结束后 | `report.json` + trace + artifacts | 持久保存；`current_map_context` 清理为 `None` |

---

## 六、启动阶段

### 6.1 启动时发生什么

启动 Pico 时：

- 创建 Pico session。
- 创建 MapEngine 对象。
- 创建 MapContextCoordinator 对象。
- 可读取已有 cache metadata。
- 记录 MapEngine feature 和预算状态。
- MapEngine feature flag 默认关闭。
- child runtime / worker 显式关闭 MapEngine，不继承父 runtime 的启用状态。

启动时不发生：

- 不枚举整个仓库。
- 不解析 AST。
- 不构建引用图。
- 不执行 PageRank。
- 不生成 repo map。
- 不调用 selector 或主模型。

### 6.2 启动数据流

```text
Pico 启动
  -> runtime 装配 MapEngine
  -> runtime 装配 Coordinator
  -> current_map_context = None
  -> SessionEventBus: map_engine_initialized
  -> 等待用户输入
```

### 6.3 用户可见行为

默认只显示 MapEngine 已启用和预算简要信息，不显示完整索引摘要。

---

## 七、用户请求进入系统

### 7.1 run 建立

用户提交请求后，Engine 首先：

- 创建新的 `TaskState`。
- 创建 `.pico/runs/<run_id>/`。
- 记录原始用户请求。
- 发送 `run_started`。

此时已经具备：

- run id。
- task id。
- 用户请求。
- RunStore 路径。
- trace 写入能力。

此后才开始 MapContext preparation。

### 7.2 Lazy Index

首次用户请求触发 index 检查：

```text
以 workspace.repo_root 为 Git 操作目录
  -> 通过 Git index 枚举 tracked / staged 路径
  -> 只保留当前工作树存在、未命中 denylist 的普通 `.py` 文件
  -> 不纳入 untracked Python 或非代码文件
  -> 检查 cache metadata
  -> 未变化文件复用缓存
  -> 新增或变化文件重新解析
  -> 形成当前 index snapshot
  -> emit map_index_status
```

cache hit 不代表完全不做工作：

- 仍需枚举允许分析的文件。
- 仍需检查文件元信息。
- 只是不重新解析未变化文件。
- tracked 但已从工作树删除的文件被跳过并记录。
- 非 Git workspace 或 Git 文件枚举失败时，MapEngine 不可用，禁止回退为文件系统递归扫描，Pico 原流程继续。

### 7.3 Prompt Analysis

```text
用户请求
  -> 提取文件路径 / basename / stem
  -> 提取完整 mentioned_idents
  -> 与 index defs 对齐得到 effective_symbol_hits
  -> 生成 PromptAnalysis
  -> emit map_prompt_analyzed
```

随后由 Engine 根据 PromptAnalysis 选择 Branch。

`mentioned_idents` 是 ranking 的 ident boost 输入；`effective_symbol_hits` 只用于 Branch 判断、trace、evidence 和 eval。

---

## 八、Branch A：Prompt 明确命中

### 8.1 触发条件

```text
mentioned_files 非空
OR
effective_symbol_hits 非空
```

典型请求：

- “修复 `auth.py` 中的 token 校验。”
- “分析 `JWTAuth` 的实现。”
- “修改 `get_repo_map`。”

### 8.2 数据流

```text
PromptAnalysis(branch=specific)
  -> Engine 调 Coordinator.prepare_specific()
  -> Coordinator 调 MapEngine.generate_focused()
  -> MapEngine 使用 prompt hits 进行排名和渲染
  -> MapEngine 返回 focused MapResult + MapContextEvidence
  -> Coordinator 组装 MapContextResult
  -> runtime.current_map_context = MapContextResult
```

### 8.3 排名语义

- 文件命中进入 `focus_fnames`；其中实际存在于文件图节点的文件进入 `personalization_files`，成为 PPR seed。
- 完整 `mentioned_idents` 可增强相关 identifier 引用边。
- `effective_symbol_hits` 不改变 PageRank/PPR 分数，但对应的精确命中 DefinitionRecord 固定进入 focused map 候选前缀。
- `personalization_files` 的出站引用可增强相关定义文件。
- `GraphRanker` 将按 definition group rank 排序后的 `tuple[DefinitionRecord, ...]` 和文件级排序结果交给 `ContextRenderer`。
- symbol-only Branch A 的 `focus_fnames=()`、`personalization_files=()`，`MapResult.mode="focused"`，成功时 `RankingEvidence.algorithm="pagerank"`。
- focus 文件仍保留在 repo map 中，不因 Aider chat-file 语义被排除。

### 8.4 预算语义

- focused map 固定使用 4,096 token budget，不因是否存在 focus 文件而扩容。
- 精确命中的 DefinitionRecord 即使没有引用边，也固定进入 focused map 候选前缀。
- 如果仍无法完整容纳，保留路径和尽可能多的顶层结构，并记录 truncation。

### 8.5 LLM 与用户交互

Branch A：

- 不调用 selector LLM。
- 不询问用户确认 focus 文件。
- 直接形成执行用 focused map。

---

## 九、Branch B：Prompt 模糊，无明确命中

### 9.1 触发条件

```text
mentioned_files 为空
AND
effective_symbol_hits 为空
```

典型请求：

- “修复登录问题。”
- “优化这个项目的缓存。”
- “找出可能导致请求失败的代码。”

### 9.2 阶段一：生成 broad map

```text
PromptAnalysis(branch=fuzzy)
  -> Engine 调 Coordinator.prepare_broad()
  -> Coordinator 调 MapEngine.generate_broad()
  -> MapEngine 执行全仓标准 PageRank
  -> broad MapResult.mode = broad
  -> RankingEvidence.focus_fnames = ()
  -> RankingEvidence.personalization_files = ()
  -> PageRank 成功时 RankingEvidence.algorithm = pagerank；失败或空图时为 stable_path_fallback
  -> MapEngine 使用 broad token budget = 8,192 渲染导航图
  -> 返回 broad MapResult + MapContextEvidence
```

### 9.3 selector LLM 前的用户可见行为

在 selector LLM 调用前，系统必须先展示 broad map 简要状态：

- 当前 branch。
- broad map 使用的 8,192 token budget。
- 主要候选文件。
- index/cache 状态。

目的：

- 用户能观察 selector 收到了什么导航信息。
- “在输出进 LLM 之前打印状态”的要求覆盖 selector LLM。

### 9.4 交互模式 selector 流程

```text
Coordinator 调 MapEngine.build_selector_catalog()
  -> 使用同一 SymbolIndex snapshot 生成完整 provenance 路径和预算受控目录
  -> Engine 组装 SelectorModelRequest
       system_prompt = 固定 JSON 输出和文件选择约束
       user_prompt = original_user_message + broad map + rendered candidate catalog
       visible_paths = stable union(broad rendered files, catalog rendered paths)
  -> [完整 SelectorModelRequest 超过 ModelRequestBudget]
  ->    selector_request_over_budget broad fallback
  -> [完整 SelectorModelRequest 通过预算门禁]
  ->    Engine 直接调 runtime.emit_trace(map_selector_requested)
  ->    Engine 使用 runtime/provider 按 system_prompt / user_prompt 角色发起 selector LLM 调用
  ->    selector 返回结构化文件建议
  ->    MapSelector 只接受 SelectorModelRequest.visible_paths 中存在的路径
  ->    selector 可建议未进入 broad map、但实际出现在 Selector Candidate Catalog 中的文件
  ->    无有效 suggested_files：selector_no_valid_files broad fallback
  ->    有有效 suggested_files：Engine 调 runtime.ask_user(["接受全部建议", "使用 broad map"])
  ->    接受全部建议且 confirmed files 非空：Engine 直接调 runtime.emit_trace(map_focus_confirmed)
  ->    使用 broad map / Esc / 未知值：形成对应 broad fallback reason
  ->    所有 broad fallback 复用 original_user_message 和 broad map，不重跑 selector、不重新询问用户、不要求重新输入 prompt
  ->    Engine 形成 SelectionDecision
```

`map_selector_requested` 只表示 selector 调用即将发生，不表示 selector 已完成。

`map_focus_confirmed` 只在用户选择“接受全部建议”且 confirmed files 非空后发送。v1 不支持部分接受、增删或调整 selector 建议文件。

### 9.5 阶段二：形成执行用 map

用户确认文件非空：

```text
SelectionDecision(confirmed files)
  -> Engine 调 Coordinator.prepare_fuzzy()
  -> Coordinator 调 MapEngine.generate_focused()
  -> confirmed files 成为 focus_fnames
  -> 实际存在于文件图节点的 focus_fnames 成为 personalization_files
  -> 复用 broad map 的 SymbolIndex snapshot
  -> 使用 focused token budget = 4,096
  -> MapResult.mode 保持 focused，RankingEvidence.algorithm 记录实际算法
  -> 返回最终 focused MapResult
```

用户选择 broad map、取消、返回未知值，或 selector 无有效路径：

```text
SelectionDecision(broad fallback)
  -> Engine 调 Coordinator.prepare_fuzzy()
  -> 不再次生成 focused map
  -> broad MapResult 成为 active result
```

### 9.6 one-shot / 无交互模式

当 `Engine._can_confirm_focus() = False`：

- v1 不自动采纳 selector 建议。
- 不调用 selector LLM。
- SelectionDecision 使用 `one_shot_no_confirm`。
- 不发送 `map_focus_confirmed`。
- 直接使用 broad map fallback。
- 主执行链继续。

selector call 不计入控制主 Agent loop 停止条件的 `TaskState.attempts`。v1 每个 run 最多调用一次 selector。`TaskState.attempts` 记录主 Agent loop 进入次数；`TaskState.main_model_calls` 和 `TaskState.selector_model_calls` 分别记录实际发起的主模型与 selector 模型调用，`total_model_calls = TaskState.main_model_calls + TaskState.selector_model_calls`。

---

## 十、ContextManager 注入流程

### 10.1 输入

ContextManager 从 runtime 读取：

```text
current_map_context: MapContextResult
model_request_budget: ModelRequestBudget
```

然后使用：

```text
current_map_context.active_result.repo_map_text
```

### 10.2 Prompt purpose 与单次 build 返回

每个 prompt build 调用点必须显式提供 `PromptPurpose`：

| purpose | 注入 repo map | 允许 auto-compaction | 可写完整 repo map artifact |
|---|---:|---:|---:|
| `main_model` | 是 | 是 | 仅首次最终返回并用于主模型请求的 result |
| `prompt_preview` | 是 | 否 | 否 |
| `evaluation` | 否 | 否 | 否 |
| `step_limit_summary` | 否 | 否 | 否 |

每次 ContextManager build 都返回独立 `PromptBuildResult`。当前 build 的 repo map 渲染结果只存在于 `PromptBuildResult.repo_map_render` 中：

- `prompt_preview` 只展示，不产生 artifact 或覆盖主模型注入 evidence。
- `evaluation` 和 `step_limit_summary` 不注入 repo map。
- auto-compaction 表示 `Pico._build_prompt_and_metadata()` 检测到“为完整 repo_map 预留空间后的有效 base prompt”超预算后，调用 `compact_history(trigger="auto_prompt_over_budget")` 修改 session history，再重新执行一次 prompt build。
- auto-compaction 只允许由 `main_model` 触发；首次 main_model build 内重复构建时始终复用 prepared MapContextResult，不重新运行 MapEngine。
- finalized 对象生成后，后续 main_model build 复用 finalized MapContextResult，只在对应 `prompt_built` trace 中记录 render 摘要。
- Pico runtime 中所有 `_build_prompt_and_metadata()` 包装入口，包括现有 `prompt()` 和 `prompt_metadata()` helper，都必须显式传递 `PromptPurpose`。

### 10.3 Section 顺序

```text
prefix
  -> memory
  -> skills
  -> relevant_memory
  -> history
  -> repo_map
  -> current_request
```

repo map 紧贴当前请求之前，作为本轮导航信息。

### 10.4 导航安全契约与最终格式

repo map 不是完整源码。只要当前 run 存在 `MapContextResult`，ContextManager 就必须在 map body 前注入固定导航安全契约。Branch A、Branch B focused 和 Branch B broad fallback 共用同一模板：

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

它是 repo_map section 内的安全契约，不是 Pico 全局 prefix，也不是主模型的 provider-level system prompt。selector 的 provider-level system prompt 是独立例外，只用于 selector LLM：

- MapEngine 禁用、MapContext 整体失败或当前 run 没有 map 时，不注入该契约。
- `focus_files_display` 只从 `current_map_context.active_result.focus_fnames` 派生，只表示读取优先级，不表示文件已读取或可直接编辑。
- `active_repo_map_text` 只从 `current_map_context.active_result.repo_map_text` 派生。
- 不使用来源模糊的 `focused_repo_map_string` 或 `focus_fnames_list` 作为模板变量。
- focused 模式不显示 fallback notice。
- broad fallback 显示：

```text
No specific focus files were confirmed. Broad repository context is provided for navigation.
```

### 10.5 独立预算与注入

MapEngine 已按 focused/broad 独立 token budget 生成候选 map。repo map body 不参与 Pico 原有 section reduction order，但完整 repo_map section 必须计入最终模型输入预算。

```text
固定导航安全契约 + 动态状态行 + 候选 repo map body
  -> ContextManager repo_map section renderer
  -> 估算完整 repo_map section token
  -> 为该 section 预留输入空间
  -> 仅缩减 Pico 原有 section
  -> 不再次 head clip repo map body
  -> 完整保留导航安全契约或整段省略
  -> 最终实际注入 repo_map section
```

MapEngine broad map 使用 8,192 token budget，focused map 使用 4,096 token budget；v1.3 使用 `ceil(chars / 4)` 作为稳定 token 估算。

### 10.6 数据回流

ContextManager 完成最终渲染后，通过当前 `PromptBuildResult.repo_map_render` 将以下信息交回 Engine，再由 Engine 传给 Coordinator：

- 最终实际注入的 repo map 文本。
- 导航安全契约和 fallback notice 是否注入。
- `map_body_raw_chars`：MapEngine 候选 repo map body 的字符数，不包含契约、动态状态行或 fallback notice。
- `map_body_rendered_chars`：实际注入的 repo map body 字符数；正常注入时等于 `map_body_raw_chars`。
- 最终字符数和 hash。
- `base_prompt_reduction_applied`：是否因为给 repo map section 预留空间而缩减 base prompt。
- `request_over_budget`：最终完整请求是否仍超出 `ModelRequestBudget`。
- 未注入整个 section 时的 omission reason。

Coordinator 使用这些事实写最终 run artifacts。

artifact 和 run 摘要完整落盘后，Coordinator 返回 finalized `MapContextResult`。runtime 使用 finalized 对象替换 preparation 阶段的 prepared `MapContextResult`，后续主模型 retry/tool loop 复用 finalized 对象。

如果任一必要证据落盘步骤失败，Coordinator 发送 `map_context_failed` 并清除 `current_map_context`；Engine 丢弃已经构建的含 repo map prompt，重新 build 无 repo map prompt 后继续 Pico。

---

## 十一、Artifact 与证据落盘

### 11.1 持久 MapEngine 状态

```text
.pico/map_engine/index.json
.pico/map_engine/cache.meta.json
.pico/map_engine/repo-map-latest.md
```

用途：

- `index.json`：机器可读 symbol/ref/index 存储，只供 MapEngine 分析、排名和生成候选 map；selector 不直接读取。
- `cache.meta.json`：缓存和版本元信息，包括 mtime、size、parser/query/schema version 和 index_snapshot_id。
- `repo-map-latest.md`：最近一次成功生成的 broad 或 focused 候选 map body 便捷快照，不触发额外 map 生成，也不代表某个 run 实际注入内容。
- `repo-map-latest.md` 只保存 MapEngine 候选 map body，不包含当前 run 的导航安全契约、动态状态行或 fallback notice。

### 11.2 当前 run artifacts

```text
.pico/runs/<run_id>/artifacts/repo-map-001.txt
.pico/runs/<run_id>/artifacts/map-evidence-001.json
```

`repo-map-001.txt`：

- 只保存首次 `purpose="main_model"` 最终返回并用于主模型请求的 repo map section 内容。
- 包含完整导航安全契约、动态状态行、可选 fallback notice 和 MapEngine 独立 token budget 已裁剪的 map body。
- 不能只保存 MapEngine 裁剪前候选文本。
- 如果 repo_map section 注入渲染失败，或预留 repo map 后必须降级为无 repo map prompt，则保存空文本，并由 evidence 记录稳定空 hash 和 omission reason。

`map-evidence-001.json`：

- 是 `MapEvidenceArtifact` 的序列化结果，保存完整检索事实和控制决策。
- 包含 broad/focused 结构化结果、selector/确认/fallback、首次主模型最终注入信息和 repo map artifact 引用。
- 不保存完整 repo map 文本，也不保存自身 artifact path。

同一 run 内后续主模型 build 不重复写完整 repo map artifact，只在对应 `prompt_built` trace 中记录 render hash、字符数和 omission 状态。

### 11.3 落盘顺序

```text
首次 purpose="main_model" build 返回 build-local RepoMapSectionRender
  -> Engine 将 repo_map_render 交给 Coordinator.finalize_prompt_context()
  -> Coordinator 写 repo-map-001.txt 并取得稳定路径
  -> Coordinator 使用该路径组装并写 map-evidence-001.json
  -> Coordinator 更新 TaskState / report 可消费摘要
  -> Coordinator 返回 finalized MapContextResult
  -> runtime.current_map_context 替换为 finalized MapContextResult
  -> Coordinator 调 runtime.emit_trace(map_generated)
```

如果上述任一步骤失败，则不发送该次含 repo map prompt：Coordinator 发送 `map_context_failed`、清除 `current_map_context`，部分 artifact 不作为有效证据引用，Engine 重建无 repo map prompt 后继续。

---

## 十二、终端与用户可见输出

### 12.1 输出原则

- 终端输出是 evidence 的用户可见投影。
- 终端不产生新事实。
- 同一 run 内主模型多次 retry/tool loop 不重复打印最终 MapContext 摘要。
- 输出应发生在对应 LLM 调用前。

### 12.2 默认输出时机

| 场景 | 用户看到什么 | 时机 |
|---|---|---|
| 首次 lazy index cache miss | index 和仓库摘要 | index 完成后 |
| Branch A | focused retrieval 摘要 | 主模型前 |
| Branch B 阶段一 | broad retrieval 摘要 | selector LLM 前 |
| Branch B 阶段二 | confirmed focused 摘要 | 主模型前 |
| Branch B fallback | broad fallback 摘要 | 主模型前 |
| MapContext 增强层失败 | 检索或证据落盘失败和 Pico 继续执行提示 | 主模型前 |

### 12.3 用户可见摘要内容

默认摘要包含：

- Branch。
- broad / focused / fallback 模式。
- focus files。
- top ranked files 与实际 rendered / omitted files。
- prompt symbol hits 和已有 evidence 支持的 top rank contributors。
- used tokens / budget tokens。
- cache hit/miss。
- focus truncation。
- artifact 已完整落盘后可用的 evidence artifact 路径。

格式参考：

```
◆ Repository Intelligence Summary
  ├── Branch / mode:    specific / focused
  ├── Focus files:      auth.py
  ├── Top ranked files: auth.py(PRn:0.87), db.py(PRn:0.71), models.py(PRn:0.64)
  ├── Rendered/omitted: 3 / 5
  ├── Budget:           12000 / 32768 chars
  └── Evidence:         .pico/runs/<run_id>/artifacts/map-evidence-001.json
```

Branch B selector 前的 broad 摘要发生在 run artifact 落盘前，因此不得展示或伪造 evidence artifact path。终端不得产生 evidence 中不存在的新推理理由。



---

## 十三、Pico 主模型与工具执行

### 13.1 主模型输入

Pico 主模型收到：

- Pico 原有 prefix、memory、history 和当前请求。
- 当前 run 的 repo map 导航 section，包括完整导航安全契约、动态状态行和 map body。

主模型不会直接收到：

- 完整 `MapContextEvidence` JSON。
- 完整 index。
- selector 原始控制对象。
- 用户确认内部状态对象。

### 13.2 文件读取安全边界

repo map 中出现文件不代表已读取。

导航安全契约负责提醒主模型正确使用 repo map；Pico `ToolPolicyChecker` 的 fresh-read 校验负责强制阻止未读取就修改已有文件。提示层与工具策略层同时保留。

正确执行路径：

```text
模型从 repo map 发现可能相关文件
  -> 调用 read_file
  -> 获得完整当前源码
  -> 基于完整源码分析
  -> 再调用 patch_file / write_file
```

`file_summaries` 和 freshness 规则保持 Pico 原有语义。

### 13.3 同一 run 内复用

当主模型调用工具后再次进入模型：

- 不重新执行 MapEngine。
- 不重新调用 selector。
- 不重新询问用户。
- 复用同一 `current_map_context`。
- ContextManager 使用 `purpose="main_model"` 可再次注入同一 map。
- 不重复写完整 repo map artifact，只在 `prompt_built` trace 中记录本次 render 摘要。

---

## 十四、Trace 事件顺序

### 14.1 Branch A 正常顺序

```text
run_started
map_index_status
map_prompt_analyzed
map_context_ranked
map_context_selected
map_generated
prompt_built
model_requested
...
run_finished
```

### 14.2 Branch B 交互模式正常顺序

```text
run_started
map_index_status
map_prompt_analyzed
map_context_ranked        stage=broad
map_context_selected      stage=broad
map_selector_requested
map_focus_confirmed
map_context_ranked        stage=focused
map_context_selected      stage=focused
map_generated
prompt_built
model_requested
...
run_finished
```

### 14.3 Branch B broad fallback 顺序

```text
run_started
map_index_status
map_prompt_analyzed
map_context_ranked        stage=broad
map_context_selected      stage=broad
map_selector_requested    仅交互 selector 实际发起时存在
map_generated             active result = broad
prompt_built
model_requested
...
run_finished
```

### 14.4 MapContext preparation 整体失败顺序

```text
run_started
map_context_failed
prompt_built              无 repo_map section
model_requested
...
run_finished
```

`map_context_failed` 表示异常失败，不用于表示正常 broad fallback。

`map_generated -> prompt_built` 表示 artifact 已完整落盘后，Engine 再发送当前实际用于主模型请求的 prompt trace。prompt 的 build 操作本身发生在 `map_generated` 之前。

### 14.5 完整注入证据落盘失败顺序

```text
run_started
map_index_status
map_prompt_analyzed
map_context_ranked / map_context_selected
map_context_failed         证据落盘失败，丢弃含 repo map prompt
prompt_built               重建后的无 repo_map section prompt
model_requested
...
run_finished
```

该路径不发送 `map_generated`，TaskState、trace 和 report 不引用未形成完整证据链的部分 artifact。

---

## 十五、Report 数据流

### 15.1 report 的职责

`report.json` 是当前 run 的最终轻量摘要。

它保存：

- MapEngine 是否启用。
- branch 和 stage。
- focus_fnames 和 rendered_files。
- index snapshot id。
- selector_model_calls。
- main_model_calls 和 total_model_calls。
- 完整证据链落盘成功时的 repo map / evidence artifact 路径。

它不复制：

- 完整 repo map 文本。
- 完整 evidence。
- 完整 trace。

### 15.2 事实层级

```text
完整事实：map-evidence-001.json
事件时间线：trace.jsonl
最终摘要：report.json
用户展示：terminal / TUI
```

---

## 十六、失败与降级流程

### 16.1 单文件解析失败

```text
解析某文件失败
  -> 跳过该文件
  -> 记录 skipped file
  -> 继续构建其余 index
```

对用户影响：repo map 可能缺少该文件，但 Pico 主任务仍继续。

### 16.2 Cache 失败

```text
cache 读取失败
  -> 尝试重建或使用内存状态
  -> emit map_index_status
  -> 继续当前 run
```

cache 写入失败时，当前内存中的检索结果仍可用于本次 run；记录 `map_index_status` 后继续，不阻断主模型。

### 16.3 Ranking / Rendering 失败

```text
空图或 PageRank 失败
  -> 按 repo-relative path 使用稳定文件排序
  -> 记录 RankingEvidence.algorithm=stable_path_fallback
  -> 继续主执行链

TreeContext 单文件失败
  -> 输出该文件路径或跳过该文件
  -> 记录 rendering evidence
  -> 继续其余文件渲染
```

### 16.4 Selector 失败

```text
selector JSON 无效
OR 建议路径全部无效
  -> selector_no_valid_files broad fallback
  -> 具体解析错误保存在 SelectorResult.parse_error
  -> 不调用 runtime.ask_user()
  -> 不发送 map_context_failed
  -> 继续主模型

完整 SelectorModelRequest 超过 ModelRequestBudget
  -> selector_request_over_budget broad fallback
  -> 不发送 map_selector_requested
  -> 不递增 selector_model_calls
  -> 不发送 map_context_failed
  -> 继续主模型

用户选择“使用 broad map”
  -> user_selected_broad fallback

用户 Esc / 空字符串
  -> user_cancelled fallback

ask_user 返回未知值
  -> invalid_confirmation fallback

所有正常 broad fallback
  -> 不发送 map_context_failed
  -> 主模型 repo_map section 显示统一 broad fallback notice
  -> 复用 original_user_message 和已经生成的 broad map
  -> 不重跑 selector、不重新询问用户、不要求用户重新输入 prompt
  -> 继续主模型
```

### 16.5 MapContext 整体失败

```text
MapContext preparation 抛出未局部处理异常
  -> Coordinator 调 runtime.emit_trace(map_context_failed)
  -> current_map_context = None
  -> 不注入 repo_map section
  -> Pico 原流程继续

非 Git workspace 或 Git 文件枚举失败
  -> 禁止递归扫描 fallback
  -> Coordinator 调 runtime.emit_trace(map_context_failed)
  -> current_map_context = None
  -> Pico 原流程继续

首次含 repo map prompt 已构建，但完整注入证据落盘失败
  -> Coordinator 调 runtime.emit_trace(map_context_failed)
  -> current_map_context = None
  -> 部分 artifact 不作为有效证据引用
  -> 丢弃含 repo map prompt
  -> Engine 重建无 repo map prompt
  -> Pico 原流程继续

预留 repo map 后 base prompt 仍无法容纳
  -> current_map_context = None
  -> 丢弃含 repo map prompt
  -> Engine 重建无 repo map prompt
  -> 若仍超出 ModelRequestBudget，则不发起 provider 调用，走本地超预算失败路径
```

---

## 十七、run 结束与状态清理

### 17.1 正常结束

```text
Pico 完成任务
  -> run_finished
  -> report.json 写入
  -> current_map_context 清理为 None
  -> turn_finished
```

### 17.2 失败或停止

模型错误、用户停止、step limit 等所有退出路径同样必须：

- 写入当前 run 可用 report。
- 保留已形成完整证据链的 map artifacts。
- 不把证据落盘失败产生的部分 artifact 引用为有效 run 证据。
- 清理 `current_map_context`。
- 不让旧 map 泄漏到下一个用户请求。

### 17.3 Session 与下一轮

当前 `MapContextResult` 不写入 session。

下一次用户请求：

- 创建新的 run。
- 复用持久 index/cache。
- 重新执行 prompt analysis 和 map preparation。

---

## 十八、Branch 对比

| 项目 | Branch A | Branch B |
|---|---|---|
| 触发 | prompt 命中文件或 symbol | prompt 无明确命中 |
| 第一张 map | focused | broad |
| selector LLM | 不调用 | 交互模式调用 |
| 用户确认 | 不需要 | 交互模式需要 |
| 最终 active map | focused | confirmed focused 或 broad fallback |
| repo map token budget | focused 固定 4,096 | broad 8,192；confirmed focused 改为 4,096 |
| 主模型前输出 | final focused 摘要 | final focused/fallback 摘要 |

---

## 十九、完整数据流总图

```text
┌─────────────────────────────────────────────────────────────┐
│ 用户提交请求                                                │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Engine 创建 TaskState / run，emit run_started               │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Coordinator -> MapEngine：lazy index + PromptAnalysis       │
│ MapEngine 返回确定性分析事实                                │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
                  ┌────────┴────────┐
                  │ Engine 选择分支 │
                  └────────┬────────┘
                           ↓
        ┌──────────────────┴───────────────────┐
        │                                      │
        ↓                                      ↓
┌───────────────────┐                ┌────────────────────────┐
│ Branch A specific │                │ Branch B fuzzy         │
│ generate focused  │                │ generate broad         │
└─────────┬─────────┘                └───────────┬────────────┘
          │                                      ↓
          │                           broad 状态在 selector 前展示
          │                                      ↓
          │                           build selector catalog
          │                           + Engine selector + ask_user
          │                                      ↓
          │                           focused 或 broad fallback
          └──────────────────┬───────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ Coordinator 组装 MapContextResult                           │
│ runtime.current_map_context 保存对象                        │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ ContextManager 首次 main_model build，返回 build-local render │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Coordinator 尝试写 repo-map-001.txt / map-evidence-001.json │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
                  ┌────────┴────────┐
                  │ 完整证据链成功? │
                  └────────┬────────┘
                           ↓
        ┌──────────────────┴───────────────────┐
        │                                      │
        ↓                                      ↓
┌──────────────────────────────┐      ┌──────────────────────────┐
│ 成功：evidence 已就绪         │      │ 失败：map_context_failed │
│ emit map_generated            │      │ current_map_context=None │
│ [可继续带 map 或降级去掉 map] │      │ 重建无 repo map prompt   │
└──────────────┬───────────────┘      └────────────┬─────────────┘
               └────────────────────┬──────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────┐
│ Engine emit prompt_built，发起当前实际 prompt 的主模型调用  │
│ 若无 repo map prompt 仍超预算，则在本地失败，不调用 provider │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Pico 主模型/tool loop                                       │
│ repo map 导航 -> read_file 完整源码 -> 分析/修改            │
└──────────────────────────┬──────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ run_finished / report / 清理 current_map_context             │
└─────────────────────────────────────────────────────────────┘
```

---

## 二十、用户可观察的 v1 成功标准

用户提交一个请求后，应能观察到：

1. 启动时 MapEngine 已初始化，但没有立即扫描仓库。
2. 首次请求后出现 index/cache 状态。
3. 系统明确显示进入 Branch A 或 Branch B。
4. Branch B broad 状态在 selector LLM 前显示。
5. 最终 focused/fallback 状态在主模型前显示。
6. Pico 根据 repo map 导航调用 `read_file`，而不是将 map 当作完整源码。
7. run 目录包含统一命名的 repo map 和 evidence artifacts。
8. trace 可以按顺序复盘检索和控制流。
9. report 可以快速定位 branch、focus/rendered files、模型调用数和 artifact。
10. MapEngine 失败时 Pico 仍能按原流程继续。
11. 存在 MapContext 时，主模型收到完整 `[Repo Map - Navigation Context Only]` 安全契约。
12. broad fallback 明确说明未形成 confirmed focus，但不错误声称 selector 没有识别出文件。
13. MapContext 不存在时，不向 Pico 全局 prefix 或主 prompt 注入空导航契约。
14. repo map 注入证据落盘失败时，系统丢弃含 map prompt、重建无 repo map prompt，并继续 Pico。
15. selector 请求按 provider-level `system_prompt` / `user_prompt` 角色发送，完整请求通过 `ModelRequestBudget` 门禁。
16. selector 只接受实际展示在 broad map 或 Selector Candidate Catalog 中的 `visible_paths`。
17. Branch A、Branch B focused 和 Branch B broad fallback 使用同一主模型导航契约模板。
18. selector 无有效建议或用户拒绝建议时，系统不重跑 selector、不重新询问用户，也不要求重新输入 prompt。
19. 主模型不会使用无法由完整 repo map artifact、evidence artifact 和 run 摘要共同证明的 repo map。
