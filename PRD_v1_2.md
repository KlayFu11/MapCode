# 面向 coding agent 开发执行的工程型 AI 编程协作 PRD

## MapCode PRD v1.1

- Project: MapCode v1
- Stage: MVP Design / SPEC and FuncFlow v1.4 Architecture Alignment
- Date: 2026/6/15
- Target Reader: Self / Claude Code / Codex
- Goal: Define the implementation boundary of MapCode v1: a Pico-runtime-based local coding agent enhanced with Aider-style Repo Map capability, aligned with `SPEC_v1_4.md` and `FuncFlow_v1_4.md`.

---

## 文档目的

1. 明确 MapCode v1 的项目定位、架构边界和第一版实现范围，避免开发过程中扩大范围。
2. 约束 Claude Code / Codex 执行开发时必须以 Pico 现有 runtime 为唯一工程底座进行增量修改。
3. 明确 MapCode v1 不是重建一个新的 coding agent，而是在 Pico runtime 上接入从 Aider Repo Map 中抽象出的仓库结构导航能力。
4. 明确 MapEngine 只负责提供 repo map 导航上下文，不负责代码编辑、不负责完整源码理解、不负责绕过 Pico 现有工具安全边界。
5. 明确当前架构的关键产品规则：文件、symbol、path ident 三类有效信号共同决定 Branch；focus / path personalization 分离；固定 focused / broad token budget；ModelRequestBudget 门禁；可审计 ranking evidence；ContextManager 不二次裁剪 repo map body。

---

## 项目背景

Pico 是一个本地 Python coding agent runtime，已经具备 CLI 入口、运行时控制、上下文构造、模型调用、工具调用、审批、History、Trace、Report、RunStore 等基础能力。

Aider 的 Repo Map 能力提供了一套成熟的代码仓库结构压缩思路：通过 tree-sitter 提取 definition / reference，通过文件级引用图和 PageRank / Personalized PageRank 对文件和符号排序，再在 token budget 内生成仓库结构摘要，帮助模型知道应该优先查看哪些文件和符号。

MapCode v1 的核心思路是：

```text
MapCode = Pico runtime + MapEngine(repo map 能力增强)
```

第一版不另起一个新的 runtime，不重建 SessionManager、Agent loop、ToolRegistry、Approval、TraceWriter 或工具系统。所有功能增量和接口设计修改都必须在 Pico 的现有目录结构、控制流、ContextManager、RunStore、Trace/Report 等模块上进行。

Aider 只作为 Repo Map 行为和算法设计参考。MapCode 需要把 Aider 中有价值的 repo map / tree-sitter / def-ref / PageRank / TreeContext / token budget 思路抽象成 MapEngine，并作为 Pico 的一个增强 feature 接入，而不是直接复制 Aider 的产品控制流。

---

## 项目是什么

MapCode v1 是一个基于 Pico runtime 增量演进的本地代码仓库 coding agent。

它的第一版目标不是做一个功能庞大的通用 Coding Agent，而是验证一条最小但完整的可解释执行链路：

```text
用户提交代码仓库任务
  -> Pico 创建 run
  -> MapEngine 对 Git tracked / staged Python 文件建立结构索引
  -> MapEngine 根据用户请求生成 broad / focused repo map
  -> ContextManager 将 repo map 作为导航上下文注入主模型 prompt
  -> Pico 主模型根据 repo map 判断优先读取哪些文件
  -> Pico 通过 read_file 获取完整当前源码
  -> Pico 继续使用原有工具链完成分析、修改或报告输出
  -> trace / report / artifact 记录完整检索和执行证据
```

MapCode v1 的核心不是“模型能不能直接读完整仓库”，而是：

```text
如何在本地 coding agent runtime 中，把大仓库压缩成可解释、可追踪、可评测的导航上下文。
```

Repo map 只回答：

- 可能相关的文件在哪里。
- 可能相关的符号在哪里。
- 为什么这些文件和符号被选中。
- 在当前预算下哪些结构摘要进入 prompt。

Repo map 不回答：

- 文件完整当前内容是什么。
- 文件是否已经被模型读取。
- 文件是否可以直接修改。
- 某个调用关系是否经过完整语义验证。
- README、配置文件、CI、Dockerfile 等非代码文件表达的项目语义。

因此，MapEngine 只给 Pico 提供“代码仓库重点摘要输入”。代码修改、工具调用、审批、安全校验、fresh-read 规则、trace/report 等仍由 Pico 既有能力完成。

---

## 项目价值

MapCode v1 的项目价值不是做一个替代 Codex 或 Claude Code 的通用生产力工具，而是做一个面向工程理解和二次开发的本地 coding agent runtime：在 Pico 既有 agent loop 上接入 MapEngine，把代码仓库压缩、文件选择、上下文注入、工具调用、read_file freshness、trace、report、artifact 和 retrieval eval 串成一条可解释的执行链路。

### 为什么要做这样一个本地 coding agent

通用 coding agent 已经能完成大量代码编写、解释、调试和重构任务，但对于学习和二次开发来说，它们通常更像完整产品，内部的上下文选择、文件排序、工具调用决策、prompt 注入策略和失败降级路径并不完全以项目开发者可控的形式暴露出来。

MapCode 要解决的不是“再做一个更强的 Claude Code / Codex”，而是回答一个更底层的问题：

```text
一个本地 coding agent 如何稳定、可控、可解释地在真实代码仓库中运行？
```

因此，MapCode v1 的重点不是追求模型能力本身，而是追求 runtime 工程能力：

- 如何管理一次用户请求对应的 run 生命周期。
- 如何在主模型调用前准备仓库导航上下文。
- 如何让模型先知道“应该去哪里看”，再通过 read_file 获取完整源码。
- 如何约束模型不能把 repo map 当作完整源码。
- 如何把检索、prompt 注入、工具调用、失败降级和最终输出记录进 trace / report / artifact。
- 如何通过 retrieval eval 判断上下文选择是否有效。

### 本地 coding agent 中存在的问题

本地 coding agent 在真实代码仓库中执行任务时，常见问题不是单纯“模型不会写代码”，而是上下文和执行链路不稳定。

第一，大仓库上下文无法直接全部塞进模型窗口。代码仓库包含大量文件、符号、测试、配置和历史信息，如果简单把所有文件加入 prompt，会迅速超出上下文预算；如果完全依赖模型自己反复 list / grep / read，又会产生大量盲目探索和无效工具调用。

第二，文件选择过程不够可解释。模型可能最终读对了文件，也可能读错了文件，但如果系统没有记录为什么某个文件被选中、使用了什么 ranking 信号、哪些文件被预算裁掉，就很难复盘和评测。

第三，repo map、文件摘要和完整源码之间容易混淆。模型如果把结构摘要当作完整源码，可能在没有读取当前文件内容的情况下进行推理或修改，导致错误编辑。因此，本地 coding agent 必须明确区分：

```text
repo_map_context != full_source
repo_map_context != prior_read_authorization
repo_map_context != editable_file_content
```

第四，执行失败后需要可靠降级。如果检索模块、缓存、repo map 渲染或 artifact 落盘失败，系统不应中断主任务，而应清除增强层状态，回到 Pico 原有主执行链路继续运行。

第五，缺少面向开发者的评测闭环。coding agent 不能只看最终回答是否“看起来合理”，还应该能评测 ground-truth 文件是否进入 repo map、首个 read_file 是否命中正确文件、selector 调用了几次、broad fallback 比例是多少、上下文预算是否被合理使用。

MapCode v1 引入 MapEngine，就是为了解决这些问题中的“仓库导航上下文选择”这一层。

### 为什么引入 repo map 模块

Repo map 的作用是给主模型提供一个结构化的仓库导航视图，让模型在读取完整源码前，先知道哪些文件和符号可能重要。

MapEngine 不负责替代 Pico 的工具系统，也不负责直接修改代码。它只负责在主模型调用前完成一件事：

```text
把 Git tracked / staged Python 代码仓库压缩成可解释、可预算、可落盘、可评测的导航上下文。
```

引入 repo map 的核心价值包括：

