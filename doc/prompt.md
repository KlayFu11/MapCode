# MapCode v1 Implementation Prompt

## 项目目标

基于 Pico 当前 runtime 增量实现 MapCode 产品 v1；当前实现契约以 `SPEC_v1_4.md` 为准：在首次主模型调用前使用确定性 MapEngine 分析文件、symbol 和 path-ident 信号，生成 broad/focused repo map，按最终模型输入预算原子注入完整 repo map section，并通过 artifact、trace、report、terminal 和 retrieval eval 完整复盘上下文选择、排名贡献与请求预算决策。

## 当前项目阶段

- `vibe-prac` 阶段三任务拆分已完成。
- 实现必须从 `doc/tasks/v1/progress.md` 中优先选择依赖已满足的 P0 未完成任务；同优先级按进度表顺序执行，没有可执行 P0 时再执行 P1。
- 当前首个任务以 `doc/tasks/v1/progress.md` 为准；完成 `V1-F0-05`、`V1-F0-06`、`V1-F0-07`、`V1-F0-08` 后应进入 `V1-F1-01 创建 MapEngine 配置和版本常量`。

## 三段验收里程碑

1. 第一阶段可展示成果：`F0-F3`。离线 MapEngine 能运行并生成 broad/focused map，不要求 Pico runtime 接入。
2. 第二阶段核心 MVP：`F4-F6`。Pico runtime、MapEngine、prompt injection 和 Branch A 跑通，形成可讲的 MapCode v1 垂直切片，不要求 Branch B selector 或 retrieval eval。
3. 第三阶段完整 v1：`F7-F9`。Branch B selector、完整 evidence、retrieval eval、README/demo 完成；`V1-F8-07` 是核心证据链门禁，`V1-F8-05`/`V1-F8-06` 是 P1 release polish，不阻塞 `V1-F8-07` 或 `V1-F9-01`，但阻塞最终 `V1-F9-09`。

## 必读文件

每次实现任务开始前必须读取：

1. `AGENTS.md`，或阶段 0 统一后的唯一规则入口。
2. 根目录当前活动事实文档：
   - `PRD_v1_2.md`
   - `SPEC_v1_4.md`
   - `FuncFlow_v1_4.md`
3. `doc/tasks/progress_cross.md`
4. `doc/tasks/v1/progress.md`
5. 当前任务所属的 `doc/tasks/v1/<module>.md`
6. 与当前任务直接相关的真实 Pico/Aider 源码接缝。

PRD、SPEC、FuncFlow 始终直接维护在项目根目录，以版本化文件名控制修订；不得创建或切换到 `doc/PRD.md`、`doc/SPEC.md`、`doc/FuncFlow.md`。

## 事实优先级

```text
SPEC > PRD > FuncFlow > doc/tasks > 当前 .planning > 聊天记录
```

发现冲突时停止扩展实现范围，将问题写入当前 `.planning/<task>/findings.md`，按治理规则回退对应项目文档。

## 当前 v1 设计修订固定实现契约

- focused map 固定使用 4,096 tokens，broad map 固定使用 8,192 tokens。
- `effective_symbol_hits` 对应的 `DefinitionRecord` 固定进入 focused 候选前缀。
- `MapEngine.build_selector_catalog()` 和 `MapContextCoordinator.build_selector_catalog()` 返回同一 snapshot 的 `SelectorCandidateCatalog`。
- selector 请求使用 `SelectorModelRequest(system_prompt, user_prompt, visible_paths)`；provider 必须保留 system/user 角色，主模型继续使用单一组合 prompt。
- selector `visible_paths` 是 broad rendered files 与 catalog `rendered_paths` 的稳定并集；`candidate_paths` 只证明 snapshot 来源，隐藏 candidate 必须拒绝。
- 完整 `system_prompt + user_prompt` 参与 ModelRequestBudget 门禁。
- `pico/`、`src/` 等目录样式片段不进入 `mentioned_files`，不新增 `mentioned_dirs`；它们通过 `mentioned_idents` 与 indexed path terms 匹配形成 path-ident 事实，有效命中时进入 Branch A，但不形成文件 focus、目录 scope 或读取授权。
- Branch B 只在 `mentioned_files`、`effective_symbol_hits`、`path_ident_hits` 均为空时触发；selector system prompt 不包含目录偏好规则。
- `focus_personalization_files` 与 `path_personalization_files` 分离，`personalization_files` 是稳定并集；只有 focus personalization files 获得 `FOCUS_OUTBOUND_BOOST`。
- trace/evidence/eval 必须保留原始 path ident、全量 `path_ident_hit_files`、图节点过滤、文件级 `prompt_path_ident_hits` 和 Aider-style multiplier/reason codes。
- 普通分析优先 source 文件，仅在明确需要时选择 test 文件。
- Branch A、Branch B focused 和 Branch B broad fallback 使用同一主模型导航模板，由 `focus_files_display` 和 `active_repo_map_text` 驱动；主模型不增加 provider-level system prompt。
- broad fallback 复用原始请求与 broad map，不重跑 selector、不重新询问用户、不要求重新输入 prompt。
- `FallbackReason` 包含 `selector_request_over_budget`。
- `ModelRequestBudget` 解析顺序为 CLI > `[model_request_budget]` > `[providers.<provider>]` profile > fallback。
- fallback input budget 为 32,768 tokens，默认 safety margin 为 1,024 tokens，token 估算为 `ceil(chars / 4)`。
- selector 和最终请求的超预算条件为 `estimated_request_tokens + margin > input budget`。
- ContextManager 不二次裁剪 repo map body；先为完整 repo map section 预留输入空间，再缩减 base prompt，并原子注入或整段省略。
- Engine 负责 selector、用户确认、超预算降级和最终 provider 调用门禁。
- 无 repo map prompt 仍超预算时，不发送 `model_requested`，不调用 provider。

