# 03 Deterministic MapEngine Tasks

## 模块目标

基于同一 SymbolIndex snapshot 实现文件/symbol/path-ident 信号分析、文件级引用图、Aider-style multiplier、focus/path personalization、PageRank/PPR、精确 symbol 候选前缀、TreeContext 渲染、固定 token budget、SelectorCandidateCatalog 和结构化 evidence。

## 相关设计

- 当前迁移前来源：`SPEC_v1_4.md` 7.5 至 8、15、17.1。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 2 全部门禁通过。

## 模块通用边界

- **允许修改**：`pico/pico/features/map_engine/` 下 analyzer、ranker、renderer、catalog、evidence、engine 与对应测试/fixture。
- **禁止修改**：`pico/pico/core/`、模型 provider、用户交互、trace、RunStore、Aider。
- **模块原则**：MapEngine 只执行确定性构建；token budget 只约束候选 map/catalog；不读取 `ModelRequestBudget`。

## 任务列表

### V1-F3-01：实现 PromptAnalyzer identifier 与 symbol hit 提取

- **优先级**：P0
- **依赖**：V1-F2-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、同一 SymbolIndex snapshot、依赖任务产物
- **输出**：`prompt_analyzer.py` 稳定 `mentioned_idents` 与 `effective_symbol_hits` 提取
- **允许修改路径**：`prompt_analyzer.py`、`pico/tests/test_map_engine_prompt_analyzer.py`
- **禁止修改边界**：不得实现文件/path-ident 匹配、最终 Branch 判断、ranking 或 LLM 语义分析
- **步骤**：按 `re.split(r"\W+", text)` 提取并按首次出现顺序稳定去重；保留原始大小写且不增加 keyword/长度过滤；使用 snapshot `all_defs` 计算大小写敏感的 `effective_symbol_hits`；完整 `mentioned_idents` 保留为后续 symbol edge boost 输入。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py -q
  ```
- **完成标准**：identifier 顺序、大小写、去重和 symbol hits 符合 SPEC；本任务不提前决定 Branch。
- **回退条件**：引入未定义的 keyword/长度/语义过滤。

### V1-F3-02：实现文件匹配、path ident 与 Branch 判断

- **优先级**：P0
- **依赖**：V1-F3-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：准确文件匹配、`path_ident_hits/path_ident_hit_files` 与最终 Branch 判断
- **允许修改路径**：`prompt_analyzer.py`、`test_map_engine_prompt_analyzer.py`
- **禁止修改边界**：不得新增交互式消歧
- **步骤**：实现 repo-relative、`./`、repo-root 内 absolute path 的准确匹配，以及保守的唯一 basename/stem 匹配；path component、目录和路径前缀不得进入 `mentioned_files`；从同一 snapshot 的 indexed paths 构造 components/basename/stem path terms 和 lowercase key；使用 `mentioned_idents` 做大小写不敏感匹配，同时在 hits/evidence 中保留原始 ident；记录每个 ident 命中的全部 indexed files；以文件、symbol、path ident 任一有效命中判定 specific，三者均为空判定 fuzzy。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py -q
  ```
- **完成标准**：歧义、目录和 path component 不进入 mentioned_files；path-ident-only 请求进入 specific，但不形成 `mentioned_files`、`mentioned_dirs` 或 focus 文件；symbol-only specific 的 focus files 仍为空。
- **回退条件**：模糊匹配错误选中文件、path ident 被当作目录 scope/focus，或有效 path ident 仍进入 Branch B。

### V1-F3-03：构建文件级 def/ref 图和稳定 fallback