1. 降低盲目探索成本。模型不需要完全从 list_files / grep / read_file 开始盲找，而是可以先根据 repo map 中的高 rank 文件和符号决定读取顺序。
2. 提升首轮文件命中率。对存在有效文件、symbol 或 path ident 命中的请求，MapEngine 生成 focused map；只有三类信号均无有效命中的模糊请求，才先生成 broad map，再通过 selector 和用户确认形成 focused map 或 broad fallback。
3. 支持大仓库上下文压缩。MapEngine 通过 tree-sitter def/ref、文件级引用图、PageRank / Personalized PageRank 和 TreeContext 风格渲染，把仓库结构压缩成有限预算内的导航摘要。
4. 保留确定性证据链。MapEngine 的 ranking、rendering、cache、rendered files、omitted files、focus truncation、token budget 使用等信息进入 evidence。
5. 保持安全边界。repo map 只告诉模型“应该去哪里看”，不告诉模型“可以直接编辑”。真正的代码修改仍必须经过 Pico 的 read_file freshness、工具策略和审批机制。

当前架构中需要特别记录的问题不再是“ContextManager 是否二次裁剪 repo map”，而是：

- MapEngine 独立 token budget 是否发生 budget_reduction_applied。
- ContextManager 是否发生 base_prompt_reduction_applied。
- repo map section 是否被完整注入。
- repo map section 未注入时的 omission reason。
- selector prompt 是否因为超过 ModelRequestBudget 进入 selector_request_over_budget fallback。
- path ident 命中了哪些 indexed files，其中哪些实际进入 path personalization。
- focus personalization 与 path personalization 是否被正确区分。
- Aider-style symbol multiplier 和 focus outbound boost 是否能从 ranking evidence 复盘。

### MapCode 与通用 Codex / Claude Code 的区别

MapCode 不以替代 Codex / Claude Code 为目标。Codex 和 Claude Code 是面向真实开发者生产力的通用 coding agent 产品，功能覆盖代码阅读、编辑、命令执行、Git 工作流、IDE/终端集成、多任务协作等完整开发场景。

MapCode v1 的定位不同：

```text
Codex / Claude Code 更像完整产品。
MapCode v1 更像可解释 coding agent runtime 的工程化实验底座。
```

| 对比项 | Codex / Claude Code | MapCode v1 |
|---|---|---|
| 产品目标 | 通用 AI 编程助手，面向开发者生产力 | 面向本地 coding agent runtime 的工程学习、二次开发和可解释实验 |
| 核心能力 | 读代码、改代码、运行命令、处理多文件任务、集成 IDE / CLI / Git 工作流 | 在 Pico runtime 上接入 MapEngine，验证 repo map 导航、上下文注入、trace/report/artifact/eval 闭环 |
| 上下文选择 | 产品内部完成大量上下文管理，用户通常关注结果 | 把上下文选择拆成 PromptAnalysis、GraphRanker、ContextRenderer、PromptInjectionEvidence 等可观察模块 |
| 文件选择证据 | 不一定以项目自定义 schema 暴露每个文件的 ranking、omission 和 budget 证据 | 明确落盘 map-evidence-001.json，记录 ranking、rendering、cache、selector、fallback、prompt injection |
| repo map 定位 | 作为产品内部能力或上下文机制的一部分 | 作为 MapEngine 的核心一等模块，直接服务 retrieval eval 和工程可解释性 |
| 执行控制 | 产品级 agent loop，用户主要通过提示词、配置、权限和界面控制 | 复用 Pico agent loop，重点展示 run 生命周期、Branch A/B、read_file freshness、trace/report/artifact |
| 评测重点 | 用户任务完成质量 | v1 只评测 retrieval / context selection，不评测完整代码生成质量 |
| 适用场景 | 日常开发、修 bug、重构、写测试、提交 PR 等 | 理解和实现本地 coding agent 的上下文工程、检索证据链和执行链路治理 |

MapCode 的差异化不在于“比 Codex / Claude Code 会写更多代码”，而在于它把 coding agent 的关键内部链路显式化、模块化和可评测化：

```text
用户请求
  -> PromptAnalysis
  -> broad / focused repo map
  -> ranking evidence
  -> prompt injection evidence
  -> read_file freshness
  -> tool loop
  -> trace / report / artifact
  -> retrieval eval
```

### MapCode v1 的真实价值边界

MapCode v1 的价值不是做“大而全”，而是做“小而硬”。第一版只做 Git tracked / staged Python 文件的 repo map，不做多语言、不做 embedding、不做 LSP、不做完整 call graph、不做复杂 planner。

MapCode v1 的最小价值可以总结为：

```text
让 Pico 从一个普通本地 coding agent runtime，
升级为一个具备仓库结构导航、上下文选择证据、prompt 注入记录和 retrieval eval 的可解释 coding agent runtime。
```

后续所有能力都应建立在同一条主线上：

```text
Pico runtime 负责执行。
MapEngine 负责导航。
Coordinator 负责适配。
ContextManager 负责注入。
Trace / Report / Artifact / Eval 负责解释和验证。
```

---

## 能力展示目标

### Agent Runtime 能力

MapCode v1 复用 Pico 既有 agent loop，不新增独立 planner，不新增第二套运行时。

v1 需要展示：

- 一个用户请求对应一个 Pico run。
- run 启动、执行、失败、结束和清理路径清晰。
- 主模型可以在多轮 tool loop 中继续推理和调用工具。
- MapEngine preparation 每个 run 只执行一次。
- 后续 retry / tool loop 复用同一个 finalized map context，不重复扫描、不重复 selector、不重复询问用户。
- `current_map_context` 在 run 结束后必须清理，不能泄漏到下一轮请求。
- 代码修改仍遵守 Pico 原有 `read_file` freshness 和审批机制。
- 主模型请求和 selector 请求都必须通过 `ModelRequestBudget` 门禁。

### 上下文工程能力

MapCode v1 需要展示：

- 如何只对 Git tracked / staged Python 文件建立结构索引。
- 如何通过 tree-sitter 提取 definitions / references。
- 如何建立文件级 def/ref 引用图。
- 如何通过 PageRank / Personalized PageRank 对文件和符号排序。
- 如何区分准确文件命中、symbol 命中与 path ident 命中。
- 如何保证目录样式输入只形成 path ident 信号，不形成目录 scope、文件 focus 或读取授权。
- 如何区分 `focus_personalization_files`、`path_personalization_files` 与最终 `personalization_files`。
- 如何组合应用 Aider-style prompt / structured / private / common symbol multiplier，并保留可审计证据。
- 如何区分 `MapResult.mode` 与 `RankingEvidence.algorithm`。
- 如何区分 broad map 和 focused map。
- 如何使用固定的 broad / focused 两套独立 token budget 控制 repo map 长度：broad = 8,192 tokens，focused = 4,096 tokens。
- 如何使用 `ModelRequestBudget` 作为最终模型请求输入硬上限。
- 如何把 repo map 作为独立 `repo_map` section 注入 prompt。
- 如何为完整 repo_map section 预留输入空间，再缩减 Pico 原有 base prompt section。
- 如何保证 ContextManager 不二次裁剪 MapEngine 已生成的 repo map body。
- 如何保证 repo map 只作为导航上下文，而不是完整源码或编辑授权。

### 可解释工程能力

MapCode v1 需要展示：

- 每次 MapEngine 检索都有结构化 evidence。
- 每次 run 都能通过 trace 复盘事件顺序。
- 每次成功注入 repo map 都落盘 `repo-map-001.txt` 和 `map-evidence-001.json`。
- report 只保存轻量摘要，不复制完整 evidence。
- 终端输出只展示 evidence 中已有事实，不产生新事实。
- MapEngine 失败时 Pico 原执行链继续，不让增强层成为单点故障。
- evidence 同时区分 MapEngine rendering 事实、selector / 用户确认事实、prompt injection 事实和最终 request budget 事实。
- trace / evidence 能解释每个 path ident 命中的全部 indexed files、实际图节点过滤结果和最终 personalization 输入。
- top rank contributor evidence 能解释最终 weight multiplier 及其 reason codes。

### 检索评测能力

MapCode v1 只评测 retrieval / context selection，不评测完整代码生成质量。

v1 重点评测：

- ground-truth 文件是否进入 rendered files。
- 首个 `read_file` 是否命中 ground-truth 文件。
- broad / focused repo map 使用 token 与字符数。
- 是否发生 focus truncation。
- selector 调用次数。
- selector_request_over_budget 次数。
- broad fallback 比例。
- base_prompt_reduction_applied 次数。
- repo_map omission 次数。
- 文件、symbol、path ident 三类有效信号命中情况。
- path-ident-only 请求是否进入 Branch A，且没有被错误升级为文件 focus。
- path ident 全量命中文件到 path personalization files 的过滤是否可解释。
- top rank contributor 的 multiplier / reason codes 是否准确。
- MapEngine 失败时 Pico 是否仍能正常继续。

