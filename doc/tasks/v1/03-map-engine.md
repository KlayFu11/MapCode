# 03 Deterministic MapEngine Tasks

## 模块目标

基于同一 SymbolIndex snapshot 实现 prompt 信号分析、文件级引用图、PageRank/PPR、精确 symbol 候选前缀、TreeContext 渲染、固定 token budget、SelectorCandidateCatalog 和结构化 evidence。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 7.5 至 8、15、17.1。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 2 全部门禁通过。

## 模块通用边界

- **允许修改**：`pico/pico/features/map_engine/` 下 analyzer、ranker、renderer、catalog、evidence、engine 与对应测试/fixture。
- **禁止修改**：`pico/pico/core/`、模型 provider、用户交互、trace、RunStore、Aider。
- **模块原则**：MapEngine 只执行确定性构建；token budget 只约束候选 map/catalog；不读取 `ModelRequestBudget`。

## 任务列表

### V1-F3-01：实现 PromptAnalyzer identifier 与 Branch 判断

- **优先级**：P0
- **依赖**：V1-F2-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、同一 SymbolIndex snapshot、依赖任务产物
- **输出**：`prompt_analyzer.py` identifier 提取、effective symbol hits、Branch 判断
- **允许修改路径**：`prompt_analyzer.py`、`pico/tests/test_map_engine_prompt_analyzer.py`
- **禁止修改边界**：不得实现文件路径匹配、ranking 或 LLM 语义分析
- **步骤**：按 `re.split(r"\W+", text)` 稳定提取 tokens；使用 snapshot `all_defs` 计算 effective symbol hits；判定 specific/fuzzy；目录类片段如 `pico/`、`src/` 不进入 `mentioned_files`，不新增 `mentioned_dirs`，仅保留在原始请求中并形成 fuzzy Branch B。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py -q
  ```
- **完成标准**：identifier 顺序、大小写、去重、symbol hits 与 Branch 规则符合 SPEC；“分析 `pico/` 文件夹下的内容”不会被错误识别为 specific 文件请求。
- **回退条件**：引入未定义的 keyword/长度/语义过滤。

### V1-F3-02：实现文件路径唯一匹配与歧义过滤

- **优先级**：P0
- **依赖**：V1-F3-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：repo path、basename、stem、path component 匹配
- **允许修改路径**：`prompt_analyzer.py`、`test_map_engine_prompt_analyzer.py`
- **禁止修改边界**：不得新增交互式消歧
- **步骤**：优先精确 repo-relative path；仅唯一候选可由 basename/stem/component 命中；按首次出现稳定去重。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py -q
  ```
- **完成标准**：歧义候选不会进入 mentioned_files；symbol-only specific 的 focus files 仍为空。
- **回退条件**：模糊匹配错误选中文件。

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

### V1-F3-04：实现 broad PageRank 和 ranking evidence

- **优先级**：P0
- **依赖**：V1-F3-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：标准 PageRank、node score、definition rank、reason codes
- **允许修改路径**：`graph_ranker.py`、`evidence.py`、`test_map_engine_graph_ranker.py`
- **禁止修改边界**：不得应用 focus personalization/outbound boost
- **步骤**：使用配置参数执行 broad PageRank；保留原始/归一化分数、top files 和 contributors。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py -q
  ```
- **完成标准**：broad ranking evidence 可解释且重复运行稳定。
- **回退条件**：从最终排序文本反推 evidence。

### V1-F3-05：实现 focused PPR、boost 和 contributors

- **优先级**：P0
- **依赖**：V1-F3-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：mentioned identifier boost、focus outbound boost、PPR
- **允许修改路径**：`graph_ranker.py`、`evidence.py`、`test_map_engine_graph_ranker.py`
- **禁止修改边界**：不得复用 Aider `chat_fnames` 混合语义
- **步骤**：PageRank 前应用 ident 和 outbound boost；有实际 seed 时均匀 personalization；无实际 seed 时使用普通 PageRank。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_graph_ranker.py -q
  ```
- **完成标准**：mode 与实际 algorithm 分离，contributors 与实际权重一致。
- **回退条件**：PageRank 后修改排序权重、把 symbol hit 当作 PPR seed 或排除 focus 文件。

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
- **输出**：`context_renderer.py` TreeContext 风格渲染
- **允许修改路径**：`context_renderer.py`、`pico/tests/test_map_engine_context_renderer.py`
- **禁止修改边界**：不得复制 Aider RepoMap 控制流、spinner、IO 或 tokenizer
- **步骤**：根据有序 DefinitionRecord 与文件级排序渲染结构摘要；无 tag 文件至少输出路径；保留 rendered symbols。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_context_renderer.py -q
  ```
- **完成标准**：固定 fixture 渲染稳定，focus 文件与精确 symbol 前缀不会因 Aider 排除语义消失。
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
- **步骤**：组合 SymbolIndex、Analyzer、Ranker、Renderer、Catalog builder；确保 Branch B broad/catalog/focused 复用同一 snapshot。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine.py -q
  ```
- **完成标准**：MapEngine 主要输出为 `MapResult` 或 `SelectorCandidateCatalog`，无 runtime 副作用。
- **回退条件**：公共接口暴露内部可变状态、重复索引或引入 runtime 副作用。

### V1-F3-11：增加离线 MapEngine fixture 演示

- **优先级**：P0
- **依赖**：V1-F3-10
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：固定 Git Python fixture 与离线演示测试/脚本
- **允许修改路径**：`pico/tests/fixtures/map_engine/`、MapEngine tests、演示脚本
- **禁止修改边界**：不得调用真实模型或修改 runtime
- **步骤**：演示 broad、文件命中 focused、symbol-only focused、精确 symbol 前缀、catalog、cache hit 和稳定 fallback。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_prompt_analyzer.py pico\tests\test_map_engine_graph_ranker.py pico\tests\test_map_engine_context_renderer.py pico\tests\test_map_engine_selector_catalog.py pico\tests\test_map_engine.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico\features\map_engine pico\tests
  ```
- **完成标准**：阶段 3 可独立演示且所有门禁通过。
- **回退条件**：演示依赖 Pico runtime、无法稳定复现或没有证明固定 token budget。
