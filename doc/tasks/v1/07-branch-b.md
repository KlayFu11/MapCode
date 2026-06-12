# 07 Branch B Selector And Confirmation Tasks

## 模块目标

完成基于同一 SymbolIndex snapshot 的 broad map、SelectorCandidateCatalog、双角色 selector request、请求预算门禁、整组确认和准确 broad fallback。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 6.5、9.3、11.2、11.3、16、17.3。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 6 全部门禁通过。

## 模块通用边界

- **允许修改**：Engine Branch B 控制流、`map_selector.py`、Coordinator 最小适配、Branch B tests。
- **禁止修改**：MapEngine 排名算法、ContextManager 新行为、部分接受/调整建议文件功能。
- **模块原则**：selector request builder/parser 是纯 helper；Engine 编排 catalog、完整请求预算门禁、模型调用与确认；Coordinator 不做控制决策；`candidate_paths` 只证明 snapshot 来源，selector 返回路径必须存在于模型实际可见的 `visible_paths`。

## 任务列表

### V1-F7-01：实现 selector request builder、parser 和 visible path 校验

- **优先级**：P0
- **依赖**：V1-F6-09
- **输入**：当前最新 SPEC/PRD/FuncFlow、SelectorCandidateCatalog、SelectorModelRequest DTO
- **输出**：双角色 selector request builder、parser、confirmation renderer 与 DTO tests
- **允许修改路径**：`pico/pico/core/map_selector.py`、`pico/tests/test_map_selector.py`
- **禁止修改边界**：不得调用模型、读取 MapEngine 或直接形成用户决策
- **步骤**：构建固定 `system_prompt` 与三段式动态 `user_prompt`；system role 将 selector 限定为只负责文件检索，不修改、不测试、不调用工具、不制定实现计划；普通分析优先 source 文件，仅明确需要时选择 test 文件；目录路径只作为软偏好，不做硬过滤；替换最大文件数占位符；以 broad rendered files 与 `catalog.rendered_paths` 的稳定并集生成 `visible_paths`；解析只含 `suggested_files`、`reasoning` 的严格 JSON object，稳定去重并限制数量；只接受 `visible_paths`，拒绝只存在于 `candidate_paths` 但未展示给模型的隐藏路径；禁止裁剪原始 JSON 后再解析。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_selector.py -q
  ```
- **完成标准**：可接受 catalog 已展示但未进入 broad map 的路径；隐藏 candidate、重复、格式错误和越界路径有稳定结果。
- **回退条件**：parser 使用 `candidate_paths` 作为白名单、接受未展示路径、忽略双角色约束或直接询问用户。

### V1-F7-02：Engine 获取同 snapshot catalog 并执行 selector 请求预算门禁

- **优先级**：P0
- **依赖**：V1-F7-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、broad MapResult、Coordinator.build_selector_catalog、ModelRequestBudget
- **输出**：同 snapshot catalog、完整 SelectorModelRequest、`selector_request_over_budget` broad fallback tests
- **允许修改路径**：`pico/pico/core/engine.py`、`map_context.py` 最小适配、Branch B tests
- **禁止修改边界**：不得在超预算路径调用模型、发送 map_selector_requested 或增加 selector_model_calls
- **步骤**：fuzzy 时 prepare broad 并展示；从 Coordinator 获取同 snapshot catalog；构建完整 `system_prompt + user_prompt + visible_paths` 请求；对 `system_prompt + user_prompt` 使用同一 ModelRequestBudget 执行硬门禁。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_b_acceptance.py pico\tests\test_engine_acceptance.py -q
  ```
- **完成标准**：超预算形成 `selector_result=None` 的 `selector_request_over_budget` broad fallback；broad/catalog snapshot id 一致。
- **回退条件**：超预算仍调用 selector、重新构建索引或把门禁放入 Coordinator/MapEngine。

### V1-F7-03：Engine 复用双角色 provider adapter 调用 selector

