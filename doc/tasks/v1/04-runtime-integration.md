# 04 Runtime Integration Tasks

## 模块目标

在不改变 Pico 主模型 prompt 的前提下，完成 MapEngine feature 配置、ModelRequestBudget 解析与 Runtime 持有、Coordinator、RunStore、TaskState、retrieval 事件、reporter 和 selector 双角色 provider 适配。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 第九、十、十三、十四、十六、十七章。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 3 全部门禁通过。

## 模块通用边界

- **允许修改**：Pico 配置、CLI、Runtime 装配、budget resolver、`core/map_context.py`、reporter、RunStore、TaskState、runtime events、worker runtime、provider adapter 与对应测试。
- **禁止修改**：ContextManager repo map 注入、Engine Branch A/B 控制流、MapEngine 确定性算法。
- **模块原则**：Runtime 持有服务对象、请求硬门禁和当前 run 状态；Coordinator 只做数据适配；Reporter 只投影已有 evidence。

## 任务列表

### V1-F4-01：增加 `.pico.toml [features]` 和 `--map-engine`

- **优先级**：P0
- **依赖**：V1-F3-11
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：配置解析、CLI flag、默认关闭测试
- **允许修改路径**：`pico/pico/config/__init__.py`、`pico/pico/cli.py`、配置文档与测试
- **禁止修改边界**：不得初始化或运行 MapEngine
- **步骤**：增加项目配置 features section；CLI 显式参数覆盖 TOML；传入 runtime feature flags。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_pico.py -q
  ```
- **完成标准**：默认关闭；CLI 与 TOML 可显式启用；原有配置优先级保持。
- **回退条件**：破坏 provider/sandbox 配置或默认行为。

### V1-F4-02：解析 ModelRequestBudget 配置契约

- **优先级**：P0
- **依赖**：V1-F4-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、已批准预算契约、V1-F1-08
- **输出**：CLI/TOML/provider profile/fallback 预算解析与配置测试
- **允许修改路径**：`pico/pico/config/__init__.py`、`pico/pico/cli.py`、`pico/pico/core/model_request_budget.py`、对应测试
- **禁止修改边界**：不得修改 MapEngine config；不得静默接受非法显式配置
- **步骤**：实现 `--model-input-budget-tokens`、`--prompt-safety-margin-tokens`、`[model_request_budget]`、provider profile 与 fallback 优先级；fallback 固定 32,768/1,024。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_model_request_budget.py pico\tests\test_pico.py -q
  ```
- **完成标准**：解析 source 准确；显式非法 budget/margin 启动失败；未知模型不使用 DEFAULT_CONTEXT_WINDOW 作为硬门禁。
- **回退条件**：预算与 `max_new_tokens` 混淆，或第三方网关模型名触发未经验证的硬编码窗口。

### V1-F4-03：Runtime 装配 MapEngine、预算对象和 current map

- **优先级**：P0
- **依赖**：V1-F4-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：Runtime 对象装配、不可变 `model_request_budget` 和 `current_map_context=None`
- **允许修改路径**：`pico/pico/core/runtime.py`、`core/map_context.py`、对应测试
- **禁止修改边界**：启动时不得扫描、解析、排名或生成 repo map
- **步骤**：runtime 初始化时解析一次并持有预算；feature 开启时创建 MapEngine/Coordinator，关闭时保持 None；初始化只加载允许的轻量 metadata。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_model_request_budget.py pico\tests\test_map_context.py pico\tests\test_pico.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：ContextManager、selector 路径和最终主模型调用可读取同一预算对象；启动无 repo scan。
- **回退条件**：预算在不同请求路径重复解析，或把 MapEngine 算法塞入 Runtime。

### V1-F4-04：child runtime 关闭 MapEngine 并保留预算

- **优先级**：P0
- **依赖**：V1-F4-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、父 runtime feature flags 与 ModelRequestBudget
- **输出**：child feature flags override、预算传递与测试
- **允许修改路径**：`pico/pico/core/worker_runtime.py`、`pico/tests/test_agent_workers_acceptance.py`
- **禁止修改边界**：不得启用 child MapEngine；不得改变其他 inherited feature flags
- **步骤**：复制父 feature flags 后设置 `map_engine=False`；child 仍持有自己的不可变预算引用/值；验证父 runtime 不受影响。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_agent_workers_acceptance.py -q
  ```
- **完成标准**：所有 child runtime 默认禁用 MapEngine，但最终 provider 请求仍受 ModelRequestBudget 门禁。
- **回退条件**：父子共享可变 feature flags、child 丢失请求门禁或影响其他 worker 行为。

### V1-F4-05：RunStore 增加原子 JSON artifact

- **优先级**：P0
- **依赖**：V1-F4-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`write_json_artifact()` 与编号/原子写测试
- **允许修改路径**：`pico/pico/core/run_store.py`、`pico/tests/test_run_store.py`
- **禁止修改边界**：不得写 MapEngine 专用 envelope 或业务逻辑
- **步骤**：复用 `_write_json_atomic`；按 stem 自动编号；返回稳定 path。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_run_store.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：JSON artifact 写入属于 RunStore 通用核心职责；必要时合理提高行数门禁并记录原因。
- **回退条件**：RunStore 混入 MapContext 组装或 evidence 语义。

### V1-F4-06：TaskState 增加 MapContext 与模型调用摘要

- **优先级**：P0
- **依赖**：V1-F4-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`map_context_summary`、`main_model_calls`、`selector_model_calls` 字段与兼容测试
- **允许修改路径**：`pico/pico/core/task_state.py`、对应测试
- **禁止修改边界**：不得保存完整 MapContextResult、repo map 或完整 evidence
- **步骤**：增加默认值和 from/to dict；区分 attempts、main model calls、selector calls；验证旧 task state 兼容。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_run_store.py pico\tests\test_pico.py -q
  ```