- **优先级**：P0
- **依赖**：V1-F3-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、同一 SymbolIndex snapshot、依赖任务产物
- **输出**：`graph_ranker.py` 图构建、稳定路径 fallback
- **允许修改路径**：`graph_ranker.py`、`pico/tests/test_map_engine_graph_ranker.py`
- **禁止修改边界**：不得进行 rendering 或 runtime trace
- **步骤**：构建 `referencer -> definer` 边；使用平方根引用次数权重；空图/失败按 repo-relative path 稳定排序。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py -q
  ```
- **完成标准**：固定 fixture 图结构与 fallback 顺序可重复。
- **回退条件**：边方向、权重来源或 fallback 不稳定。

### V1-F3-04：实现 broad PageRank、Aider-style multiplier 与 ranking evidence

- **优先级**：P0
- **依赖**：V1-F3-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：Aider-style symbol multiplier、标准 PageRank、node score、definition rank、contributors 与 reason codes
- **允许修改路径**：`graph_ranker.py`、`evidence.py`、`test_map_engine_graph_ranker.py`
- **禁止修改边界**：不得应用 focus personalization/outbound boost
- **步骤**：在 PageRank 前以 `sqrt(reference_count)` 为基础组合 prompt、structured、private、common symbol multiplier；symbol matching 保持大小写敏感；记录最终 `weight_multiplier` 和稳定 `weight_reason_codes`；执行无 personalization、无 focus outbound boost 的 broad PageRank；保留原始/归一化分数、top files 和 contributors。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py -q
  ```
- **完成标准**：broad ranking evidence 可解释 multiplier 组合且重复运行稳定；不添加无引用 definition `0.1` 自环。
- **回退条件**：从最终排序文本反推 evidence。

### V1-F3-05：实现 focus/path personalization、PPR 与 outbound boost

- **优先级**：P0
- **依赖**：V1-F3-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：focus/path personalization contribution、稳定并集、PPR 与 focus-only outbound boost
- **允许修改路径**：`graph_ranker.py`、`evidence.py`、`test_map_engine_graph_ranker.py`
- **禁止修改边界**：不得复用 Aider `chat_fnames` 混合语义
- **步骤**：从 `focus_fnames` 过滤得到 `focus_personalization_files`；从 `path_ident_hit_files` 合并并过滤图节点得到按路径排序的 `path_personalization_files`；形成先 focus 后 path 的稳定 `personalization_files` 并按两类 contribution 归一化；同一文件每类 contribution 最多一次；只对 focus personalization files 的出站边应用 `FOCUS_OUTBOUND_BOOST`；无 personalization 时使用普通 PageRank。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py -q
  ```
- **完成标准**：mode 与实际 algorithm 分离；path-ident-only 可使用 PPR 且不获得 outbound boost；同时属于 focus/path 的文件各获得一次 contribution；contributors 与实际权重一致。
- **回退条件**：PageRank 后修改排序权重、把 symbol hit/path ident 当作 focus 文件、违反 focus-only outbound boost 约束，或排除 focus 文件。

### V1-F3-06：固定 effective_symbol_hits DefinitionRecord 候选前缀

- **优先级**：P0
- **依赖**：V1-F3-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、PromptAnalysis、同一 snapshot 的 `definitions_by_symbol`
- **输出**：focused rendering 的精确 DefinitionRecord 候选前缀与测试
- **允许修改路径**：`graph_ranker.py`、`context_renderer.py`、对应测试
- **禁止修改边界**：不得改变 PageRank/PPR 分数或伪造 definition rank
- **步骤**：将 effective symbol hits 对应的 DefinitionRecord 按稳定顺序固定置于 focused 候选前缀，再接排名候选并稳定去重。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py pico\tests\test_map_engine_context_renderer.py -q
  ```
- **完成标准**：精确命中的 DefinitionRecord 即使没有引用边或分数较低，也优先参与 focused map 预算渲染。
- **回退条件**：通过修改 rank 分数实现前缀，或不能证明 DefinitionRecord 来自当前 snapshot。

### V1-F3-07：使用 TreeContext 渲染结构摘要

- **优先级**：P0
- **依赖**：V1-F3-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、排名候选与精确 symbol 前缀
- **输出**：`context_renderer.py` TreeContext 风格渲染与文件级 path-ident evidence
- **允许修改路径**：`context_renderer.py`、`pico/tests/test_map_engine_context_renderer.py`
- **禁止修改边界**：不得复制 Aider RepoMap 控制流、spinner、IO 或 tokenizer
- **步骤**：根据有序 DefinitionRecord 与文件级排序渲染结构摘要；无 tag 文件至少输出路径；保留 rendered symbols；从 `path_ident_hit_files` 向 rendered/omitted file evidence 反向投影原始 `prompt_path_ident_hits`，并增加稳定 `path_ident_match` reason code。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_context_renderer.py -q
  ```
- **完成标准**：固定 fixture 渲染稳定；focus 文件与精确 symbol 前缀不会因 Aider 排除语义消失；全局 path-ident 映射与文件级反向投影一致。
- **回退条件**：渲染依赖 Aider runtime 或输出不可重复。

### V1-F3-08：实现固定 focused/broad token budget 与 truncation

- **优先级**：P0
- **依赖**：V1-F3-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：focused `4_096`、broad `8_192` token budget 选择与 RenderingEvidence
- **允许修改路径**：`context_renderer.py`、`evidence.py`、`test_map_engine_context_renderer.py`
- **禁止修改边界**：不得读取 ModelRequestBudget；不得让 focused budget 因 focus 文件存在而扩大
- **步骤**：使用 `ceil(chars / 4)` 稳定估算执行固定 token budget；按完整结构单元裁剪；保留路径并记录 truncation 和 budget reduction。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_context_renderer.py -q
  ```