- **优先级**：P0
- **依赖**：V1-F7-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、V1-F4-10 provider adapter、通过预算门禁的 SelectorModelRequest
- **输出**：保留 system/user 角色的单次 selector provider 调用、requested trace 和调用计数
- **允许修改路径**：`pico/pico/core/engine.py`、相关 tests
- **禁止修改边界**：不得新增第二套 provider/runtime；不得增加 TaskState.attempts
- **步骤**：预算通过后发送 map_selector_requested、递增 selector_model_calls、复用 V1-F4-10 双角色 provider adapter 调用一次 selector 并解析校验；保持主模型现有单一组合 prompt 调用不变。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_b_acceptance.py pico\tests\test_engine_acceptance.py -q
  ```
- **完成标准**：selector 最多调用一次；provider 收到分离的 system/user 角色；requested trace 只在实际调用前发送；调用不改变 attempts；主模型调用行为不变。
- **回退条件**：新增模型客户端、调用统计错误或事件顺序错误。

### V1-F7-04：实现整组二选一确认协议

- **优先级**：P0
- **依赖**：V1-F7-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、路径校验后的 SelectorResult
- **输出**：接受全部建议/使用 broad map 决策与确认事件
- **允许修改路径**：`engine.py`、`map_selector.py`、Branch B tests
- **禁止修改边界**：不得支持部分接受、增删或调整建议文件
- **步骤**：有效建议非空时调用 `runtime.ask_user()`；形成 immutable SelectionDecision；仅接受全部且非空 emit confirmed。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_selector.py pico\tests\test_map_context_branch_b_acceptance.py -q
  ```
- **完成标准**：确认协议与 fallback reason 完全符合 SPEC。
- **回退条件**：确认逻辑进入 Coordinator，或 selector helper 直接询问用户。

### V1-F7-05：实现 one-shot、超预算、取消和无效输出 fallback

- **优先级**：P0
- **依赖**：V1-F7-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、全部 Branch B fallback 条件
- **输出**：全部正常 broad fallback 路径和准确状态文本
- **允许修改路径**：`engine.py`、`map_selector.py`、Branch B tests
- **禁止修改边界**：不得把正常 fallback 标记为 map_context_failed
- **步骤**：覆盖 one-shot、selector_request_over_budget、无有效建议、用户 broad、取消、未知确认；复用原始 user message 与 broad result；不重跑 selector、不重新询问用户、不要求重新输入 prompt。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_b_acceptance.py -q
  ```
- **完成标准**：fallback reason、selector_result 和 selector_model_calls 准确；超预算与 one-shot 均为 0 次 selector call；broad fallback 不重跑 selector、不重问用户、不要求重新输入 prompt。
- **回退条件**：one-shot 自动采纳建议、超预算调用 provider，或 fallback notice 声称未识别文件。

### V1-F7-06：confirmed focus 生成 focused map 并复用 snapshot

- **优先级**：P0
- **依赖**：V1-F7-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、confirmed files、broad result、selection decision
- **输出**：Branch B confirmed focused MapContextResult
- **允许修改路径**：`engine.py`、`map_context.py`、Branch B tests
- **禁止修改边界**：不得在用户确认期间重新索引；Coordinator 不得自行决定 confirmed files
- **步骤**：confirmed files 交给 prepare_fuzzy；生成 focused 4,096-token map；保留 broad result/decision；复用 broad/catalog snapshot。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_b_acceptance.py pico\tests\test_map_engine.py -q
  ```
- **完成标准**：confirmed focused 的 broad/catalog/active evidence 与 snapshot 关系正确。
- **回退条件**：用户确认期间重新索引，或 focused budget 因 confirmed files 扩大。

### V1-F7-07：验证事件、展示、预算与模型调用顺序

- **优先级**：P0
- **依赖**：V1-F7-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、阶段 7 全部行为
- **输出**：完整 Branch B scripted acceptance tests
- **允许修改路径**：Branch B acceptance fixture/tests
- **禁止修改边界**：不得依赖真实模型
- **步骤**：覆盖 broad 展示在 selector 前、固定 system prompt、三段式 user prompt、完整请求预算、`visible_paths` 稳定并集、隐藏 candidate 拒绝、目录软偏好、source/test 偏好、selector 超预算、final 展示在主模型前、trace 顺序、调用统计和全部 fallback。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_selector.py pico\tests\test_map_context_branch_b_acceptance.py pico\tests\test_engine_acceptance.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：阶段 7 门禁通过；双角色请求、可见路径校验、完整请求预算、目录/source/test 偏好与 broad fallback 行为可离线复现。
- **回退条件**：事件时序、用户可见输出、snapshot 关系或模型调用统计不一致。
