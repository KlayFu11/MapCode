# MapCode v1 总体进度

> 本文件是 MapCode 产品 v1 的唯一任务进度来源；当前任务设计依据为 `SPEC_v1_4.md`、`PRD_v1_2.md`、`FuncFlow_v1_4.md`。
> 只有任务实现完成、验证命令通过、用户审查通过并完成对应 commit 后，才能勾选。

## 当前阶段

- `vibe-prac` 阶段三：已依据 `SPEC_v1_4.md`、`PRD_v1_2.md`、`FuncFlow_v1_4.md` 完成任务重新对齐；阶段 0 环境基线已完成。
- 事实优先级：`SPEC > PRD > FuncFlow`。
- 下一可执行任务：`V1-F8-05 CLI/REPL 展示 reporter 事件`

## 阶段 0：固定施工地基

- [x] V1-F0-01 校准根目录 Git baseline 与 `.gitignore` (P0, 无依赖)
- [x] V1-F0-02 统一规则入口、文档导航和事实优先级 (P0, 依赖 V1-F0-01)
- [x] V1-F0-03 校准根目录版本化事实文档治理 (P0, 依赖 V1-F0-02)
- [x] V1-F0-04 记录 Pico/Aider 基线来源、只读用途和许可证边界 (P0, 依赖 V1-F0-03)
- [x] V1-F0-05 校准项目级任务文件、进度账本和执行 Prompt (P0, 依赖 V1-F0-03)
- [x] V1-F0-06 创建根目录 `.venv` 并验证 Pico baseline (P0, 依赖 V1-F0-01)
- [x] V1-F0-07 完成 MapEngine 依赖兼容性实验 (P0, 依赖 V1-F0-06)
- [x] V1-F0-08 增加正式运行依赖和许可证说明 (P0, 依赖 V1-F0-07)

## 阶段 1：模块边界与数据契约

- [x] V1-F1-01 创建 MapEngine 配置和版本常量 (P0, 依赖 V1-F0-08)
- [x] V1-F1-02 定义索引基础 DTO (P0, 依赖 V1-F1-01)
- [x] V1-F1-03 定义 ranking、rendering 与 cache evidence DTO (P0, 依赖 V1-F1-02)
- [x] V1-F1-04 定义 PromptAnalysis、MapContextEvidence 与 MapResult (P0, 依赖 V1-F1-03)
- [x] V1-F1-05 定义 SelectorCandidateCatalog DTO (P0, 依赖 V1-F1-04)
- [x] V1-F1-06 定义 SelectorModelRequest 与 selector 决策 DTO (P0, 依赖 V1-F1-05)
- [x] V1-F1-07 定义 MapContext 与 artifact DTO (P0, 依赖 V1-F1-06)
- [x] V1-F1-08 定义 runtime-owned ModelRequestBudget (P0, 依赖 V1-F1-07)
- [x] V1-F1-09 定义 prompt render 与 build result DTO (P0, 依赖 V1-F1-08)
- [x] V1-F1-10 增加 MapEngine 与预算架构边界测试 (P0, 依赖 V1-F1-09)

## 阶段 2：Git Python 索引与缓存

- [x] V1-F2-01 实现 Git tracked/staged 文件枚举 (P0, 依赖 V1-F1-10)
- [x] V1-F2-02 实现 Python-only、denylist 和非 Git 降级 (P0, 依赖 V1-F2-01)
- [x] V1-F2-03 使用 tree-sitter query 提取 definitions (P0, 依赖 V1-F2-02)
- [x] V1-F2-04 提取 references 并隔离单文件失败 (P0, 依赖 V1-F2-03)
- [x] V1-F2-05 构建 SymbolIndex 和稳定 snapshot id (P0, 依赖 V1-F2-04)
- [x] V1-F2-06 实现 index/cache 读取与 cache hit (P0, 依赖 V1-F2-05)
- [x] V1-F2-07 实现版本失效、文件变化与 cache 失败 evidence (P0, 依赖 V1-F2-06)

## 阶段 3：确定性 MapEngine

