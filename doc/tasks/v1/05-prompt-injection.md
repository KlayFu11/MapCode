# 05 PromptPurpose And Repo Map Injection Tasks

## 模块目标

让所有 prompt build 显式声明 purpose，并让 ContextManager 在同一 ModelRequestBudget 下为完整 repo map section 预留输入空间、缩减 base prompt、原子注入或整段省略。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 6.7、6.8、8.4、9.2、12、17.4。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 4 全部门禁通过。

## 模块通用边界

- **允许修改**：ContextManager、runtime prompt wrapper、`map_context_prompt.py`、prompt 调用点与对应测试。
- **禁止修改**：Engine Branch A/B preparation、selector、MapEngine 算法、artifact 持久化。
- **模块原则**：ContextManager 拥有 section 组装和 base prompt reduction；不二次裁剪 MapEngine repo map body；完整契约与 map body 原子注入或整段省略。

## 任务列表

### V1-F5-01：引入 PromptPurpose 和 PromptBuildResult

- **优先级**：P0
- **依赖**：V1-F4-09、V1-F4-10
- **输入**：当前最新 SPEC/PRD/FuncFlow、V1-F1-09 DTO、真实 ContextManager 接缝
- **输出**：显式 purpose 类型、build-local result 返回契约
- **允许修改路径**：`pico/pico/core/context_manager.py`、对应测试
- **禁止修改边界**：不得注入 repo map、改变 base prompt reduction 或保存共享 render
- **步骤**：修改 `ContextManager.build()` 返回 PromptBuildResult；purpose 不提供默认值；当前 repo_map_render 保持 None。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_manager.py -q
  ```
- **完成标准**：每次 build 都有独立结果对象，现有 prompt 内容保持不变。
- **回退条件**：通过 ContextManager 可变共享状态传递 render。

### V1-F5-02：迁移 Runtime wrapper 与 main model 调用点

- **优先级**：P0
- **依赖**：V1-F5-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、Runtime wrapper 与 Engine main loop
- **输出**：Runtime wrapper 与全部主模型调用显式 `main_model`
- **允许修改路径**：`pico/pico/core/runtime.py`、`pico/pico/core/engine.py`、相关测试
- **禁止修改边界**：不得执行 MapContext preparation、artifact 或最终请求硬门禁
- **步骤**：迁移 `_build_prompt_and_metadata()`、首次/后续主模型 build 和 PromptBuildResult 读取；保持模型调用行为不变。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_engine_acceptance.py pico\tests\test_pico.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：所有主模型 prompt build purpose 明确。
- **回退条件**：为行数门禁把连续主模型 prompt 控制流拆成无职责 helper。

### V1-F5-03：迁移 prompt preview 调用点

- **优先级**：P0
- **依赖**：V1-F5-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、CLI/context usage preview 调用点
- **输出**：全部 preview 调用显式 `prompt_preview`
- **允许修改路径**：runtime/CLI/usage preview 接缝与相关测试
- **禁止修改边界**：不得写 artifact、覆盖首次主模型 render 或触发 auto-compaction
- **步骤**：迁移所有 preview/context usage 调用点；保持 preview 只构建不持久化。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_governance_acceptance.py pico\tests\test_usage.py -q
  ```
- **完成标准**：所有 preview 调用点 purpose 明确且无持久化副作用。
- **回退条件**：preview 覆盖 main model render 或修改 session。

### V1-F5-04：迁移 evaluation 与 step-limit summary 调用点

- **优先级**：P0
- **依赖**：V1-F5-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、evaluation 与 step-limit summary 调用点
- **输出**：辅助 prompt 显式 purpose、无 repo map/auto-compaction 测试
- **允许修改路径**：evaluation、engine helper、runtime wrapper 与对应测试
- **禁止修改边界**：不得让辅助 purpose 注入 repo map 或修改 session
- **步骤**：标记 evaluation/step_limit_summary；限制 auto-compaction 仅 main_model。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_governance_acceptance.py pico\tests\test_engine_acceptance.py -q
  ```
- **完成标准**：所有 prompt build 调用点显式提供 purpose。
- **回退条件**：辅助 prompt 覆盖主模型 render 状态或触发 session 变更。

### V1-F5-05：实现统一主模型导航模板与 fallback notice

- **优先级**：P0
- **依赖**：V1-F5-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、结构化 MapContextResult
- **输出**：统一导航模板、`map_context_prompt.py` 纯渲染函数与测试
- **允许修改路径**：`pico/pico/core/map_context_prompt.py`、对应测试
- **禁止修改边界**：不得调用模型、读取仓库、修改全局 prefix 或执行预算门禁
- **步骤**：实现 Branch A、Branch B focused、Branch B broad fallback 共用的固定导航模板；只从 active result 派生 `focus_files_display` 和 `active_repo_map_text`；实现 Branch/Mode/focus 状态和统一 fallback notice；禁止使用 `focused_repo_map_string`、`focus_fnames_list`，也不为主模型增加 provider-level system prompt。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_prompt.py -q
  ```