- **完成标准**：focused 永远使用 4,096 tokens，broad 永远使用 8,192 tokens；MapEngine 截断与 ContextManager base prompt reduction 语义分离。
- **回退条件**：恢复动态扩大 focused budget、承诺所有 focus definition 完整显示，或使用最终请求预算控制 MapEngine。

### V1-F3-09：从同一 snapshot 生成 SelectorCandidateCatalog

- **优先级**：P0
- **依赖**：V1-F3-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、已就绪 SymbolIndex snapshot
- **输出**：确定性 `SelectorCandidateCatalog` builder 与测试
- **允许修改路径**：`pico/pico/features/map_engine/selector_catalog.py`、`engine.py`、对应测试
- **禁止修改边界**：不得构造 selector LLM prompt、调用模型或读取 SymbolIndex 范围外文件
- **步骤**：从当前 snapshot 生成全量排序 `candidate_paths`、预算受控完整文件块 `rendered_text` 和 `rendered_paths`；执行 catalog token/files/defs 限制。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_selector_catalog.py -q
  ```
- **完成标准**：catalog 与 broad/focused map 复用同一 snapshot；模型可见目录与全量校验路径明确区分。
- **回退条件**：catalog 重新构建索引、截断半个文件块，或只包含 broad rendered files。

### V1-F3-10：实现 MapEngine 公共接口和 lazy index

- **优先级**：P0
- **依赖**：V1-F3-09
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`MapEngine.analyze/generate_broad/generate_focused/build_selector_catalog`
- **允许修改路径**：`features/map_engine/engine.py`、`evidence.py`、`pico/tests/test_map_engine.py`
- **禁止修改边界**：不得依赖 Pico runtime、ModelRequestBudget、模型、用户交互、trace、RunStore
- **步骤**：组合 SymbolIndex、Analyzer、Ranker、Renderer、Catalog builder；确保 path-ident-only specific 直接生成 path-personalized focused map，Branch B broad/catalog/focused 复用同一 snapshot。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine.py -q
  ```
- **完成标准**：MapEngine 主要输出为 `MapResult` 或 `SelectorCandidateCatalog`；path-ident-only 不依赖 runtime/selector；无 runtime 副作用。
- **回退条件**：公共接口暴露内部可变状态、重复索引或引入 runtime 副作用。

### V1-F3-11：增加离线 MapEngine fixture 演示

- **优先级**：P0
- **依赖**：V1-F3-10
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：固定 Git Python fixture 与离线演示测试/脚本
- **允许修改路径**：`pico/tests/fixtures/map_engine/`、MapEngine tests、演示脚本
- **禁止修改边界**：不得调用真实模型或修改 runtime
- **步骤**：演示 broad、文件命中 focused、symbol-only focused、path-ident-only focused、原始大小写保留、全量 path-ident 命中到图节点过滤、focus/path personalization 隔离、multiplier evidence、精确 symbol 前缀、catalog、cache hit 和稳定 fallback。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py pico\tests\test_map_engine_graph_ranker.py pico\tests\test_map_engine_context_renderer.py pico\tests\test_map_engine_selector_catalog.py pico\tests\test_map_engine.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico\features\map_engine pico\tests
  ```
- **完成标准**：阶段 3 可独立演示 path-ident-only Branch A 与 Aider-style multiplier 审计，且所有门禁通过。
- **回退条件**：演示依赖 Pico runtime、无法稳定复现或没有证明固定 token budget。