---

## 使用场景

### 场景 1：分析代码仓库结构

用户输入：

```text
分析一下这个代码仓库
```

系统行为：

- PromptAnalysis 无有效文件、symbol 或 path ident 命中，进入 Branch B。
- MapEngine 生成 broad repo map，固定使用 8,192 token budget。
- 系统在 selector LLM 前展示 broad map 简要状态。
- MapEngine 基于同一 SymbolIndex snapshot 生成 SelectorCandidateCatalog。
- Engine 构造 selector prompt，并先通过 ModelRequestBudget 门禁。
- selector 通过预算门禁时，LLM 基于 original prompt + broad map + SelectorCandidateCatalog 建议重点文件。
- 用户可以接受全部建议或使用 broad map。
- 主模型根据最终 repo map 调用 `read_file` 阅读重点文件。
- Pico 输出仓库结构分析报告。

### 场景 2：分析指定文件或指定符号

用户输入：

```text
分析 JWTAuth 的实现
```

系统行为：

- PromptAnalyzer 从用户请求中提取 `JWTAuth`。
- 如果 `JWTAuth` 存在于 SymbolIndex definitions 中，进入 Branch A。
- MapEngine 生成 focused repo map，固定使用 4,096 token budget。
- 如果 Branch A 仅命中 symbol、未命中文件，则 `MapResult.mode=focused`，但实际 `RankingEvidence.algorithm=pagerank`。
- 精确命中的 DefinitionRecord 固定加入 focused map 候选前缀。
- 主模型优先读取 repo map 提示的相关文件。
- Pico 输出该符号的实现分析。

### 场景 3：分析目录样式输入

用户输入：

```text
分析 pico/ 目录下的文件分别起什么作用
```

系统行为：

- `pico/` 不形成目录 scope、`mentioned_files` 或 `focus_fnames`。
- PromptAnalyzer 将 `pico` 作为 path ident，与 indexed Python 文件 path terms 做大小写不敏感匹配，并记录命中的全部 indexed files。
- 存在有效 `path_ident_hits` 时直接进入 Branch A，不调用 selector、不询问用户。
- 实际存在于文件图节点的命中文件进入 `path_personalization_files`；它们不会获得 focus outbound boost。
- 主模型获得 path-personalized focused map，但仍必须通过 `read_file` 获取完整源码。

### 场景 4：修改指定代码逻辑

用户输入：

```text
修复 auth.py 中的 token validation 问题
```

系统行为：

- PromptAnalyzer 命中 `auth.py`，进入 Branch A。
- MapEngine 使用 `auth.py` 作为 `focus_fnames`，过滤出实际存在于文件图节点的 `focus_personalization_files`。
- 最终 `personalization_files` 是 focus / path personalization files 的稳定并集；非空时执行 Personalized PageRank，否则执行标准 PageRank。
- ContextManager 将完整 repo_map section 注入主模型 prompt。
- 主模型必须先调用 `read_file("auth.py")` 获取完整当前源码。
- Pico 按原有工具策略执行 patch 或 write。
- run artifacts 记录本次 repo map 和 evidence。

### 场景 5：模糊 bug 定位

用户输入：

```text
修复登录失败的问题
```

系统行为：

- PromptAnalysis 无有效文件、symbol 或 path ident 命中，进入 Branch B。
- MapEngine 先生成 broad map。
- MapEngine 构建 SelectorCandidateCatalog。
- selector prompt 超过 ModelRequestBudget 时，不调用 selector，不发送 `map_selector_requested`，不递增 selector_model_calls，直接进入 `selector_request_over_budget` broad fallback。
- selector 通过预算门禁时，Engine 发送 `map_selector_requested` 并调用 selector LLM。
- selector 输出只允许通过 SelectorCandidateCatalog.candidate_paths 校验。
- 用户接受建议后，MapEngine 生成 focused map；用户拒绝、取消、selector 无有效文件或 selector 超预算时，使用 broad fallback。
- 主模型根据 focused / broad fallback map 调用 `read_file` 定位问题。

### 场景 6：MapEngine 失败降级

用户在非 Git workspace 中运行，或 Git 文件枚举失败。

系统行为：

- MapEngine 不使用文件系统递归扫描 fallback。
- Coordinator 发送 `map_context_failed` trace。
- `current_map_context=None`。
- ContextManager 不注入 repo map。
- Pico 原有主模型流程继续执行。

---

## 第一版做什么

MapCode v1 只实现“单会话、单用户轮次、基础 MapEngine 检索与 Pico 执行闭环”。

### 1. 基于 Pico runtime 接入 MapEngine

- 在 Pico 初始化阶段装配 MapEngine 和 MapContextCoordinator。
- 启动时只初始化对象和轻量 cache metadata。
- 启动时不扫描仓库、不解析 AST、不生成 repo map。
- feature flag 默认关闭，可显式启用或禁用。
- Pico runtime 持有 `ModelRequestBudget`，作为主模型请求和 selector 请求的输入硬门禁事实源。

### 2. Git tracked Python-only 索引

- 使用 Git index 枚举 tracked / staged 文件。
- 只保留当前工作树存在的普通 `.py` 文件。
- 跳过 `.git/`、`.pico/`、虚拟环境、缓存目录和生成目录。
- 不处理 untracked Python 文件。
- 不处理非 Python 文件。
- 非 Git workspace 或 Git 枚举失败时，MapEngine 不可用，Pico 原流程继续。

### 3. SymbolIndex 与 cache

- 使用 tree-sitter query 提取 definitions / references。
- 维护 definitions_by_symbol、definitions_by_file、references_by_file、file_records。
- 生成 index_snapshot_id。
- 支持 cache hit / miss。
- parser / query / schema version 变化时缓存失效。
- `ensure_index()` 完成或复用 lazy SymbolIndex，返回 IndexStatus，不做 prompt analysis、ranking 或 rendering。

### 4. PromptAnalyzer

- 从 user_message 中提取准确文件命中 `mentioned_files` 和稳定去重的 `mentioned_idents`。
- repo-relative path、`./` path 和 repo-root 内 absolute path 只有规范化后精确命中 indexed Python 文件时才进入 `mentioned_files`。
- basename 只在原始大小写唯一命中时进入 `mentioned_files`；stem 只在大小写不敏感、长度至少为 5 且唯一命中时进入 `mentioned_files`。
- path component 和目录样式片段不进入 `mentioned_files`，而是通过大小写不敏感的 path ident matching 形成 `path_ident_hits` 与 `path_ident_hit_files`。
- `path_ident_hit_files` 保存每个 path ident 命中的全部 indexed Python 文件，不受文件图节点、PageRank 或渲染预算过滤。
- 使用 SymbolIndex definitions 得到 effective_symbol_hits。
- 判断 Branch A / Branch B。
- Branch A 条件：mentioned_files、effective_symbol_hits 或 path_ident_hits 任一非空。
- Branch B 条件：mentioned_files、effective_symbol_hits 和 path_ident_hits 均为空。
- effective_symbol_hits 用于 Branch 判断、trace、evidence、eval，并用于将精确命中的 DefinitionRecord 固定加入 focused map 候选前缀。
- path_ident_hits 用于 Branch 判断、trace、evidence、eval 和 path personalization，但不直接形成文件 focus。
- ranking 仍使用完整 mentioned_idents 作为 ident_boost_inputs，不只使用 effective_symbol_hits。

### 5. GraphRanker