- **完成标准**：TaskState 只保存轻量摘要和准确调用计数事实。
- **回退条件**：把 attempts 当作实际模型调用数，或持久化完整当前 run 对象。

### V1-F4-07：注册 retrieval trace phase 与事件

- **优先级**：P0
- **依赖**：V1-F4-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：retrieval phase 映射与事件标准化测试
- **允许修改路径**：`pico/pico/core/runtime_events.py`、`pico/tests/test_runtime_evidence_acceptance.py`
- **禁止修改边界**：不得新增旁路 TraceWriter
- **步骤**：注册 run-level map 事件；保留 selector candidate counts、input chars 和预算/omission 摘要承载位置；验证 phase 与状态。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_runtime_evidence_acceptance.py -q
  ```
- **完成标准**：所有 run-level map trace 继续经 `runtime.emit_trace()`。
- **回退条件**：新增独立 trace writer 或事件 phase 不一致。

### V1-F4-08：实现 Coordinator 数据适配与 selector catalog 接口

- **优先级**：P0
- **依赖**：V1-F4-05、V1-F4-06、V1-F4-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、MapEngine 公共接口
- **输出**：`MapContextCoordinator` analyze/prepare/build_selector_catalog/finalize 接口骨架与 adapter tests
- **允许修改路径**：`pico/pico/core/map_context.py`、`pico/tests/test_map_context.py`
- **禁止修改边界**：不得调用模型、`ask_user()`、决定 Branch 或执行 selector 请求预算门禁
- **步骤**：注入 Runtime/MapEngine/RunStore 依赖；适配 MapEngine 结果、同 snapshot catalog、trace 和持久化接口；先使用 DTO 测试。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context.py -q
  ```
- **完成标准**：Coordinator 能返回同 snapshot 的 SelectorCandidateCatalog，无控制面越界。
- **回退条件**：Coordinator 成为第二个 Engine、直接构建主模型 prompt 或自行判断 selector 超预算。

### V1-F4-09：实现 MapEngineConsoleReporter

- **优先级**：P0
- **依赖**：V1-F4-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、依赖任务产物、结构化 evidence
- **输出**：纯 evidence 投影 reporter 与测试
- **允许修改路径**：`pico/pico/core/map_context_reporter.py`、对应测试
- **禁止修改边界**：不得运行检索、写 trace/artifact 或直接控制 CLI/TUI
- **步骤**：渲染 index、broad、focused、fallback、failure 和 token budget 摘要；缺失 artifact path 时不得伪造。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context.py pico\tests\test_runtime_evidence_acceptance.py pico\tests\test_agent_workers_acceptance.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：Reporter 只投影已有 evidence，不产生新事实。
- **回退条件**：Reporter 产生 evidence 中不存在的新事实。

### V1-F4-10：扩展 provider 双角色 selector 请求适配

- **优先级**：P0
- **依赖**：V1-F4-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、V1-F1-06 `SelectorModelRequest`、Pico 现有 provider adapter
- **输出**：支持可选 selector system prompt 的 provider adapter 与 OpenAI/Anthropic payload tests
- **允许修改路径**：`pico/pico/providers/base.py`、`pico/pico/providers/clients.py`、provider adapter tests
- **禁止修改边界**：不得改变主模型现有单组合 prompt 行为；不得新增第二套模型客户端或公开 runtime API；不得把 system prompt 拼入 user prompt
- **步骤**：为现有 completion adapter 增加可选 selector `system_prompt`；OpenAI-compatible 映射到协议原生 instructions/system 字段，Anthropic-compatible 映射到顶层 system 字段，动态 prompt 保持 user role；未提供 system prompt 时 payload 与现有主模型行为一致。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_provider_clients.py pico\tests\test_pico.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico\providers pico\tests
  ```
- **完成标准**：selector 可通过同一 provider/runtime 调用链保持 system/user 角色分离；主模型无 system prompt 时行为不变；阶段 4 门禁通过。
- **回退条件**：system/user 被拼接为单一 user prompt、主模型 provider payload 发生未批准变化，或引入第二套 provider 调用链。