## 执行顺序

1. 从 `doc/tasks/v1/progress.md` 选择依赖已满足的最高优先级未完成任务：先 P0，同优先级按进度表顺序，没有可执行 P0 时再执行 P1。
2. 创建独立 `.planning/<date>-<task-slug>/`：
   - `task_plan.md`
   - `findings.md`
   - `progress.md`
3. 检查 Git 状态；不得覆盖或混入用户已有改动。
4. 读取任务允许修改路径、禁止边界、验证命令和回退条件。
5. 先进行模块归属审查，再考虑行数门禁。
6. 使用 TDD：失败测试 -> 确认失败原因 -> 最小完整实现 -> 验证。
7. 持续更新当前 `.planning` 文件。
8. 将稳定任务、设计或进度变化折叠进项目级文档。
9. 向用户提交任务审查材料。
10. 用户审查通过后才允许 commit 和勾选项目总进度。

## Multi_Agent mode（显式启用）

只有当前用户 Prompt 明确要求“使用多 Agent 执行本次阶段施工”或明确指定 `Multi_Agent mode` 时，才启用本模式。仅讨论、设计、审查或修改多 Agent 规则，不视为启用。

未启用时，完整遵守原有单 Agent 执行顺序、普通子 Agent 规则和逐任务人工 commit gate。启用后，本节只覆盖以下两项默认规则：

1. 主 Agent 从“每次只执行一个任务”改为“每个会话在同一 `V1-F<n>` 阶段中串行执行正常目标 2 个、最多 3 个任务”。
2. commit 与进度更新从“每个任务等待用户批准”改为“reviewer `PASS` 且主 Agent 最终 gate 通过后，允许更新进度并执行单任务 commit，用户在本轮阶段批结束后批量审查”。

其余事实优先级、Pico/Aider 边界、任务允许路径、测试、失败回退、禁止 push 等规则保持不变。

### 主 Agent / coordinator 边界

- 当前会话的主 Agent 直接担任 coordinator，不创建额外 coordinator Agent。
- 每个会话只处理一个 `V1-F<n>` 阶段，只能按 `doc/tasks/v1/progress.md` 和任务依赖顺序串行施工。
- 正常目标是完成 2 个任务，本轮上限是 3 个；阶段完成、context 不足或任一 gate 失败时允许提前停止。
- 主 Agent 使用 planning-with-files 维护每个任务的 `task_plan.md`、`findings.md`、`progress.md`，并负责把子 Agent 返回的内容写入 `plan.md`、`worker-summary.md`、`review.md` 和 `handoff.md`。
- explorer、worker 和 reviewer 只执行主 Agent 派发的当前任务，不得调用 planning-with-files 创建执行文件。

### 每个任务启动前检查

主 Agent 必须在启动每个新任务前检查：

- `git status --short --branch`。
- 当前任务在 `doc/tasks/v1/progress.md` 中仍未完成。
- 当前任务的所有依赖已完成。
- 运行时可见的 context left 不低于 45%。

context left 低于 45% 时，停止启动新任务并输出下一会话恢复 Prompt。如果运行时未提供可靠的 context left，不得猜测；按“无法判断是否安全”停止启动下一任务。

### 单任务固定流程

1. 主 Agent 创建 `.planning/{YYYY-MM-DD}-{task-id-lowercase}-{task-slug}/`，初始化 planning-with-files 标准三文件。
2. 启动只读 explorer：读取任务文档、SPEC、PRD、FuncFlow 和相关代码，返回任务边界、修改/创建文件、变量/类型、验证命令和风险；主 Agent 写入 `plan.md`。
3. 主 Agent 审查 explorer plan；只有计划严格属于单任务边界时才继续。
4. 启动 worker：worker 只允许修改 explorer plan 列出的路径，不得修改 `doc/tasks/v1/progress.md`，不得 commit；主 Agent 将返回内容写入 `worker-summary.md`。
5. 启动 reviewer：审查 `git diff`，执行任务规定的验证命令，检查 SPEC、`AGENTS.md`、`doc/prompt.md` 和允许路径；reviewer 只能返回 `PASS` 或 `FAIL`，不得修改文件或 commit，主 Agent 写入 `review.md`。
6. 主 Agent 执行最终 gate：重跑必要的最小验证命令，检查 `git diff --check`、`git status --short --branch` 和实际修改路径。
7. reviewer `PASS` 且主 Agent gate 通过后，主 Agent 更新 `doc/tasks/v1/progress.md` 对应任务，生成 `handoff.md`，将实现变更与进度勾选放入同一个 commit。commit message 必须包含完整 `TASK_ID`；commit 成功后将 commit hash 追加到 `handoff.md`。
8. commit 成功后才可以检查并启动下一个依赖已满足的任务。