- 构建文件级 def/ref 引用图。
- broad map 使用标准 PageRank。
- focused map 调用 `generate_focused()`，但实际 algorithm 由 personalization_files 决定。
- personalization_files 非空时使用 Personalized PageRank。
- personalization_files 为空时使用标准 PageRank，包括 symbol-only Branch A 和无有效图节点的 path-ident-only Branch A。
- `focus_personalization_files` 只来自 `focus_fnames` 中的实际文件图节点。
- `path_personalization_files` 只来自 path_ident_hit_files 中的实际文件图节点。
- 最终 `personalization_files` 是 focus / path personalization files 的稳定并集。
- 同一文件在每类 personalization 中最多获得一次 contribution；同时属于两类时可分别获得一次 contribution。
- mentioned_idents 用于大小写敏感的 prompt identifier edge boost。
- path_ident_hits 本身不额外触发 symbol edge boost。
- symbol 边在 PageRank 前组合应用 Aider-style prompt / structured / private / common multiplier。
- 只有 focus_personalization_files 获得 focus outbound boost；path personalization files 不升级为 focus。
- PageRank / PPR 失败或图为空时，按 repo-relative path 稳定 fallback，并记录 `algorithm="stable_path_fallback"`。
- 输出 ranking evidence，包括 node_pagerank、pagerank_norm、definition_rank_sum、reason_codes、top_rank_contributors、focus_fnames、两类 personalization files、最终 personalization_files、algorithm。
- top_rank_contributors 记录最终 weight_multiplier 与稳定 reason codes，使 symbol multiplier 和 focus outbound boost 可审计。

### 6. ContextRenderer

- 使用 TreeContext 风格渲染结构摘要。
- 支持 broad / focused 两套独立 token budget。
- broad map 固定使用 8,192 token budget。
- focused map 固定使用 4,096 token budget。
- 是否存在 focus_fnames 不改变 focused budget。
- focus 文件不能因为 Aider chat-file 语义被排除。
- focus 文件拥有更高 ranking 权重，但不承诺完整显示。
- focus 文件至少保留路径和尽可能多的顶层结构。
- 精确命中的 DefinitionRecord 固定进入 focused map 候选前缀。
- 仍无法容纳时记录 focus_truncated。
- RenderingEvidence 记录 target_tokens、target_chars、used_chars、estimated_tokens、budget_reduction_applied、focus_truncated。

### 7. Branch A / Branch B 控制流

- Engine 拥有 Branch 判断、selector 调用和用户确认。
- Coordinator 不判断 Branch，不调用 selector，不询问用户。
- Branch A 由有效文件、symbol 或 path ident 命中触发，不调用 selector、不询问用户，直接生成 focused map。
- path-ident-only Branch A 的 `focus_fnames=()`，通过 path personalization 影响 ranking，不形成目录 scope。
- Branch B 先生成 broad map，再视交互能力决定是否调用 selector。
- Branch B broad map 后必须构建 SelectorCandidateCatalog。
- selector prompt = original user_message + broad repo map + SelectorCandidateCatalog.rendered_text。
- selector prompt 必须先通过 ModelRequestBudget 门禁。
- selector prompt 超预算时，形成 `selector_request_over_budget` broad fallback。
- `selector_request_over_budget` 路径不发送 `map_selector_requested`，不递增 selector_model_calls，不调用 selector LLM。
- selector 输出路径必须存在于 SelectorCandidateCatalog.candidate_paths。
- selector 可以建议未进入 broad map、但存在于当前 SymbolIndex snapshot 的 Python 文件。
- Branch B v1 只支持两个确认选项：接受全部建议 / 使用 broad map。
- v1 不支持部分接受、增删或调整 selector 建议文件。

### 8. ContextManager prompt 注入

- ContextManager 读取 `current_map_context` 对象，而不是 repo map 字符串。
- 每个 prompt build 必须显式传入 `PromptPurpose`。
- `main_model` 和 `prompt_preview` 可注入 repo map。
- `evaluation` 和 `step_limit_summary` 不注入 repo map。
- repo map section 插入 Pico 原有上下文和 current_request 之间。
- repo map section 必须包含完整导航安全契约。
- ContextManager 不二次裁剪 MapEngine 已生成的 repo map body。
- ContextManager 先为完整 repo_map section 预留 ModelRequestBudget 输入空间，再缩减 Pico 原有 base prompt section。
- 如果 base prompt 在 reduction 和允许的 auto-compaction 后仍无法与 repo map 同时容纳，Engine 清除 `current_map_context`，丢弃含 repo map prompt，重建无 repo map prompt 后继续。
- 如果无 repo map prompt 仍超过 ModelRequestBudget，Engine/runtime 不发起 provider 调用，走 Pico 统一的预请求失败路径。

### 9. Artifact / Trace / Report

- 当前 run 成功注入 repo map 后写入：
  - `.pico/runs/<run_id>/artifacts/repo-map-001.txt`
  - `.pico/runs/<run_id>/artifacts/map-evidence-001.json`
- `repo-map-001.txt` 保存首次主模型实际使用的 repo_map section。
- `map-evidence-001.json` 保存完整检索证据、控制决策和 prompt injection evidence，不保存完整 repo map 文本。
- `map-evidence-001.json` 保存 path ident 全量命中文件、实际图节点过滤、两类 personalization 和 ranking multiplier evidence。
- trace 记录 map_index_status、map_prompt_analyzed、map_context_ranked、map_context_selected、map_selector_requested、map_focus_confirmed、map_generated、map_context_failed 等事件。
- map_prompt_analyzed 记录文件、identifier、symbol hit、path ident hit、path ident hit files 和最终 branch。
- map_context_ranked 记录两类 personalization files、最终 personalization files 和 contributor multiplier evidence。
- report 保存轻量摘要和 artifact path。
- 证据落盘失败时不发送含 repo map prompt，清除 current_map_context 并重建无 repo map prompt。

### 10. 最小 retrieval eval

- 使用固定 Python fixture repo。
- 评测 ground-truth 文件是否进入 rendered files。
- 评测首个 read_file 是否命中 ground-truth。
- 评测 repo map tokens / chars、focus truncation、selector 调用数、fallback 比例。
- 评测 ModelRequestBudget 相关路径：selector_request_over_budget、base_prompt_reduction_applied、repo_map omission、request_over_budget。
- 评测文件、symbol、path ident 有效命中，path-ident-only Branch A，path personalization 过滤和 ranking contributor 可解释性。

---

## 第一版不做什么

MapCode v1 明确不做以下内容：

1. 不重建独立 Agent loop。
2. 不新增独立 planner。
3. 不新增第二套 SessionManager。
4. 不新增第二套 ToolRegistry。
5. 不新增第二套 Approval 系统。
6. 不新增第二套 TraceWriter。
7. 不新增 child runtime / worker 的 MapEngine 能力。
8. 不在同一 run 内根据文件修改自动刷新 repo map。
9. 不实现多用户、多会话协同。
10. 不实现 Aider add-to-chat 文件状态机。
11. 不实现 editable / read-only / chat file 状态机。
12. 不引入 embedding。
13. 不引入 LSP。
14. 不引入语义向量检索。
15. 不承诺准确 call graph。
16. 不承诺完整影响分析。
17. 不把 repo map 当作完整源码。
18. 不把 repo map 当作 prior-read 凭证。
19. 不让 repo map 绕过 Pico 的 `read_file` freshness 规则。
20. 不把 README、Dockerfile、CI workflow、配置文件等非 Python 文件纳入 SymbolIndex、PageRank 或 repo map。
21. Git 文件枚举失败时，不回退到文件系统递归扫描。
22. 不评测完整代码修复成功率。
23. 不整体复制 Aider RepoMap 类。
24. 不在 MapCode 代码中直接 `import aider.*`。
25. 不引入 `mentioned_dirs`，不把目录样式输入解释为目录 scope、目录硬过滤或文件 focus。
26. 不把 path ident 命中当作 prior-read / read_file 授权。
27. 不移植 Aider 为无引用 definition 添加的 `0.1` 自环。

---

## 功能模块

MapCode v1 按产品 / 工程能力分为 8 个模块。

## 模块 1：Pico Runtime Shell

### 职责

Pico Runtime Shell 是 MapCode v1 的工程底座，负责运行本地 coding agent 的主链路。

### 功能

- 创建和管理 Pico run。
- 持有模型 provider、工具系统、ContextManager、RunStore、SessionEventBus、Trace / Report 能力。
- 持有并向 Engine / ContextManager 暴露 ModelRequestBudget。
- 初始化 MapEngine 和 MapContextCoordinator。
- 管理 `current_map_context` 生命周期。
- 在 MapEngine 失败时继续执行 Pico 原有主流程。
- 在 run 完成、失败或停止时清理 `current_map_context`。
- 在 selector 请求和主模型请求前执行输入预算门禁。

### 输入

- CLI / TUI 用户请求。
- Pico 配置。
- MapEngine feature flag。
- workspace repo root。
- provider/model 输入预算信息。

### 输出

- Pico run。
- runtime.current_map_context。
- ModelRequestBudget。
- trace/report/artifact。
- 主模型调用结果。
- 工具执行结果。

