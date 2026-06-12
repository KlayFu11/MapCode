# 06 Branch A And Final Model Gate Tasks

## 模块目标

完成 Branch A 首个端到端垂直闭环，并让 Engine 编排首次 prompt finalization、无 map 重建、最终请求硬门禁、实际模型调用计数和 current map 生命周期。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 9、10、11.1、11.3、14、16、17.2 至 17.5。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 5 全部门禁通过。

## 模块通用边界

- **允许修改**：Engine、Runtime 最小适配、Coordinator finalization、TaskState、Branch A acceptance tests。
- **禁止修改**：Branch B selector/确认、MapEngine 算法、ContextManager 新行为。
- **模块原则**：Engine 拥有 run 控制流、超预算降级和最终模型调用；禁止只为行数门禁拆为隐式回调链。

## 任务列表

### V1-F6-01：Engine 在首次主模型 build 前执行 Branch A preparation

- **优先级**：P0
- **依赖**：V1-F5-09
- **输入**：当前最新 SPEC/PRD/FuncFlow、Coordinator、Engine.run_turn 真实接缝
- **输出**：specific Branch preparation 接缝与事件
- **允许修改路径**：`pico/pico/core/engine.py`、`map_context.py`、相关 tests
- **禁止修改边界**：不得实现 Branch B selector 或在 ContextManager/runtime wrapper 触发 preparation
- **步骤**：run_started 后分析请求；specific 时 prepare focused；设置 prepared current map；异常时 emit failure 并继续。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_engine_acceptance.py -q
  ```
- **完成标准**：preparation 发生在首次 main_model build 前且每 run 仅一次。
- **回退条件**：preparation 放入 ContextManager/runtime wrapper，或控制流因行数门禁被拆散。

### V1-F6-02：首次 main model build 后持久化 artifacts

- **优先级**：P0
- **依赖**：V1-F6-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、首次 main_model PromptBuildResult
- **输出**：repo-map text artifact、map evidence JSON artifact 与路径摘要
- **允许修改路径**：`engine.py`、`map_context.py`、RunStore 最小适配、相关 tests
- **禁止修改边界**：不得在实际首次主模型 build 确定前写 artifact
- **步骤**：Engine 取得 build-local render；Coordinator 先写 repo-map，再组装 evidence JSON；含 repo map prompt 只有完整证据落盘后才可发送。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：artifact 路径与内容符合 SPEC，evidence 不保存完整 map 文本或自身路径。
- **回退条件**：artifact 在最终 prompt render 确定前写入，或落盘失败后仍发送含 map prompt。

### V1-F6-03：prepared MapContext 替换为 finalized 对象

- **优先级**：P0
- **依赖**：V1-F6-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、prepared result 与 finalization artifacts
- **输出**：同 map_context_id 的 finalized 生命周期
- **允许修改路径**：`engine.py`、`map_context.py`、TaskState 摘要与 tests
- **禁止修改边界**：不得跨 run/session 持久化完整 MapContextResult
- **步骤**：Coordinator 返回 immutable finalized result；Engine 替换 current map；更新轻量 TaskState 摘要。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_map_context_models.py -q
  ```
- **完成标准**：prepared/finalized id 一致，finalized prompt/artifact 字段完整。
- **回退条件**：当前 map 保存字符串、跨 run/session 持久化或使用共享可变状态。

### V1-F6-04：retry/tool loop 复用同一 MapContext