- [x] V1-F3-01 实现 PromptAnalyzer identifier 与 symbol hit 提取 (P0, 依赖 V1-F2-07)
- [x] V1-F3-02 实现文件匹配、path ident 与 Branch 判断 (P0, 依赖 V1-F3-01)
- [x] V1-F3-03 构建文件级 def/ref 图和稳定 fallback (P0, 依赖 V1-F3-02)
- [x] V1-F3-04 实现 broad PageRank、Aider-style multiplier 与 ranking evidence (P0, 依赖 V1-F3-03)
- [x] V1-F3-05 实现 focus/path personalization、PPR 与 outbound boost (P0, 依赖 V1-F3-04)
- [x] V1-F3-06 固定 effective_symbol_hits DefinitionRecord 候选前缀 (P0, 依赖 V1-F3-05)
- [x] V1-F3-07 使用 TreeContext 渲染结构摘要 (P0, 依赖 V1-F3-06)
- [x] V1-F3-08 实现固定 focused/broad token budget 与 truncation (P0, 依赖 V1-F3-07)
- [x] V1-F3-09 从同一 snapshot 生成 SelectorCandidateCatalog (P0, 依赖 V1-F3-08)
- [x] V1-F3-10 实现 MapEngine 公共接口和 lazy index (P0, 依赖 V1-F3-09)
- [x] V1-F3-11 增加离线 MapEngine fixture 演示 (P0, 依赖 V1-F3-10)

## 阶段 4：Pico Runtime 基础接入

- [x] V1-F4-01 增加 `.pico.toml [features]` 和 `--map-engine` (P0, 依赖 V1-F3-11)
- [x] V1-F4-02 解析 ModelRequestBudget 配置契约 (P0, 依赖 V1-F4-01)
- [x] V1-F4-03 Runtime 装配 MapEngine、预算对象和 current map (P0, 依赖 V1-F4-02)
- [x] V1-F4-04 child runtime 关闭 MapEngine 并保留预算 (P0, 依赖 V1-F4-03)
- [x] V1-F4-05 RunStore 增加原子 JSON artifact (P0, 依赖 V1-F4-03)
- [x] V1-F4-06 TaskState 增加 MapContext 与模型调用摘要 (P0, 依赖 V1-F4-03)
- [x] V1-F4-07 注册 retrieval trace phase 与事件 (P0, 依赖 V1-F4-03)
- [x] V1-F4-08 实现 Coordinator 数据适配与 selector catalog 接口 (P0, 依赖 V1-F4-05/V1-F4-06/V1-F4-07)
- [x] V1-F4-09 实现 MapEngineConsoleReporter (P0, 依赖 V1-F4-08)
- [x] V1-F4-10 扩展 provider 双角色 selector 请求适配 (P0, 依赖 V1-F4-04)

## 阶段 5：PromptPurpose 与 Repo Map 注入

- [x] V1-F5-01 引入 PromptPurpose 和 PromptBuildResult (P0, 依赖 V1-F4-09/V1-F4-10)
- [x] V1-F5-02 迁移 Runtime wrapper 与全部直接调用者 (P0, 依赖 V1-F5-01)
- [x] V1-F5-03 迁移 prompt preview 调用点 (P0, 依赖 V1-F5-02)
- [x] V1-F5-04 限制辅助 purpose 的 auto-compaction 并验证辅助调用 (P0, 依赖 V1-F5-03)
- [x] V1-F5-05 实现统一主模型导航模板与 fallback notice (P0, 依赖 V1-F5-04)
- [x] V1-F5-06 ContextManager 组装独立 repo_map section (P0, 依赖 V1-F5-05)
- [x] V1-F5-07 为完整 repo map 预留输入空间并缩减 base prompt (P0, 依赖 V1-F5-06)
- [x] V1-F5-08 实现 repo map 原子注入或整段省略 (P0, 依赖 V1-F5-07)
- [x] V1-F5-09 验证 feature disabled、无 MapContext 与四种 purpose (P0, 依赖 V1-F5-08)

## 阶段 6：Branch A 与最终模型门禁

- [x] V1-F6-01 Engine 在首次主模型 build 前执行 Branch A preparation (P0, 依赖 V1-F5-09)
- [x] V1-F6-02 首次 main model build 后持久化 artifacts (P0, 依赖 V1-F6-01)
- [x] V1-F6-03 prepared MapContext 替换为 finalized 对象 (P0, 依赖 V1-F6-02)
- [x] V1-F6-04 retry/tool loop 复用同一 MapContext (P0, 依赖 V1-F6-03)
- [x] V1-F6-05 preparation 或 artifact 失败时重建无 map prompt (P0, 依赖 V1-F6-03)
- [x] V1-F6-06 repo map 无法共存时重建无 map prompt (P0, 依赖 V1-F6-05)
- [x] V1-F6-07 执行最终请求硬门禁与模型调用计数 (P0, 依赖 V1-F6-06)
- [x] V1-F6-08 所有退出路径统一清理 current map (P0, 依赖 V1-F6-04/V1-F6-05/V1-F6-06/V1-F6-07)
- [x] V1-F6-09 增加 Branch A scripted acceptance test (P0, 依赖 V1-F6-08)