---

## 模块 2：MapEngine 仓库结构索引

### 职责

对 Git tracked / staged Python 文件建立可用于 repo map 的 symbol/ref 索引，并维护可复用的 index snapshot。

### 功能

- 以 Git repo root 作为工作目录。
- 使用 `git ls-files --cached -z` 枚举 tracked / staged 文件。
- 过滤出当前工作树存在的普通 `.py` 文件。
- 使用 tree-sitter query 提取 Definition / Reference。
- 维护 definitions_by_symbol、definitions_by_file、references_by_file、file_records。
- 维护 cache metadata。
- 生成 index_snapshot_id。
- 记录 skipped_files、parsed_files、reused_files。
- 对外提供 `ensure_index()`，只负责 lazy index，不负责 prompt analysis / ranking / rendering。

### 输入

- workspace.repo_root。
- Git index。
- Python 源码文件。
- parser_version。
- query_version。
- schema_version。
- cache metadata。

### 输出

- SymbolIndex。
- IndexStatus。
- index_snapshot_id。
- cache_status。
- map_index_status trace payload。

---

## 模块 3：PromptAnalyzer 请求信号分析

### 职责

从用户请求中提取文件、路径、identifier 和 symbol 命中信号，并决定 Branch A / Branch B。

### 功能

- 规范化并验证 repo-relative、`./` repo-relative 和 repo-root 内 absolute file path。
- 保守提取唯一 basename 与唯一 stem 文件命中。
- 使用 Aider-style identifier 提取规则形成 mentioned_idents。
- 与 SymbolIndex.all_defs 对齐得到 effective_symbol_hits。
- 使用 normalized lowercase path terms 形成 path_ident_hits 与全量 path_ident_hit_files，同时在 evidence 中保留原始 ident。
- 根据 mentioned_files、effective_symbol_hits 和 path_ident_hits 判断 branch。
- 保证 path component 和目录样式输入不形成 mentioned_files、focus_fnames 或目录过滤。
- 生成 PromptAnalysis。
- 为 focused map 候选前缀提供精确命中的 DefinitionRecord。

### 输入

- user_message。
- SymbolIndex.all_defs。
- repo 文件路径集合。

### 输出

- PromptAnalysis：branch、mentioned_files、mentioned_idents、effective_symbol_hits、path_ident_hits、path_ident_hit_files。

---

## 模块 4：GraphRanker 排名与 focus / broad 预算

### 职责

基于 def/ref 图对文件和符号进行 PageRank / Personalized PageRank 排名，并输出可解释 ranking evidence。

### 功能

- 构建文件级引用图：`referencer file --identifier--> definer file`。
- broad map 使用标准 PageRank。
- focused map 根据 personalization_files 决定实际算法。
- personalization_files 非空时使用 Personalized PageRank。
- personalization_files 为空时使用标准 PageRank。
- 从 focus_fnames 过滤得到 focus_personalization_files。
- 从 path_ident_hit_files 过滤得到 path_personalization_files。
- 合并两类 contribution 形成最终 personalization_files。
- mentioned_idents 对相关引用边进行 prompt ident boost，并与 structured / private / common symbol multiplier 组合。
- 只有 focus_personalization_files 对 focus 文件出站边进行 outbound boost。
- PageRank 失败或空图时使用 stable_path_fallback。
- 记录 `MapResult.mode` 与 `RankingEvidence.algorithm` 的区别。
- 记录 contributor 的最终 weight_multiplier 与 weight_reason_codes。

### 输入

- SymbolIndex.definitions_by_symbol。
- SymbolIndex.references_by_file。
- PromptAnalysis.mentioned_idents。
- PromptAnalysis.path_ident_hit_files。
- focus_fnames。
- ranking config。

### 输出

- ranked files。
- ranked definitions。
- ranked tags。
- RankingEvidence。
- RenderedFileEvidence / OmittedFileEvidence 所需 ranking 字段。

---

## 模块 5：ContextRenderer / repo map 渲染

### 职责

将排名后的文件和符号渲染为 TreeContext 风格 repo map，并执行 MapEngine 层的独立 token budget 选择。

### 功能

- 根据 ranked tags 渲染结构摘要。
- 生成 broad repo map。
- 生成 focused repo map。
- broad map 固定使用 8,192 token budget。
- focused map 固定使用 4,096 token budget。
- focus_fnames 不改变 focused budget。
- focus 文件存在时不从 repo map 排除。
- 预算不足时优先保留高 rank 内容。
- focus 文件无法完整容纳时至少保留路径并记录 focus_truncated。
- 精确命中的 DefinitionRecord 固定进入 focused map 候选前缀。
- 记录 rendered_files、rendered_symbols、omitted_files。
- 生成 RenderingEvidence。

### 输入

- ranked files。
- ranked tags。
- definitions_by_file。
- focus_fnames。
- broad / focused token budget。

### 输出

- repo_map_text。
- rendered_files。
- rendered_symbols。
- RenderingEvidence。
- MapResult。

---

## 模块 6：MapContextCoordinator 数据适配与 artifact 落盘

### 职责

MapContextCoordinator 是 Pico runtime 与 MapEngine 之间的数据面 adapter。它只接受 Engine 已经形成的命令或决策，调用 MapEngine，组装 MapContextResult，写 trace/artifact/report 所需数据。

### 功能

- analyze_turn：调用 MapEngine.ensure_index 和 MapEngine.analyze。
- prepare_specific：调用 MapEngine.generate_focused。
- prepare_broad：调用 MapEngine.generate_broad。
- build_selector_catalog：基于同一 SymbolIndex snapshot 调用 MapEngine.build_selector_catalog。
- prepare_fuzzy / finalize_fuzzy：根据 SelectionDecision 生成 focused map 或复用 broad map。
- finalize_prompt_context：根据首次 main_model build 的 RepoMapSectionRender 写 artifact。
- 组装 prepared / finalized MapContextResult。
- 调用 runtime.emit_trace 写 MapEngine 相关事件。
- 在 MapEngine 异常或证据落盘失败时设置 current_map_context=None，并让 Pico 原流程继续。

### 输入

- TaskState。
- user_message。
- PromptAnalysis。
- MapResult。
- SelectorCandidateCatalog。
- SelectionDecision。
- RepoMapSectionRender。

### 输出

- MapContextResult。
- repo-map-001.txt。
- map-evidence-001.json。
- trace payload。
- report map_context summary。

---

## 模块 7：Engine Branch A/B 控制流与 selector 确认

### 职责

Engine 是当前 run 的控制面，负责决定 Branch A / Branch B，编排 selector LLM 和用户确认，并决定何时进入主模型/tool loop。

### 功能

- 创建 TaskState 和 run 目录。
- 执行 MapContext preparation。
- 根据 PromptAnalysis.branch 进入 Branch A 或 Branch B。
- Branch A：直接请求 Coordinator 生成 focused map。
- Branch B：先请求 Coordinator 生成 broad map。
- Branch B：在 selector LLM 前展示 broad map 状态。
- Branch B：请求 Coordinator 构建 SelectorCandidateCatalog。
- Branch B：构造 selector prompt 并执行 ModelRequestBudget 门禁。
- selector_request_over_budget：不调用 selector、不发送 map_selector_requested、不增加 selector_model_calls、直接 broad fallback。
- selector 通过预算门禁：发送 map_selector_requested，调用 selector LLM。
- 校验 selector 输出路径只能来自 SelectorCandidateCatalog.candidate_paths。
- 调用 runtime.ask_user，提供“接受全部建议 / 使用 broad map”两项。
- 形成 SelectionDecision。
- 调用 Coordinator.prepare_fuzzy / finalize_fuzzy。
- 控制首次 main_model prompt build 和 artifact 落盘顺序。
- 成功落盘后发起主模型调用。
- 失败落盘时丢弃含 repo map prompt，重建无 repo map prompt。

### 输入

- user_message。
- PromptAnalysis。
- broad MapResult。
- SelectorCandidateCatalog。
- selector raw output。
- 用户确认结果。
- runtime 交互能力状态。
- ModelRequestBudget。

### 输出

- SelectionDecision。
- prepared / finalized current_map_context。
- map_selector_requested trace。
- map_focus_confirmed trace。
- 主模型请求。

---

## 模块 8：ContextManager prompt 注入、Trace / Report / Eval

### 职责