- **完成标准**：三种主模型模式使用同一模板；变量来源准确；focused/fallback 文本准确；MapContext 不存在时无 section。
- **回退条件**：通过搜索 repo map 文本猜测 fallback 状态。

### V1-F5-06：ContextManager 组装独立 repo_map section

- **优先级**：P0
- **依赖**：V1-F5-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、current_map_context、ModelRequestBudget
- **输出**：repo_map section 顺序、build-local RepoMapSectionRender 与 metadata
- **允许修改路径**：`pico/pico/core/context_manager.py`、相关测试
- **禁止修改边界**：不得触发 MapEngine、修改 current_map_context 或写 artifact
- **步骤**：main_model/prompt_preview 读取 current map；使用 active result 预渲染 `focus_files_display`、`active_repo_map_text`、完整契约、状态行和 notice；将 repo_map 放在 history 与 current_request 之间。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_manager.py pico\tests\test_map_context_prompt.py -q
  ```
- **完成标准**：section 顺序正确；evaluation/summary 不注入；无 current map 时原行为不变。
- **回退条件**：ContextManager 触发 MapEngine，或 repo map 文本进入全局 prefix/file summaries。

### V1-F5-07：为完整 repo map 预留输入空间并缩减 base prompt

- **优先级**：P0
- **依赖**：V1-F5-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、完整 repo_map section、runtime ModelRequestBudget
- **输出**：reservation、base prompt budget、base prompt reduction 与 metadata 测试
- **允许修改路径**：`pico/pico/core/context_manager.py`、`pico/pico/core/runtime.py`、相关测试
- **禁止修改边界**：不得二次裁剪 repo map body；不得裁剪 current_request；不得把 repo map 叠加到最终硬上限之外
- **步骤**：估算完整 section tokens；计算 active reservation 与 base prompt budget；仅缩减 Pico 原有 base sections；auto-compaction 使用预留后的有效 base prompt budget。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_manager.py pico\tests\test_context_governance_acceptance.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：metadata 准确记录 input budget、margin、reservation、base budget、estimated request、request_over_budget 和来源。
- **回退条件**：ContextManager 修改 MapEngine map body，或仍按未预留 repo map 的阈值执行 reduction/compaction。

### V1-F5-08：实现 repo map 原子注入或整段省略

- **优先级**：P0
- **依赖**：V1-F5-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、预留后的 build 结果
- **输出**：完整 section/空 section、稳定 hash、omission evidence 测试
- **允许修改路径**：`pico/pico/core/context_manager.py`、`map_context_prompt.py`、相关测试
- **禁止修改边界**：不得产生部分契约或部分 map body；不得从最终 prompt 反推 evidence
- **步骤**：完整 section 可容纳时原子注入；无法共存或渲染失败时返回空 section、稳定空 hash、非空 omission reason 和 request_over_budget metadata。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_manager.py pico\tests\test_map_context_prompt.py -q
  ```
- **完成标准**：ContextManager 不二次裁剪 repo map body；导航安全契约与 map body完整保留或整段省略。
- **回退条件**：出现缺少完整安全契约的 repo map section，或 omission reason 不稳定。

### V1-F5-09：验证 feature disabled、无 MapContext 与四种 purpose

- **优先级**：P0
- **依赖**：V1-F5-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、阶段 5 全部实现
- **输出**：feature-off、purpose、预算与 prompt 回归 acceptance tests
- **允许修改路径**：ContextManager/runtime acceptance tests
- **禁止修改边界**：不得接入 Engine MapContext preparation 或 artifact
- **步骤**：覆盖 feature disabled、current map None、四种 purpose、preview 不覆盖 main render、完整 reservation/reduction/omission metadata；验证 Branch A、Branch B focused、Branch B broad fallback 共用统一导航模板，且 `focus_files_display`、`active_repo_map_text` 只来自 active result。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_context_manager.py pico\tests\test_context_governance_acceptance.py pico\tests\test_map_context_prompt.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：阶段 5 门禁通过；统一主模型导航模板及变量来源有 acceptance 覆盖；MapEngine 尚未进入 Engine run_turn preparation。
- **回退条件**：feature-off prompt、Pico 原测试或请求预算 metadata 发生未解释回归。
