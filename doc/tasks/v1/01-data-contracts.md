# 01 Data Contracts Tasks

## 模块目标

固定 MapEngine-owned 与 Pico runtime-owned 数据契约、预算配置事实源和架构依赖方向，为索引、排名、selector、最终请求门禁和证据链提供稳定接口。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 第六章与第七章、`PRD_v1_1.md` 模块契约。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 0 全部门禁通过。

## 模块通用边界

- **允许修改**：`pico/pico/features/map_engine/`、对应 DTO 所属的 `pico/pico/core/` 模块、配置模块与对应测试。
- **禁止修改**：MapEngine 算法、Engine 控制流、ContextManager prompt 行为、Aider 源码。
- **模块原则**：DTO 按所有权放置；`ModelRequestBudget` 属于 runtime；`SelectorCandidateCatalog` 属于 MapEngine；不为减少行数创建无职责文件。

## 任务列表

### V1-F1-01：创建 MapEngine 配置和版本常量

- **优先级**：P0
- **依赖**：V1-F0-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`pico/pico/features/map_engine/__init__.py`、`config.py`、配置测试
- **允许修改路径**：`pico/pico/features/map_engine/`、`pico/tests/test_map_engine_config.py`
- **禁止修改边界**：不得实现索引、排名、runtime 请求预算或 runtime 接入
- **步骤**：定义 focused `4_096`、broad `8_192` token budget，selector catalog 三项限制、schema/parser/query/ranking 版本和 PageRank 参数；测试唯一事实源。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_config.py -q
  ```
- **完成标准**：MapEngine 固定参数与 `SPEC_v1_3.md` 一致，focused budget 不因 focus 文件存在而变化。
- **回退条件**：配置值分散到其他模块、继续使用字符 budget 作为 MapEngine 预算名称，或与 SPEC 不一致。

### V1-F1-02：定义索引基础 DTO

- **优先级**：P0
- **依赖**：V1-F1-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`DefinitionRecord`、`ReferenceRecord`、`FileRecord`
- **允许修改路径**：`pico/pico/features/map_engine/models.py`、`pico/tests/test_map_engine_models.py`
- **禁止修改边界**：不得加入 runtime-owned 字段或持久化行为
- **步骤**：使用 immutable dataclass 定义字段；测试相等性、不可变性、0-based line 和 repo-relative path 契约。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_models.py -q
  ```
- **完成标准**：三个基础 DTO 与 SPEC 字段一致。
- **回退条件**：DTO 混入模块内部临时状态或 Pico runtime 状态。

### V1-F1-03：定义 ranking、rendering 与 cache evidence DTO

- **优先级**：P0
- **依赖**：V1-F1-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：排名贡献、rendered/omitted file、ranking/rendering/cache evidence DTO
- **允许修改路径**：`pico/pico/features/map_engine/models.py`、`pico/tests/test_map_engine_models.py`
- **禁止修改边界**：不得实现 evidence 推导算法
- **步骤**：定义字段与 Literal 范围；RenderingEvidence 固定记录 `target_tokens`、`target_chars`、`used_chars`、`estimated_tokens`、`budget_reduction_applied`、`focus_truncated`。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_models.py -q
  ```
- **完成标准**：MapEngine token budget 和 ranking/rendering 事实无需松散 dict 传递。
- **回退条件**：同一字段同时表达 MapEngine 截断与 ContextManager base prompt reduction。

### V1-F1-04：定义 PromptAnalysis、MapContextEvidence 与 MapResult

- **优先级**：P0
- **依赖**：V1-F1-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：MapEngine 主要输入/输出 DTO
- **允许修改路径**：`pico/pico/features/map_engine/models.py`、`pico/tests/test_map_engine_models.py`
- **禁止修改边界**：不得包含 selector、run id、artifact path 或终端文本
- **步骤**：定义三个 immutable DTO；测试 `effective_symbol_hits`、MapContextEvidence 确定性边界和 MapResult 主要输出契约。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_models.py -q
  ```
- **完成标准**：MapEngine 唯一主要 map 输出是结构化 `MapResult`。
- **回退条件**：MapEngine-owned DTO 依赖 Pico runtime 事实。

### V1-F1-05：定义 SelectorCandidateCatalog DTO