### 停止与批量审查

- 测试失败、依赖不满足、SPEC 冲突、未预期 diff、路径越界、commit 失败或无法判断是否安全时，立即停止，不启动下一任务。未通过双 gate 的任务不得 commit。
- 完成 3 个任务、当前阶段完成、context 不足或任一 gate 失败时，结束本轮。
- 结束时按“每次任务审查交付”格式汇总每个已完成任务的 explorer plan、worker summary、reviewer 结论、主 Agent gate、commit hash 和未提交改动，由用户做阶段批量审查。
- 本模式只允许按上述 gate 自动 commit，不允许自动 push、merge、rebase 或创建 PR。

## 模块拆分与行数门禁原则

```text
功能完整接入与职责正确
> 控制流内聚和可读性
> 可复用性
> 现有行数门禁
```

- 先按职责边界判断代码归属，再处理行数门禁。
- 禁止只为通过行数门禁拆分模块。
- 禁止只为通过行数门禁拆散完整控制流或创建无意义 helper。
- 独立职责、可独立测试或可复用逻辑应拆分。
- 合理实现超过门禁时，优先提高门禁并记录原因。
- 禁止通过提高门禁掩盖职责混乱或明显臃肿。

提高行数门禁时，审查交付必须包含：

```text
涉及文件：
原门禁：
新门禁：
新增代码承担的核心职责：
不适合拆分的原因：
是否引入新的独立职责：
相关测试：
```

## 主 Agent 职责

- 维护项目事实优先级和任务依赖。
- 每次只执行一个 `V1-F<n>-<nn>` 任务。
- 保持任务允许修改路径和禁止边界。
- 对实现进行源码、测试、架构边界和行数门禁审查。
- 不允许子 Agent 修改 `doc/tasks/v1/progress.md`。
- 统一运行阶段门禁并决定是否进入下一阶段。
- 在用户审查前不得自动 commit；不得自动 push。

## 子 Agent / 隔离会话规则

只有两个以上互不修改共享状态的探索或验证任务才使用子 Agent。

每个子 Agent 任务必须包含：

- 任务 ID 和模块名。
- 相关需求与设计摘录。
- 允许读取和修改路径。
- 禁止修改边界。
- 输入、预期输出、验证命令和完成标准。
- 完成后返回的发现与测试结果。

子 Agent 不得：

- 修改项目总进度。
- 改变 SPEC/PRD。
- 自动 commit 或 push。
- 在未授权路径写入文件。

## 测试要求

- 每个行为变化必须先有失败测试。
- 优先运行当前任务目标测试，再运行相关回归。
- 涉及核心模块或依赖边界时运行：

```powershell
.\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
```

- 每个任务完成前运行目标范围 Ruff。
- 每个阶段完成前运行阶段门禁。
- 最终阶段运行：

```powershell
.\.venv\Scripts\python.exe -m pytest pico\tests -q
.\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
```

- 禁止删除、跳过或注释失败测试来通过门禁。

## 进度更新规则

- 当前会话步骤、错误、命令和测试结果写入当前 `.planning/<task>/`。
- 稳定任务边界变化写入对应 `doc/tasks/v1/<module>.md`。
- 稳定设计变化先更新 SPEC。
- 需求范围变化先更新 PRD。
- 任务完成、验证通过、用户审查通过并完成 commit 后，才更新 `doc/tasks/v1/progress.md`。
- 阶段门禁未通过，不进入下一阶段。

## 失败回退规则

- 需求或范围变化：回退 PRD。
- 架构、接口、数据流、状态流转、错误处理或测试策略变化：回退 SPEC。
- 任务过大、依赖错误、验证不足或允许路径不合理：回退模块任务文件。
- 当前实现策略失败或命令反复失败：回退当前任务计划。
- 同一阻塞连续三次无法推进时，向用户报告具体事实和已尝试方案。

## 每次任务审查交付

任务结束时必须提供：

```text
任务 ID：
任务目标：
当前分支：
修改文件：
核心行为变化：
模块归属判断：
行数门禁判断：
已运行验证：
验证结果：
未运行验证及原因：
稳定文档更新：
建议 commit message：
是否存在未提交改动：
```

用户审查通过后，再执行 commit，并更新项目总进度。