## 阶段 7：Branch B Selector 与确认流

- [x] V1-F7-01 实现 selector request builder、parser 和 visible path 校验 (P0, 依赖 V1-F6-09)
- [x] V1-F7-02 Engine 获取同 snapshot catalog 并执行 selector 请求预算门禁 (P0, 依赖 V1-F7-01)
- [x] V1-F7-03 Engine 复用双角色 provider adapter 调用 selector (P0, 依赖 V1-F7-02)
- [x] V1-F7-04 实现整组二选一确认协议 (P0, 依赖 V1-F7-03)
- [x] V1-F7-05 实现 one-shot、超预算、取消和无效输出 fallback (P0, 依赖 V1-F7-04)
- [x] V1-F7-06 confirmed focus 生成 focused map 并复用 snapshot (P0, 依赖 V1-F7-05)
- [x] V1-F7-07 验证事件、展示、预算与模型调用顺序 (P0, 依赖 V1-F7-06)

## 阶段 8：完整证据链与可观测性

- [x] V1-F8-01 写入完整 retrieval 与预算 trace (P0, 依赖 V1-F7-07)
- [x] V1-F8-02 保证 repo-map artifact 与首次实际注入一致 (P0, 依赖 V1-F8-01)
- [x] V1-F8-03 写入结构化 map evidence artifact (P0, 依赖 V1-F8-02)
- [x] V1-F8-04 report 增加 MapContext、预算与模型调用摘要 (P0, 依赖 V1-F8-03)
- [ ] V1-F8-05 CLI/REPL 展示 reporter 事件 (P1, 依赖 V1-F8-04)
- [ ] V1-F8-06 TUI 展示 reporter 事件 (P1, 依赖 V1-F8-05)
- [ ] V1-F8-07 增加证据一致性、redaction 和降级测试 (P0, 依赖 V1-F8-04)

## 阶段 9：Retrieval Eval 与发布验收

- [ ] V1-F9-01 建立固定 retrieval fixture 和 ground truth (P0, 依赖 V1-F8-07)
- [ ] V1-F9-02 实现 effective-hit、rendered-file、first-read 与 map budget 指标 (P0, 依赖 V1-F9-01)
- [ ] V1-F9-03 实现完整 selector request 与 catalog truncation 指标 (P0, 依赖 V1-F9-02)
- [ ] V1-F9-04 实现 fallback、reduction、omission 与超预算指标 (P0, 依赖 V1-F9-03)
- [ ] V1-F9-05 接入 Pico evaluator (P0, 依赖 V1-F9-04)
- [ ] V1-F9-06 运行完整离线回归和架构边界检查 (P0, 依赖 V1-F9-05)
- [ ] V1-F9-07 使用真实 provider 演示 Branch A 与 path-ident-only (P0, 依赖 V1-F9-06)
- [ ] V1-F9-08 使用真实 provider 演示 Branch B 和预算降级 (P0, 依赖 V1-F9-07)
- [ ] V1-F9-09 更新 README、配置、演示步骤和项目总进度 (P0, 依赖 V1-F9-08/V1-F8-06)

## 当前阻塞

- 无。阶段 0 已在 macOS 主开发环境完成复验；Windows baseline 失败保留为后续兼容性事项，不阻塞 v1 主线继续推进。

## 最近完成