ContextManager 负责在 prompt build 阶段读取 current_map_context，把 repo map 作为独立 section 注入主模型 prompt，并返回当前 build 独立的 repo map render 结果。

Trace / Report / Eval 负责让本次检索、注入和执行链路可解释、可复盘、可评测。

### 功能

- ContextManager 读取 MapContextResult 对象。
- ContextManager 读取 ModelRequestBudget。
- 根据 PromptPurpose 决定是否注入 repo map。
- 生成完整导航安全契约。
- 生成 branch / mode / focus / fallback notice 状态行。
- 将 repo map section 插入 current_request 前。
- 不二次裁剪 MapEngine 已生成的 repo map body。
- 为完整 repo_map section 预留输入空间。
- 缩减 Pico 原有 base prompt section。
- 如果 repo map 与 base prompt 无法同时满足 ModelRequestBudget，则整段省略 repo map，并由 evidence 记录 omission reason。
- 返回 PromptBuildResult.repo_map_render。
- trace 记录检索和 prompt 构建事件。
- trace / report 展示文件、symbol、path ident 信号，两类 personalization 和 ranking contributor evidence。
- report 保存 run 级轻量摘要。
- eval 统计 retrieval、path ident personalization 和 ranking 可解释性指标。

### 输入

- current_map_context。
- user_message。
- PromptPurpose。
- ModelRequestBudget。
- MapEvidenceArtifact。
- trace events。
- evaluation fixture。

### 输出

- PromptBuildResult。
- RepoMapSectionRender。
- PromptInjectionEvidence。
- prompt_built trace。
- report.json。
- retrieval eval result。

---

## 文件结构

推荐在 Pico 当前目录结构上增量加入以下文件：

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
│
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

路径职责：

```text
features/map_engine/
  放 MapEngine 自有能力：
  - Git 文件枚举
  - tree-sitter 索引
  - prompt analysis
  - graph ranking
  - repo map rendering
  - selector candidate catalog
  - MapResult / MapContextEvidence

core/
  放 Pico runtime 接入能力：
  - Engine Branch A/B 控制流
  - ModelRequestBudget 门禁
  - MapContextCoordinator
  - selector prompt / parser / confirmation DTO
  - repo_map prompt section 渲染
  - ContextManager purpose 注入
  - RunStore artifact 写入
  - Trace / Report 集成
```

核心边界：

```text
features/map_engine 不依赖 Pico runtime。
core/map_context 负责连接 Pico run 生命周期和 MapEngine 确定性结果。
Engine 拥有控制流。
Coordinator 只做数据适配。
ContextManager 只做 prompt 注入和 base prompt budget 协调。
```

MapEngine v1 对外接口（以 `SPEC_v1_4.md` 为准）：

```python
class MapEngine:
    def ensure_index(self) -> IndexStatus: ...
    def analyze(self, prompt: str) -> PromptAnalysis: ...
    def generate_broad(self, analysis: PromptAnalysis) -> MapResult: ...
    def build_selector_catalog(self) -> SelectorCandidateCatalog: ...
    def generate_focused(
        self,
        analysis: PromptAnalysis,
        focus_fnames: tuple[str, ...],
    ) -> MapResult: ...
```

---

## 系统架构

```text
┌─────────────────────────────────────────────────────────────┐
│                         User / CLI                          │
└──────────────────────────────┬──────────────────────────────┘
                               │ user_message
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                      Pico Runtime Shell                     │
│ provider / tools / approval / history / trace / RunStore     │
│ ModelRequestBudget / current_map_context                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                            Engine                           │
│ run lifecycle / Branch A-B / selector / confirmation         │
│ ModelRequestBudget gate / final main model request           │
└───────────────┬───────────────────────────────┬─────────────┘
                │ deterministic command          │ selector/control decision
                ↓                               ↓
┌─────────────────────────────────────────────────────────────┐
│                   MapContextCoordinator                     │
│ adapter / trace emit / artifact persist / MapContextResult   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                          MapEngine                          │
│ ensure_index -> analyze -> rank -> render -> selector catalog│
└──────────────────────────────┬──────────────────────────────┘
                               │ MapResult + Evidence
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                   runtime.current_map_context               │
│                  prepared -> finalized object               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                       ContextManager                        │
│ PromptPurpose / repo_map section / base prompt reduction     │
└──────────────────────────────┬──────────────────────────────┘
                               │ prompt + repo_map
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                    Pico Main Model / Tool Loop              │
│        repo map navigation -> read_file -> patch/write       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ↓
┌─────────────────────────────────────────────────────────────┐
│                Trace / Report / Run Artifacts / Eval        │
└─────────────────────────────────────────────────────────────┘
```

---

## 操作数据流

### 操作流

```text
用户进入 Git 管理的 Python 仓库目录
  ↓
启动 Pico CLI，并启用 MapEngine feature flag
  ↓
Pico runtime 初始化 MapEngine / Coordinator 对象和 ModelRequestBudget
  ↓
启动阶段不扫描仓库、不解析 AST、不生成 repo map
  ↓
用户输入任务
  ↓
Engine 创建 TaskState 和 run 目录
  ↓
Coordinator 调用 MapEngine.ensure_index()
  ↓
MapEngine 枚举 Git tracked / staged Python 文件
  ↓
MapEngine 使用 tree-sitter 提取 definitions / references
  ↓
MapEngine 生成 SymbolIndex、IndexStatus 和 index_snapshot_id
  ↓
PromptAnalyzer 分析用户请求，生成 PromptAnalysis
  ↓
Engine 根据 PromptAnalysis 判断 Branch A 或 Branch B
  ↓
Branch A：文件、symbol 或 path ident 任一有效命中，生成 fixed-budget focused map
  ↓
Branch B：三类信号均无有效命中，先生成 fixed-budget broad map
  ↓
Branch B：构建 SelectorCandidateCatalog
  ↓
Branch B：selector prompt 经过 ModelRequestBudget 门禁
  ↓
Branch B：selector 超预算则 broad fallback；通过则 selector + 用户确认
  ↓
Coordinator 组装 prepared MapContextResult
  ↓
runtime.current_map_context = prepared MapContextResult
  ↓
ContextManager 执行首次 purpose="main_model" prompt build
  ↓
ContextManager 预留完整 repo_map section 空间，缩减 base prompt，不二次裁剪 map body
  ↓
Coordinator 写 repo-map-001.txt 和 map-evidence-001.json
  ↓
落盘成功：runtime.current_map_context 替换为 finalized MapContextResult
  ↓
落盘失败：清除 current_map_context，丢弃含 repo map prompt，重建无 repo map prompt
  ↓
Engine 发起主模型调用
  ↓
主模型根据 repo map 判断优先读取文件
  ↓
Pico 调用 read_file 获取完整当前源码
  ↓
Pico 根据完整源码分析、修改或输出报告
  ↓
run 结束，写 report，清理 current_map_context
```

### 数据流

#### 1. 用户请求进入

输入：

```text
user_message
workspace.repo_root
feature_flags
ModelRequestBudget
```

输出：

```text
TaskState
run_id
trace 写入能力
```

#### 2. Lazy Index

输入：

```text
workspace.repo_root
Git index
cache.meta.json
index.json
```

输出：

```text
SymbolIndex
IndexStatus
index_snapshot_id
CacheEvidence
map_index_status trace
```

#### 3. PromptAnalysis

输入：

```text
user_message
SymbolIndex.all_defs
repo file paths
```

输出：

```text
PromptAnalysis(
  mentioned_files,
  mentioned_idents,
  effective_symbol_hits,
  path_ident_hits,
  path_ident_hit_files,
  branch
)
map_prompt_analyzed trace
```

#### 4. Branch A 数据流

触发：

```text
mentioned_files 非空
OR effective_symbol_hits 非空
OR path_ident_hits 非空
```

处理：

```text
Engine -> Coordinator.prepare_specific()
Coordinator -> MapEngine.generate_focused(analysis, focus_fnames=analysis.mentioned_files)
MapEngine -> GraphRanker
  -> focus_fnames 过滤为 focus_personalization_files
  -> path_ident_hit_files 过滤为 path_personalization_files
  -> 合并为 personalization_files
  -> ContextRenderer
```

输出：

```text
focused MapResult
MapContextEvidence
prepared MapContextResult
map_context_ranked trace
map_context_selected trace
```

#### 5. Branch B 数据流

触发：