- **优先级**：P0
- **依赖**：V1-F6-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、finalized current map
- **输出**：后续 main_model build 复用和 prompt_built 摘要测试
- **允许修改路径**：`engine.py`、相关 acceptance tests
- **禁止修改边界**：不得重复 preparation、selector、确认或完整 artifact 写入
- **步骤**：后续 tool/retry loop 仅重建 prompt；复用 finalized map；记录 render hash/chars/omission/request budget 摘要。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_engine_acceptance.py -q
  ```
- **完成标准**：同 run preparation 一次，后续调用复用 finalized map。
- **回退条件**：每次 prompt build 重新索引、排名、写 artifact 或覆盖首次注入 evidence。

### V1-F6-05：preparation 或 artifact 失败时重建无 map prompt

- **优先级**：P0
- **依赖**：V1-F6-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、preparation/finalization 失败路径
- **输出**：两类增强层失败降级测试
- **允许修改路径**：`engine.py`、`map_context.py`、相关 tests
- **禁止修改边界**：不得把正常 broad fallback 标记为 failure
- **步骤**：preparation 失败直接无 map 继续；artifact 失败清除 current map、丢弃含 map prompt并重新 main_model build；不重复 preparation。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：增强层失败不阻断 Pico，主模型不会收到不可审计 map。
- **回退条件**：失败后重复 preparation，或含 map prompt 在证据失败后仍发送。

### V1-F6-06：repo map 无法共存时重建无 map prompt

- **优先级**：P0
- **依赖**：V1-F6-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、`base_prompt_cannot_fit_with_repo_map_reservation` build 结果
- **输出**：Engine 清除 map、丢弃含 map prompt、重建无 map prompt 的测试
- **允许修改路径**：`pico/pico/core/engine.py`、相关 acceptance tests
- **禁止修改边界**：不得要求 ContextManager 修改 map body；不得重新运行 MapEngine
- **步骤**：识别整段 omission/request_over_budget 结果；清除 current_map_context；重建无 repo map prompt；保留可审计 omission 事实。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_context_governance_acceptance.py -q
  ```
- **完成标准**：repo map 与 base prompt 无法共存时不会发送含 map prompt，也不会二次裁剪 map body。
- **回退条件**：通过删减 map body绕过降级，或重建时重复检索。

### V1-F6-07：执行最终请求硬门禁与模型调用计数

- **优先级**：P0
- **依赖**：V1-F6-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、无 map/有 map PromptBuildResult、runtime ModelRequestBudget
- **输出**：provider 前硬门禁、`main_model_calls` 与 trace 顺序测试
- **允许修改路径**：`pico/pico/core/engine.py`、TaskState 最小适配、相关 tests
- **禁止修改边界**：不得把 provider 返回的超限错误当作本地门禁；不得在未调用 provider 时增加 main_model_calls
- **步骤**：每次实际 provider 调用前检查 request_over_budget；超预算时不发送 model_requested、不调用 provider；实际调用前递增 main_model_calls。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_engine_acceptance.py pico\tests\test_context_governance_acceptance.py -q
  ```
- **完成标准**：无 repo map prompt 仍超预算时本地失败；attempts、main_model_calls、selector_model_calls 语义分离。
- **回退条件**：超预算请求到达 provider，或模型调用统计与实际调用不一致。

### V1-F6-08：所有退出路径统一清理 current map

- **优先级**：P0
- **依赖**：V1-F6-04、V1-F6-05、V1-F6-06、V1-F6-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、Engine 所有结束路径
- **输出**：completed/failed/stopped/step-limit/retry-limit/over-budget 清理测试
- **允许修改路径**：`pico/pico/core/engine.py`、相关 tests
- **禁止修改边界**：不得只为行数门禁复制多处清理逻辑
- **步骤**：选择保持控制流内聚的统一清理接缝；覆盖所有退出路径；记录行数门禁判断。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_engine_acceptance.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：所有结束路径 current map 为 None，其他 current run 状态行为不回归。
- **回退条件**：清理逻辑分散、遗漏或破坏现有 finalize 行为。

### V1-F6-09：增加 Branch A scripted acceptance test

- **优先级**：P0
- **依赖**：V1-F6-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、阶段 6 全部行为
- **输出**：完整 Branch A scripted end-to-end acceptance
- **允许修改路径**：Branch A acceptance fixture/tests
- **禁止修改边界**：不得依赖真实模型
- **步骤**：覆盖明确文件、symbol-only/精确 DefinitionRecord 前缀、统一主模型导航模板、`focus_files_display`/`active_repo_map_text` 来源、首个 read_file、tool loop、artifacts、预算、trace/report、所有失败和超预算降级；验证主模型保持单一组合 prompt，不增加 provider-level system prompt。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_branch_a_acceptance.py pico\tests\test_map_context_evidence_acceptance.py pico\tests\test_engine_acceptance.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：阶段 6 门禁通过；Branch A 使用统一导航模板且变量来源准确；形成首个可运行 MapCode v1 垂直切片。
- **回退条件**：测试依赖真实模型或不能证明 evidence、预算门禁与实际 prompt/provider 调用一致。