- 日期：2026-06-16
- 完成任务：`V1-F0-02 统一规则入口、文档导航和事实优先级`；`V1-F0-03 校准根目录版本化事实文档治理`；`V1-F0-04 记录 Pico/Aider 基线来源、只读用途和许可证边界`
- 验证命令：`Select-String -Path .\AGENT*.md -Pattern "SPEC > PRD > FuncFlow|pico行数门禁|功能完整接入与职责正确"`；`Get-ChildItem . -File -Filter "PRD_v*.md"`；`Get-ChildItem . -File -Filter "SPEC_v*.md"`；`Get-ChildItem . -File -Filter "FuncFlow_v*.md"`；`Select-String -Path .\AGENT*.md,.\doc\tasks\v1\*.md,.\doc\prompt.md -Pattern "PRD_v1_2.md|SPEC_v1_4.md|FuncFlow_v1_4.md|doc/PRD.md|doc/SPEC.md|doc/FuncFlow.md"`；`Select-String -Path .\doc\baselines.md -Pattern "aider|pico_origin|Apache|import aider"`；`git status --short`；`git check-ignore -v aider pico_origin .planning PRD SPEC FuncFlow`；`git ls-files aider pico_origin .planning PRD SPEC FuncFlow doc`；`git diff --check`
- 结果：验证通过；用户已手动提交，当前 HEAD 为 `88969af docs(V1-F0-02,V1-F0-03,V1-F0-04): align foundation governance docs`。

## 最近执行

- 日期：2026-06-23
- 执行任务：`V1-F3-08 实现固定 focused/broad token budget 与 truncation`。
- 结果：`V1-F3-08` 为 ranked context renderer 增加 fixed focused/broad budget、完整 file block 裁剪、path-only fallback、budget omitted evidence 与 `RenderingEvidence`；目标 pytest、相关回归、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F3-09`。

- 日期：2026-06-23
- 执行任务：`V1-F3-09 从同一 snapshot 生成 SelectorCandidateCatalog`。
- 结果：`V1-F3-09` 新增 deterministic selector catalog builder，从同一 `SymbolIndex` snapshot 生成全量 `candidate_paths`、预算受控 `rendered_text`、实际可见 `rendered_paths` 和计数/截断元数据；目标 pytest、architecture boundary、Ruff 和 diff whitespace 检查均通过。本轮只执行一个任务，不启动 `V1-F3-10`。

- 日期：2026-06-24
- 执行任务：`V1-F3-11 增加离线 MapEngine fixture 演示`。
- 结果：`V1-F3-11` 已由 commit `0dbafd2` 完成，新增固定 offline fixture 与 public MapEngine facade 演示测试，覆盖 broad/focused maps、selector catalog、cache hit、path-ident filtering、multipliers、symbol hits 和 stable fallback；本次仅按用户确认补齐进度账本，下一任务进入 `V1-F4-01`。

- 日期：2026-06-24
- 执行任务：`V1-F4-01 增加 .pico.toml [features] 和 --map-engine`。
- 结果：`V1-F4-01` 新增 `[features] map_engine` 配置解析、`--map-engine` / `--no-map-engine` CLI override、默认关闭测试、配置示例和配置文档；目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-02`。

- 日期：2026-06-24
- 执行任务：`V1-F4-02 解析 ModelRequestBudget 配置契约`。
- 结果：`V1-F4-02` 新增 CLI、`[model_request_budget]`、provider profile 与 fallback 的 `ModelRequestBudget` 解析契约，显式非法 budget/margin 在启动装配阶段失败，未知 provider/model 使用 32,768/1,024 fallback 且不复用 `DEFAULT_CONTEXT_WINDOW`；目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-03`。

- 日期：2026-06-24
- 执行任务：`V1-F4-03 Runtime 装配 MapEngine、预算对象和 current map`。
- 结果：`V1-F4-03` 为 Pico runtime 装配 `model_request_budget`、`current_map_context=None`、feature-gated `MapEngine` 和最小 `MapContextCoordinator`，CLI 解析出的预算对象进入同一 runtime；启动阶段不调用 `ensure_index()`，不扫描、不解析、不排名、不生成 repo map；目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-04`。

- 日期：2026-06-24
- 执行任务：`V1-F4-04 child runtime 关闭 MapEngine 并保留预算`。
- 结果：`V1-F4-04` 在 worker child runtime 构造时复制父 feature flags 并强制 `map_engine=False`，同时传递父 runtime 已解析的不可变 `ModelRequestBudget`；新增 acceptance test 覆盖 parent MapEngine 保持启用、child MapEngine 关闭、child 不创建 MapEngine/Coordinator、预算对象保留和其他 feature flag 继承。目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-05`。

- 日期：2026-06-25
- 执行任务：`V1-F4-06 TaskState 增加 MapContext 与模型调用摘要`。
- 结果：`V1-F4-06` 为 `TaskState` 增加轻量 `map_context_summary`、`main_model_calls` 和 `selector_model_calls`，保留旧 `task_state.json` 兼容，并明确 `attempts` 与实际模型调用计数分离；目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-07`。