```text
mentioned_files 为空
AND effective_symbol_hits 为空
AND path_ident_hits 为空
```

处理：

```text
Coordinator.prepare_broad()
  -> MapEngine.generate_broad()
  -> broad repo map
  -> broad_ready display

Coordinator / MapEngine.build_selector_catalog()
  -> SelectorCandidateCatalog

Engine builds selector prompt
  -> ModelRequestBudget gate
  -> selector_request_over_budget broad fallback
  OR selector LLM + ask_user confirmation

Coordinator.prepare_fuzzy()
  -> confirmed files: generate_focused()
  -> fallback: reuse broad MapResult
```

输出：

```text
SelectionDecision
focused MapResult 或 broad fallback MapResult
prepared MapContextResult
```

#### 6. Prompt 注入数据流

输入：

```text
prepared MapContextResult
PromptPurpose="main_model"
user_message
ModelRequestBudget
```

处理：

```text
ContextManager.build()
  -> render full repo_map section
  -> estimate repo_map reservation tokens
  -> compute base_prompt_budget_tokens
  -> reduce base prompt sections
  -> return PromptBuildResult.repo_map_render
```

输出：

```text
PromptBuildResult.prompt
PromptBuildResult.repo_map_render
PromptBuildResult.metadata
```

#### 7. Artifact 落盘数据流

输入：

```text
MapContextResult
RepoMapSectionRender
MapResult
MapContextEvidence
SelectionDecision
TaskState
```

输出：

```text
repo-map-001.txt
map-evidence-001.json
finalized MapContextResult
map_generated trace
```

失败输出：

```text
map_context_failed trace
current_map_context=None
无 repo map prompt rebuild
```

#### 8. 主模型与工具数据流

输入：

```text
Pico prompt
repo_map section
user request
Pico tools
```

处理：

```text
model reads repo map as navigation
  -> decides files to inspect
  -> calls read_file
  -> receives full current source
  -> reasons over full source
  -> calls patch_file / write_file when needed
```

输出：

```text
analysis result
code modification
tool observations
prompt_built trace
model/tool trace
report.json
```

---

## 验收标准

### Runtime 验收

1. MapEngine 可通过 feature flag 启用或禁用。
2. MapEngine 禁用时，Pico 原有测试和行为保持不变。
3. Pico 启动时只初始化 MapEngine 对象，不扫描仓库、不生成 repo map。
4. `current_map_context` 保存 MapContextResult 对象，不保存字符串。
5. 每个 run 只执行一次 MapContext preparation。
6. 首次 main_model build 后，prepared MapContextResult 被 finalized MapContextResult 替换。
7. 后续 retry / tool loop 复用 finalized MapContextResult。
8. run 结束、失败、停止、step limit 等所有退出路径都清理 `current_map_context`。
9. child runtime 默认禁用 MapEngine。
10. ModelRequestBudget 作为 selector 请求和主模型请求的统一输入硬门禁。

### MapEngine 验收

1. MapEngine 不调用 LLM。
2. MapEngine 不调用 `runtime.ask_user()`。
3. MapEngine 不写 trace。
4. MapEngine 不写 RunStore。
5. MapEngine 只索引 Git tracked / staged Python 文件。
6. untracked Python 文件不进入 repo map。
7. 非 Python 文件不进入 SymbolIndex、PageRank 或 repo map。
8. 非 Git workspace 或 Git 文件枚举失败时，不回退到递归扫描。
9. tree-sitter 可提取 definitions / references。
10. cache hit 时未变化文件不重复解析。
11. parser / query / schema version 变化时缓存失效。
12. index_snapshot_id 稳定生成。
13. PageRank / PPR 排名结果保留 evidence。
14. 空图或 PageRank 失败时使用 stable_path_fallback。
15. 不存在 `import aider.*`。
16. 准确路径只有在规范化后精确命中 indexed Python 文件时进入 mentioned_files；目录、路径前缀和 repo root 外路径不得进入。
17. basename / stem 匹配遵守保守唯一候选规则，path component 不进入 mentioned_files。
18. path ident matching 大小写不敏感，但 evidence 保留 prompt 原始 ident 和全部匹配 indexed files。
19. focus_fnames 只记录明确文件 focus；path ident 命中文件不进入 focus_fnames。
20. focus_personalization_files 与 path_personalization_files 分开记录，最终 personalization_files 是两者稳定并集。
21. 同一文件在每类 personalization 中最多获得一次 contribution，同时属于两类时分别贡献一次。
22. path_ident_hits 本身不额外触发 symbol edge boost，只有 focus personalization files 获得 focus outbound boost。
23. Aider-style prompt / structured / private / common symbol multiplier 在 PageRank 前组合应用，并可从 contributor evidence 复盘。
24. 不添加 Aider 无引用 definition `0.1` 自环。

### Budget 验收

1. broad map 固定使用 8,192 token budget。
2. focused map 固定使用 4,096 token budget。
3. 是否存在 focus_fnames 不改变 focused budget。
4. 无法完整容纳 focus 结构时显式记录 truncation。
5. repo map body 不参与 Pico 原有 section reduction。
6. ContextManager 不二次裁剪 MapEngine 已生成的 repo map body。
7. 完整 repo_map section 预留必须计入最终 ModelRequestBudget。
8. base prompt reduction 只作用于 Pico 原有 base prompt section。
9. repo map 与 base prompt 无法共存时，Engine 清除 current_map_context 并重建无 repo map prompt。
10. 无 repo map prompt 仍超过 ModelRequestBudget 时，不发起 provider 调用。

### Branch A/B 验收

1. Branch A 由 mentioned_files、effective_symbol_hits 或 path_ident_hits 任一有效命中触发。
2. Branch A 不调用 selector。
3. Branch A 不询问用户。
4. Branch A 直接生成 focused map。
5. path-ident-only Branch A 的 focus_fnames 为空，通过 path personalization 影响 ranking，且不形成目录 scope。
6. Branch B 仅在文件、symbol 和 path ident 均无有效命中时触发。
7. Branch B 先生成 broad map。
8. Branch B broad 摘要在 selector LLM 前展示。
9. Branch B 构建 SelectorCandidateCatalog。
10. selector 输出校验基于 SelectorCandidateCatalog.candidate_paths。
11. selector 可以建议未进入 broad map、但存在于当前 SymbolIndex snapshot 的 Python 文件。
12. selector prompt 超过 ModelRequestBudget 时，直接 selector_request_over_budget broad fallback。
13. selector_request_over_budget 路径不发送 map_selector_requested，不递增 selector_model_calls。
14. 交互模式 Branch B 最多调用一次 selector。
15. Branch B 只支持“接受全部建议 / 使用 broad map”。
16. v1 不支持部分接受、增删或调整建议文件。
17. `map_focus_confirmed` 只在用户接受全部有效建议且 confirmed files 非空时发送。
18. selector 无有效建议时不调用 `ask_user()`，直接 broad fallback。
19. one-shot 模式不调用 selector，不询问用户，直接 broad fallback。

### Prompt 注入验收

1. 所有 prompt build 调用点必须显式提供 PromptPurpose。
2. `main_model` 注入 repo map。
3. `prompt_preview` 可注入 repo map，但不写 artifact。
4. `evaluation` 不注入 repo map。
5. `step_limit_summary` 不注入 repo map。
6. repo_map section 位于 Pico 原有上下文和 current_request 之间。
7. 存在 MapContext 时，repo_map section 必须包含完整导航安全契约。
8. MapContext 不存在时，不注入空 repo_map section。
9. broad fallback 使用统一 fallback notice，且不错误声称 selector 没有识别出文件。
10. ContextManager 返回 build-local RepoMapSectionRender，不保存 `last_map_section_render`。
11. 导航安全契约不进入 Pico 全局 prefix。

### Artifact / Trace / Report 验收

1. 成功注入 repo map 后写 `repo-map-001.txt`。
2. 成功注入 repo map 后写 `map-evidence-001.json`。
3. `repo-map-001.txt` 保存首次主模型实际使用的完整 repo_map section。
4. `map-evidence-001.json` 保存完整检索和控制证据。
5. `map-evidence-001.json` 不保存完整 repo map 文本。
6. 证据落盘失败时，不发送含 repo map 的 prompt。
7. 证据落盘失败时，清除 current_map_context，重建无 repo map prompt。
8. trace 可复盘 map_index_status、map_prompt_analyzed、map_context_ranked、map_context_selected、map_generated。
9. `map_context_failed` 只表示增强层异常，不表示正常 broad fallback。
10. map_prompt_analyzed 可复盘完整 path_ident_hit_files 和最终 branch。
11. map_context_ranked 可复盘 focus/path personalization files、最终 personalization files 和 contributor multiplier evidence。
12. report 保存 branch、stage、focus_fnames、focus/path personalization files、path ident 摘要、rendered_files、selector_model_calls、artifact path 等轻量摘要。
13. 终端输出只展示 evidence 中已有事实。