- **优先级**：P0
- **依赖**：V1-F1-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：MapEngine-owned `SelectorCandidateCatalog`
- **允许修改路径**：`pico/pico/features/map_engine/models.py`、`pico/tests/test_map_engine_models.py`
- **禁止修改边界**：不得构建 selector prompt、调用模型或包含 SymbolIndex 范围外路径
- **步骤**：定义 snapshot id、全量 `candidate_paths`、模型可见 `rendered_paths/rendered_text`、计数、estimated tokens 和 truncated 字段；测试子集与稳定排序不变量。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_models.py -q
  ```
- **完成标准**：全量校验路径集合与预算受控模型可见目录具有明确独立语义。
- **回退条件**：将 `candidate_paths` 误描述为模型全部可见，或将 catalog 放入 Pico core。

### V1-F1-06：定义 SelectorModelRequest 与 selector 决策 DTO

- **优先级**：P0
- **依赖**：V1-F1-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`SelectorModelRequest`、`SelectorResult`、`SelectionDecision`、包含 `selector_request_over_budget` 的 `FallbackReason`
- **允许修改路径**：`pico/pico/core/map_selector.py`、`pico/tests/test_map_selector.py`
- **禁止修改边界**：不得实现 selector 调用、用户交互或 trace
- **步骤**：定义包含 `system_prompt`、`user_prompt`、`visible_paths` 的 immutable `SelectorModelRequest`；定义 selector/decision DTO、fallback constructors、`excess_files` 和整组二选一映射不变量。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_selector.py -q
  ```
- **完成标准**：selector 双角色请求、超预算和其他确认/fallback 决策可独立测试，且不包含副作用。
- **回退条件**：DTO 直接调用模型、询问用户或写 trace。

### V1-F1-07：定义 MapContext 与 artifact DTO

- **优先级**：P0
- **依赖**：V1-F1-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`MapContextResult`、`MapResultEvidence`、`MapEvidenceArtifact`
- **允许修改路径**：`pico/pico/core/map_context.py`、`pico/tests/test_map_context_models.py`
- **禁止修改边界**：不得实现 Coordinator、artifact 写入或 trace
- **步骤**：定义 immutable DTO；测试 Branch A/B、prepared/finalized、selector call snapshot、fallback 和 artifact envelope 不变量。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_models.py -q
  ```
- **完成标准**：当前 run MapContext 和持久化 envelope 具有明确结构化契约。
- **回退条件**：DTO 混入持久化副作用或保存完整 map 文本到错误层级。

### V1-F1-08：定义 runtime-owned ModelRequestBudget

- **优先级**：P0
- **依赖**：V1-F1-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、已批准的预算配置契约、依赖任务产物
- **输出**：不可变 `ModelRequestBudget`、保守 token estimator 与契约测试
- **允许修改路径**：`pico/pico/core/model_request_budget.py`、对应测试
- **禁止修改边界**：不得放入 MapEngine config；不得使用 `ContextUsageAnalyzer.DEFAULT_CONTEXT_WINDOW` 作为硬门禁
- **步骤**：定义 provider/model/input budget/safety margin/estimation method/source；固定 fallback `32_768`、默认 margin `1_024`、`ceil(chars / 4)`；验证输入 budget 和 margin 不变量。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_model_request_budget.py -q
  ```
- **完成标准**：selector 与最终主模型请求可读取同一不可变硬门禁事实源。
- **回退条件**：把输出 `max_new_tokens` 当作输入上限，或显式错误配置被静默接受。

### V1-F1-09：定义 prompt render 与 build result DTO

- **优先级**：P0
- **依赖**：V1-F1-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`RepoMapSectionRender`、`PromptInjectionEvidence`、`PromptPurpose`、`PromptBuildResult`
- **允许修改路径**：`pico/pico/core/map_context_prompt.py`、`pico/pico/core/context_manager.py`、对应测试
- **禁止修改边界**：不得实现 repo map 注入、base prompt reduction 或 artifact 写入
- **步骤**：定义 build-local render 和首次主模型 injection evidence；PromptBuildResult metadata 必须承载 input budget、margin、reservation、base budget、estimated request、request_over_budget 和预算来源。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_prompt.py pico\tests\test_context_manager.py -q
  ```
- **完成标准**：prompt render 与请求预算事实可通过 build result 传递，不依赖共享可变状态。
- **回退条件**：引入 `last_map_section_render`、从完整 prompt 反推 evidence，或在 DTO 任务中改变 prompt 行为。

### V1-F1-10：增加 MapEngine 与预算架构边界测试

- **优先级**：P0
- **依赖**：V1-F1-09
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：扩展后的 `pico/tests/test_architecture_boundaries.py`
- **允许修改路径**：`pico/tests/test_architecture_boundaries.py`
- **禁止修改边界**：不得只增加行数门禁而缺少依赖边界断言
- **步骤**：增加 MapEngine 不导入 `pico.core`/`aider`、runtime DTO 不反向进入 MapEngine、ModelRequestBudget 不进入 MapEngine config 的测试。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico\features\map_engine pico\pico\core pico\tests
  ```
- **完成标准**：架构边界可自动验证；任何行数门禁调整均有职责说明。
- **回退条件**：测试通过但不能阻止 MapEngine 依赖 Pico/Aider，或预算职责跨层漂移。