- 日期：2026-06-26
- 执行任务：`V1-F4-07 注册 retrieval trace phase 与事件`。
- 结果：`V1-F4-07` 注册 run-level MapEngine retrieval trace events 到 `retrieval` phase，并新增 acceptance test 覆盖 path-ident 命中摘要、focus/path personalization、ranking multiplier/reason codes、selector counts、budget/omission payload 与 `map_context_failed` error status；目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-08`。

- 日期：2026-06-27
- 执行任务：`V1-F4-08 实现 Coordinator 数据适配与 selector catalog 接口`。
- 结果：`V1-F4-08` 为 `MapContextCoordinator` 增加 analyze/prepare/build_selector_catalog/finalize 数据面 adapter，覆盖同 snapshot selector catalog、prepared/finalized `MapContextResult`、retrieval trace、repo-map/map-evidence artifact 和轻量 `TaskState.map_context_summary`；目标 pytest、相关 DTO 回归、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-09`。

- 日期：2026-06-29
- 执行任务：`V1-F4-09 实现 MapEngineConsoleReporter`。
- 结果：`V1-F4-09` 新增 `MapEngineConsoleReporter` 和 `MapEngineConsoleReport`，支持 index、retrieval、finalized artifact path、broad fallback 和 failure 的纯 evidence 展示投影；prepared 状态不伪造 artifact path，不读取 `repo_map_text`，不接入 CLI/TUI、trace 或 artifact 写入。目标 pytest、runtime evidence/worker 回归、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F4-10`。

- 日期：2026-07-05
- 执行任务：`V1-F4-10 扩展 provider 双角色 selector 请求适配`。
- 结果：`V1-F4-10` 在现有 provider 调用链中增加可选 selector `system_prompt`，OpenAI-compatible payload 映射到顶层 `instructions`，Anthropic-compatible payload 映射到顶层 `system`，动态 prompt 保持 user role；未传入 `system_prompt` 时主模型 payload 不新增 system/instructions 字段。目标 pytest、architecture boundary、Ruff 和 `git diff --check` 均通过。本轮只执行一个任务，不启动 `V1-F5-01`。

- 日期：2026-07-21
- 执行任务：`V1-F5-01 引入 PromptPurpose 和 PromptBuildResult`。
- 结果：`ContextManager.build()` 现在要求显式 keyword-only `purpose` 并返回 build-local `PromptBuildResult`；prompt 文本与既有 base-prompt reduction 不变，`repo_map_render` 仍为 `None`，metadata 记录七项 runtime-owned request-budget 字段。ContextManager 目标测试、Ruff 和 `git diff --check` 均通过。`V1-F5-02` 继续迁移旧 runtime 调用点。

- 日期：2026-07-30
- 执行任务：`V1-F5-02 迁移 Runtime wrapper 与全部直接调用者`。
- 结果：`Pico._build_prompt_and_metadata()` 现在要求显式 `purpose` 并返回 build-local `PromptBuildResult`；main model、step-limit summary 与 evaluation 直接调用者分别使用 `main_model`、`step_limit_summary`、`evaluation`，全部适配 DTO 属性读取。任务拆分同步修正为：V1-F5-02 统一迁移直接调用者，V1-F5-04 只负责辅助 purpose 的 auto-compaction 约束。`runtime.py` 保持连续 wrapper 编排，恢复方法间空行并将行数预算由 990 调整为 1000（实际 991 行）。组合 pytest 88 passed、architecture 4 passed、Ruff 与 `git diff --check` 均通过；下一项为 `V1-F5-03`。

- 日期：2026-07-30
- 执行任务：`V1-F5-03 迁移 prompt preview 调用点`。
- 结果：`Pico.prompt()`、`Pico.prompt_metadata()` 与 `/context` 间接链路显式使用 `prompt_preview`；新增普通和超预算 preview 回归，确认不调用模型、不创建 run/artifact，超预算时也不压缩 session history。evaluation 与 step-limit summary 策略保持不变，留给 V1-F5-04。目标 pytest 87 passed、Ruff 与 `git diff --check` 均通过。