### 安全边界验收

1. Repo map 只作为导航上下文。
2. Repo map 不代表完整源码。
3. Repo map 不满足 prior-read / freshness requirement。
4. Pico 修改已有文件前必须调用 `read_file`。
5. `patch_file` / `write_file` 仍遵守 Pico 原有工具策略。
6. 主模型不能仅凭 repo map 直接修改文件。

---

## 评测方案

MapCode v1 只做 retrieval / context selection 评测，不评测完整代码生成质量。

### 评测目标

验证 MapEngine 是否能在不读取完整仓库的情况下，将相关文件和符号压缩进 repo map，并引导 Pico 主模型优先读取正确文件。

### 最小评测 fixture

使用固定 Python fixture repo，例如：

```json
{
  "request": "fix token validation in JWTAuth",
  "ground_truth_files": ["auth.py"]
}
```

### 指标 1：Rendered File Hit

定义：

```text
ground_truth_files 是否出现在 MapResult.rendered_files 中
```

### 指标 2：First read_file Hit

定义：

```text
Pico 主模型第一次 read_file 调用是否命中 ground_truth_files
```

### 指标 3：Repo Map Budget Usage

定义：

```text
focused_map_used_tokens / 4096
broad_map_used_tokens / 8192
used_chars / target_chars
```

### 指标 4：Focus Truncation

定义：

```text
focus_truncated 是否为 true
```

### 指标 5：Selector Calls

定义：

```text
selector_model_calls
```

### 指标 6：Broad Fallback Ratio

定义：

```text
broad fallback runs / total fuzzy runs
```

### 指标 7：Selector Request Over Budget Count

定义：

```text
selector_request_over_budget fallback 次数
```

### 指标 8：Base Prompt Reduction Count

定义：

```text
base_prompt_reduction_applied 次数
```

### 指标 9：Repo Map Omission Count

定义：

```text
repo_map section_rendered=False 的次数，以及对应 omission_reason
```

### 指标 10：Selector Catalog Truncation Count

定义：

```text
SelectorCandidateCatalog.truncated 为 true 的次数
```

### 指标 11：Selector Excess Files Count

定义：

```text
SelectorResult.excess_files 数量
```

### 指标 12：MapEngine Failure Degradation

定义：

```text
MapEngine preparation 失败或证据落盘失败时，Pico 是否继续主流程
```

### 指标 13：Prompt Signal Hit Coverage

定义：

```text
文件、symbol、path ident 三类有效信号的命中情况
```

### 指标 14：Path Ident Branch Accuracy

定义：

```text
path-ident-only 请求是否进入 Branch A，且 mentioned_files=()、focus_fnames=()
```

### 指标 15：Path Personalization Evidence

定义：

```text
path_ident_hit_files 是否完整记录全部 indexed file matches，
并能解释到 path_personalization_files 的文件图节点过滤
```

### 指标 16：Path Ident Rendered File Hit

定义：

```text
path ident 命中的 ground-truth 文件是否进入 path_personalization_files 和 rendered_files
```

### 指标 17：Ranking Contributor Explainability

定义：

```text
top rank contributor 的 weight_multiplier / weight_reason_codes 是否准确反映
prompt / structured / private / common symbol multiplier 与 focus outbound boost
```

### v1 不评测

- 不评测完整代码修复成功率。
- 不评测生成 patch 的业务正确性。
- 不评测多语言仓库能力。
- 不评测 README / 配置文件语义理解。
- 不评测跨 run repo map 自动刷新。
- 不评测复杂 call graph 精度。

---

## 后续迭代优化方向

MapCode v1 完成后，后续可以围绕“更强的仓库理解、更稳定的长期运行、更深的 Git 融合、更完整的评测闭环”继续演进。

### 方向 1：多轮对话中的 repo map 刷新策略

v1 一个 run 内不根据文件修改刷新 repo map。后续可以参考 Aider 的 auto / always / files / manual 等模式，设计多轮会话下的 repo map 刷新策略。

### 方向 2：文件状态管理

后续可以增加文件状态：

```text
chat files
read-only files
editable files
repo-map-only files
unread files
fresh-read files
```

但必须避免把 focus_fnames 和“文件已完整进入 prompt”混用。

### 方向 3：更完整的缓存策略

v1 只实现基础 SymbolIndex cache。后续可以扩展 tag cache、TreeContext render cache、graph ranking cache、repo map snapshot cache、按 Git commit / branch 管理 cache。

### 方向 4：Git 深度融合

后续可以围绕 Git 做更强的执行治理：branch/session 绑定、commit/checkpoint 绑定、AI 修改独立 commit、AI commit message 自动生成、人类提交和 AI 提交区分、checkpoint / resume、基于 diff 的代码修改影响分析。

### 方向 5：更多语言支持

v1 只支持 Python。后续可以扩展 JavaScript / TypeScript、Java、Go、Rust、多语言 tree-sitter query 管理和多语言 ranking evidence 对齐。

### 方向 6：更强的上下文选择

后续可以引入 LSP symbol、embedding 检索、BM25、hybrid retrieval、call graph、impact analysis、README / 配置文件 / CI workflow 的项目级语义摘要。

### 方向 7：更完整的 eval

后续可以扩展多任务 retrieval benchmark、read_file 命中率、patch success rate、test pass rate、token cost、selector 成本收益、broad vs focused 对比实验、MapEngine on/off A/B 实验。

### 方向 8：产品化命名清理

v1 开发阶段保留 Pico 内部命名和目录结构。MapEngine 功能跑通后，再逐步清理外露命名，将项目包装为 MapCode。

原则：

```text
先做实功能，再清理命名。
不要为了改名破坏 Pico 现有 runtime 边界。
```

---

## 开发硬约束

本节用于约束 Claude Code / Codex 执行开发时的行为。

1. 所有功能增量必须基于 Pico 当前代码结构进行。
2. 不允许另起一个新项目。
3. 不允许重建一套 runtime。
4. 不允许复制拼接 Pico / Aider 的零散代码形成并行系统。
5. MapEngine 必须作为 Pico 的增强 feature 接入。
6. Engine 拥有控制流。
7. MapEngine 只做确定性检索。
8. Coordinator 只做数据适配。
9. ContextManager 只做 prompt 注入和 base prompt budget 协调。
10. Trace / Report / RunStore 必须复用 Pico 既有能力。
11. Aider 只能作为 Repo Map 算法和行为参考。
12. 不允许在 MapCode 代码中直接 `import aider.*`。
13. 每完成一个阶段必须补充对应单元测试或集成测试。
14. 任何实现如果会破坏 Pico 原有行为，必须优先保证 MapEngine disabled 时 Pico 原测试通过。
15. 遇到 SPEC / FuncFlow / PRD 冲突时，优先级为：

```text
SPEC_v1_4.md > PRD_v1_2.md > FuncFlow_v1_4.md > 临时实现想法
```

---

## MVP 完成定义

MapCode v1 的 MVP 完成定义：

```text
在一个 Git 管理的 Python 仓库中，
用户提交一次代码分析或修改请求后，
Pico 能在首次主模型调用前执行一次 MapContext preparation，
MapEngine 能生成 broad 或 focused repo map，
文件、symbol 或 path ident 有效命中能稳定进入 Branch A，
只有三类信号均无有效命中的请求才进入 Branch B 流程，
focus personalization、path personalization 和 ranking multiplier evidence 可以被复盘，
ContextManager 能将带完整导航安全契约的 repo map 注入主 prompt，
Pico 主模型能基于 repo map 调用 read_file 获取完整源码，
run 结束后 trace / report / repo-map artifact / evidence artifact 可复盘本次检索和上下文选择过程，
且 MapEngine 禁用、失败或 repo map 无法满足 ModelRequestBudget 时，Pico 能按 `SPEC_v1_4.md` 定义的降级路径继续或走统一预请求失败路径。
```
