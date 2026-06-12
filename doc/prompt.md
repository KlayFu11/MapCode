# MapCode v1 Implementation Prompt

## 项目目标

基于 Pico 当前 runtime 增量实现 MapCode 产品 v1；当前实现契约以 `SPEC_v1_3.md` 为准：在首次主模型调用前使用确定性 MapEngine 生成 broad/focused repo map，按最终模型输入预算原子注入完整 repo map section，并通过 artifact、trace、report、terminal 和 retrieval eval 完整复盘上下文选择与请求预算决策。

## 当前项目阶段

- `vibe-prac` 阶段三任务拆分已完成。
- 实现必须从 `doc/tasks/v1/progress.md` 中第一个未完成且依赖已满足的任务开始。
- 当前首个任务是 `V1-F0-01 校准根目录 Git baseline 与 .gitignore`。

## 必读文件

每次实现任务开始前必须读取：

1. `AGENT.md`，或阶段 0 统一后的唯一规则入口。
2. 阶段 0 文档迁移前：
   - `PRD_v1_1.md`
   - `SPEC_v1_3.md`
   - `FuncFlow_v1_3.md`
3. 阶段 0 文档迁移后：
   - `doc/PRD.md`
   - `doc/SPEC.md`
   - `doc/FuncFlow.md`
4. `doc/tasks/progress_cross.md`
5. `doc/tasks/v1/progress.md`
6. 当前任务所属的 `doc/tasks/v1/<module>.md`
7. 与当前任务直接相关的真实 Pico/Aider 源码接缝。

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
- `pico/`、`src/` 等目录片段不进入 `mentioned_files`，不新增 `mentioned_dirs`；目录类请求进入 Branch B fuzzy，目录路径只作为 selector 软偏好。
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

1. 从 `doc/tasks/v1/progress.md` 选择第一个未完成且依赖已满足的任务。
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
