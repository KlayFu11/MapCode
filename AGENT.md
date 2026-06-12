# AGENT.md

## 使用范围

本文件是 `D:\VScodeProject\MapCode` 项目的 Agent 工作规范入口。项目工作先读取本文件；需要调整规范时，先修改本文件，再按新规范执行。


## MapCode项目简介

符号图谱驱动的本地 Coding Agent Harness
MapCode 是一个面向 Agent 应用开发求职场景的本地代码仓库智能体项目，定位为“可解释、可恢复、可评测、可持续运行”的 Coding Agent Harness。项目以 Pico 的本地 Agent Runtime 为工程底座，保留其在模型接入、工具调用、上下文管理、任务恢复、结构化记忆、运行审计与评测闭环上的设计；同时引入 Aider Repo Map 的代码仓库理解能力，将其提炼为独立的 `MapEngine`，作为静态前置检索层与检索决策可观测层接入 Pico。

MapCode 的核心目标不是简单扩大上下文窗口，也不是让模型盲目通过 `read_file` / `search` 逐步试探仓库，而是先通过 tree-sitter 解析源文件，提取 Definition / Reference Tags，构建跨文件符号定义与引用图，并结合 PageRank 在可配置 token 预算内选出与当前任务最相关的文件和符号上下文。由此，Agent 在执行任务前即可获得一份结构化的仓库地图 `repomap.md`，并将其注入 prompt，使模型“带着地图出发”，优先基于符号图谱和检索分数选择上下文，而不是依赖大容量上下文窗口和重复搜索。

项目名称叫做MapCode，但是在完整的功能实现前，代码内部先保留 pico 的骨架命名，等 Aider 风格的 Repo Map 能力抽象成 MapEngine作为上下文选择和仓库理解层接入Pico后能被pico 的 agent runtime 能稳定驱动后，再分阶段重命名为MapCode。**MapCode 本质上是“Pico runtime + MapEngine(repo map 能力增强) + 对外产品化命名”，因此任何开发任务都必须保持 Pico 的模块边界和接口设计为主线，Aider 相关代码只能作为 MapEngine 的设计参考或局部能力来源。**

在 MapCode 中，`MapEngine` 负责仓库结构化分析、符号提取、引用关系建图、PageRank 排名、token-budgeted context packing、缓存复用与检索链路记录；Pico 负责 Agent 执行主循环、工具调用、安全审批、上下文裁剪、任务恢复、trace 记录、报告生成与评测闭环。

目前项目处于第一阶段，不实现 Aider 完整交互规则，不做手动 add-to-chat、editable/read-only 文件状态机、多轮自动刷新、embedding、LSP、完整 call graph 或复杂影响分析。v1 重点是验证 repo map 作为静态前置检索层和检索决策可观测层，能否稳定增强 Pico 的仓库理解与上下文选择能力。

MapCode的价值在于把本地 Coding Agent 的文件选择过程，从“搜索关键词 + 直接读文件 + 依赖模型窗口硬推理”，升级为“AST 符号图谱 + 引用关系建模 + PageRank 相关性排序 + token 预算控制 + 可审计检索链路”。它不仅关注 Agent 是否能完成代码分析或修改任务，更关注 Agent 在长链路本地仓库任务中是否具备上下文选择能力、执行过程可解释性、状态可恢复性、工具副作用可控性以及检索质量可评测性。


## 基本约定

- MapCode 的工程演进必须以 Pico 现有 runtime 作为唯一代码底座。所有从 Aider 抽象出的 RepoMap / MapEngine 能力，都必须作为 Pico 现有功能模块、接口、数
- 据流和执行链路的增强能力接入，而不是另起一个新项目、重建一套 runtime、复制拼接 Pico/Aider 的零散代码片段。除非明确要求重构，否则所有功能实现都应优先在 Pico 当前目录结构、CLI 入口、WorkspaceContext、PromptBuilder、ToolRegistry、Approval、History、Trace / Report 等既有模块上做增量修改。
- 默认使用中文解释；代码、命令、路径、API 字段和变量名保持 English。
- 修改前先确认项目规则和相关文档，避免只依赖聊天上下文。
- 单文件小改可以不创建 `.planning/`；复杂任务按下方长期治理规则执行。
- 修改完成后主动运行可行的验证命令，并记录无法验证的原因。
- 对于pico自定义的行数门禁架构预算，当新增内容确实属于该模块核心职责、是必要的核心编排代码，无法合理拆分时才应提高。不能因为测试失败就直接增加上限，不能用提高门禁来掩饰职责混乱。对于合理的代码，不要强行保持现有的行数限制，而降低可读性。
- 密钥、token、密码不得写入代码，使用 `.env` 或项目指定的密钥机制。


## 文档导航

- MapCode v1 PRD查阅"D:\VScodeProject\MapCode\PRD_v1_1.md"
- MapCode v1 SEPC查阅"D:\VScodeProject\MapCode\SPEC_v1_3.md"
- MapCode v1 功能流程说明查阅"D:\VScodeProject\MapCode\FuncFlow_v1_3.md"
- 项目各类文档中出现的专有术语查阅"D:\VScodeProject\MapCode\Specialized Terminology.md"
- aider项目简介查阅"D:\VScodeProject\MapCode\adier.md"
- MapCode项目中aider中被插入pico的功能模块部分查阅"D:\VScodeProject\MapCode\aider_module.md"
- pico项目简介查阅"D:\VScodeProject\MapCode\pico.md"
- pico架构和设计文档查阅D:\VScodeProject\MapCode\pico\release\v3\learning


## 长期项目文档治理规则

本项目使用两层文档系统维护长期开发过程，主要使用vibe-prac skill 与 planning-with-files skill 共同协作规范开发

- `vibe-prac`：项目级开发治理流程，负责需求、设计、任务拆分、主执行 Prompt、项目总进度跟踪、跨会话交接、设计回退。
- `planning-with-files`：会话级工作记忆与执行日志，负责单次任务的计划、调研发现、错误记录、测试结果、上下文恢复、局部任务进度、会话中断后恢复信息、任务实现常识。

二者不得混用职责。  
`vibe-prac` 产物是项目长期事实；`planning-with-files` 产物是某一次任务或会话的执行过程记录。

---

### 1. 总体原则

1. MapCode 产品发布版本只使用 `v1`、`v2` 这类 major release 名称；`SPEC_v1_2.md`、`SPEC_v1_3.md`、`PRD_v1_1.md` 等 `v<major>_<revision>` 名称只表示对应产品版本下的文档或设计修订版本，不表示新的产品发布版本。
2. 文档中提到的 SPEC、PRD、FuncFlow 等由于设计修订需要，在文件仓库中命名为 `SPEC_vx_x.md`、`PRD_vx_x.md`、`FuncFlow_vx_x.md` 等。如无明确说明，均默认调用当前活动产品版本对应的最新修订文档，**落后修订版本的文档不要再去读**。
3. FuncFlow 文档解释模块流程、数据走向、事件顺序和用户可见行为，是流程解释文档。
4. 项目级事实必须写入 `doc/`。
5. 简单问题、单文件小修改、快速查询可以不创建 `.planning/` 目录，其他符合 `planning-with-files` skill 描述的任务场景必须创建 `.planning/` 目录，禁止多个无关任务共用同一个 `.planning/` 目录。
6. 不允许只依赖聊天上下文传递需求、设计、任务状态、错误原因或测试结果。
7. 不允许在没有读取项目级文档的情况下直接实现代码。
8. 不允许把临时调研结论直接当成正式设计；调研结论必须经过确认后才能沉淀到 `doc/SPEC.md`。
9. 不允许为了通过测试而删除、跳过、注释掉失败逻辑；必须定位根因并记录处理过程。
10. 每次会话结束前必须更新相关文档，例如（`.planning/<task>/task_plan.md` -> 如任务拆分、依赖、验证命令变化，沉淀到 `doc/tasks/{product-version}/{module-name}.md`）确保下一个会话可以从文件恢复上下文。
11. 文档冲突时，采取 `SPEC > PRD > FuncFlow > doc/tasks/{product-version}/*.md > doc/tasks/{product-version}/progress.md > doc/tasks/progress_cross.md > .planning/<task>/task_plan.md > .planning/<task>/progress.md > .planning/<task>/findings.md` 的优先级。
12. 如果 `.planning/` 或实现代码引入了 `doc/PRD.md` 中没有的行为，视为未批准范围。写入 `.planning/<task>/findings.md`，不默认实现，需要时回到 `doc/PRD.md` 更新需求，需求确认后再实现。
13. 实现过程中发现 `doc/SPEC.md` 不合理，写入 `.planning/<task>/findings.md`，提出设计修正，更新 `doc/SPEC.md`，再继续实现，禁止在不更新 `doc/SPEC.md` 的情况下偷偷加功能或者实现另一套设计。
14. 每个文档的结构模版参考各自对应的 skill 内容要求来布局。
15. 禁止在没有说明的情况下随意新增多个文档目录，除非已经明确规定这些目录的用途。

---

### 2. 产品版本、任务 ID 与会话命名规范

1. 产品版本是任务的 release namespace。任务 ID 固定使用 `V<major>-F<stage>-<sequence>`，例如 `V1-F0-01`、`V2-F3-05`。
2. 所有任务 ID 必须使用完整版本前缀；任务标题、任务依赖、进度账本、Prompt、分支说明和跨会话引用中禁止省略产品版本前缀。
3. 文档修订版本变化不会改变任务 ID。`SPEC_v1_2.md` 更新为 `SPEC_v1_3.md` 后，属于产品 v1 的任务仍使用 `V1-F...`。
4. 每个产品版本的任务文件固定放在 `doc/tasks/<product-version>/`，例如 `doc/tasks/v1/`、`doc/tasks/v2/`。
5. `doc/tasks/<product-version>/progress.md` 是该产品版本唯一任务进度来源；模块任务文件只记录任务定义、依赖、边界和验证命令。
6. `doc/tasks/progress_cross.md` 只记录跨版本状态、当前活动产品版本和各版本进度账本入口，不记录具体任务明细。
7. 当前活动产品版本以 `doc/tasks/progress_cross.md` 为准。开始任务前必须先确定活动产品版本，再读取对应版本的任务进度与模块任务文件。
8. 新产品版本只有在进入正式规划时才创建对应任务目录和进度账本；不得提前复制上一版本任务作为占位。
9. 新任务会话目录固定使用 `.planning/{YYYY-MM-DD}-{task-id-lowercase}-{task-slug}/`，例如 `.planning/2026-08-01-v2-f0-01-v2-baseline/`。
10. 历史 `.planning` 会话目录作为执行记录保留原名，不因后续命名规则调整而批量重命名；目录内仍在引用的活动任务 ID 必须使用完整版本前缀。
11. 跨版本依赖必须显式使用完整任务 ID，例如 `V2-F0-01` 依赖 `V1-F9-09`，禁止依赖“上一版本最终任务”等模糊描述。

---

### 3. 目录结构规范

长期项目必须使用以下文档结构：

```markdown
project/
├── AGENT.md
├── doc/
│   ├── PRD.md						#项目需求
│   ├── SPEC.md						#项目技术设计
│   ├── prompt.md					#主agent启动prompt	
│   └── tasks/
│       ├── progress_cross.md          #跨版本状态和当前活动产品版本
│       ├── v1/
│       │   ├── {module-name}.md       #v1 模块任务说明
│       │   └── progress.md            #v1 唯一任务进度来源
│       └── v2/                        #进入 v2 正式规划时创建
│           ├── {module-name}.md       #v2 模块任务说明
│           └── progress.md            #v2 唯一任务进度来源
├── .planning/
│   └── {YYYY-MM-DD}-{task-id-lowercase}-{task-slug}/
│       ├── task_plan.md		     #当前会话任务执行计划
│       ├── findings.md			     #当前会话任务调研/代码阅读发现
│       └── progress.md               #当前会话任务会话日志、修改记录、测试结果和错误处理过程
└── src/
```

---

### 4.每次任务开始前准备

1. 读取 AGENT.md
2. 读取 doc/PRD.md
3. 读取 doc/SPEC.md
4. 读取 `doc/tasks/progress_cross.md`，确认当前活动产品版本
5. 读取 `doc/tasks/{product-version}/progress.md`
6. 读取对应 `doc/tasks/{product-version}/{module-name}.md`
7. 创建或继续 `.planning/{YYYY-MM-DD}-{task-id-lowercase}-{task-slug}/`
8. 编写或更新 task_plan.md，没有 task_plan.md 不能开始该会话任务的实现
9. 执行代码阅读、调研、实现、测试
10. 持续更新 findings.md 和 progress.md
11. 任务完成后更新 `doc/tasks/{product-version}/progress.md`
12. 产品版本状态或当前活动版本变化时更新 `doc/tasks/progress_cross.md`
13. 如有稳定设计变化，更新 doc/SPEC.md
14. 如有需求边界变化，更新 doc/PRD.md
15. 输出会话结束交付

---

### 5.会话结束状态记录

- 当前处于哪个阶段：
- 本次更新了哪些文档：
-  本次修改了哪些代码：
-  哪些完成标准已满足：
-  运行了哪些验证命令：
-  验证结果：
-  是否需要回退到前一阶段：
-  哪些 findings 需要沉淀到项目级文档：
- 下一次会话应该从哪个文件和哪个任务继续：

---

### 6. 文档更新规则

在一个会话中执行任务时按以下顺序更新文档：

```
读取项目级文档
    ↓
创建或读取 .planning/<task>/
    ↓
更新 task_plan.md
    ↓
执行代码阅读、调研、实现、测试
    ↓
持续更新 findings.md 和 progress.md
    ↓
任务完成后回写 doc/tasks/{product-version}/progress.md
    ↓
产品版本状态变化时回写 doc/tasks/progress_cross.md
    ↓
必要时回写 doc/SPEC.md、doc/PRD.md 或 doc/tasks/{product-version}/{module-name}.md
```

具体规则：

1. 项目目标、用户场景、功能边界变化：更新 `doc/PRD.md`。
2. 架构、模块职责、接口、数据流、错误处理、测试策略变化：更新 `doc/SPEC.md`。
3. 任务粒度、依赖关系、输入输出、验证命令变化：更新 `doc/tasks/{product-version}/{module-name}.md`。
4. 任务完成状态变化：更新 `doc/tasks/{product-version}/progress.md`。
5. 产品版本状态、当前活动版本或版本进度入口变化：更新 `doc/tasks/progress_cross.md`。
6. 当前会话计划变化：更新 `.planning/<task>/task_plan.md`。
7. 当前会话调研和代码阅读发现：更新 `.planning/<task>/findings.md`。
8. 当前会话执行日志、错误、测试结果：更新 `.planning/<task>/progress.md`。

### 7.冲突处理

#### 任务边界冲突

如果当前任务过大、过模糊或依赖缺失：

1. 停止扩展实现范围。
2. 写入 `.planning/<task>/progress.md`。
3. 更新 `doc/tasks/{product-version}/<module-name>.md`。
4. 必要时更新 `doc/tasks/{product-version}/progress.md`。
5. 拆小任务后再继续。

#### 进度冲突

如果 `.planning/<task>/progress.md` 说任务完成，但 `doc/tasks/{product-version}/progress.md` 没有打勾，则任务在对应产品版本中仍未完成。

处理方式：

1. 检查代码。
2. 检查测试。
3. 检查文档更新。
4. 确认无误后更新 `doc/tasks/{product-version}/progress.md`。

单个产品版本的任务完成状态只以 `doc/tasks/{product-version}/progress.md` 为准；跨版本状态与当前活动版本只以 `doc/tasks/progress_cross.md` 为准。

####  聊天记录冲突

如果聊天记录和文档冲突，以文档为准。

聊天记录不是长期项目记忆。

任何重要信息都必须写入：`doc`


## Git 与版本控制约束

本项目必须使用 Git 作为工程演进和变更审计的基础。Agent 在执行任何代码修改、文件移动、目录重构、依赖变更或批量格式化前，必须先确认当前仓库状态，并遵守以下规则。

### 1. 修改前必须检查仓库状态

在开始修改前，必须执行并阅读：

```bash
git status --short --branch
```

必要时继续查看：

```bash
git diff
git diff --staged
```

如果发现工作区已有未提交改动，必须先判断这些改动是否属于当前任务。不得覆盖、删除、格式化或混入用户已有改动。若当前任务需要修改同一文件，必须先说明冲突风险，并等待用户确认或改为只读分析。

### 2. 禁止无确认执行破坏性 Git 操作

除非用户明确要求，否则禁止执行以下命令或等价操作：

```bash
git reset --hard
git clean -fd
git clean -fdx
git checkout -- .
git restore .
git restore --staged .
git branch -D
git push --force
git push --force-with-lease
rm -rf .git
```

如果确实需要撤销本次 agent 产生的改动，应优先使用路径级别、可解释、可审查的方式，例如：

```bash
git restore <file>
git restore --staged <file>
```

执行前必须说明会影响哪些文件。

### 3. 分支策略

不得直接在长期主分支上进行高风险开发。涉及功能开发、架构调整、MapEngine 接入、批量重命名、依赖升级、测试框架调整时，应使用任务分支：

```bash
git switch -c <type>/<short-task-name>
```

由于我要在两个电脑上进行开发，因此在本电脑上所以的分支前面都加上win~，例如以下分支命名：

```text
winfeat/map-engine-bootstrap
winfeat/repo-map-context
winrefactor/prompt-builder-map-context
wintest/map-engine-ranking
windocs/update-agent-rules
```

小型文档修改或用户明确指定时，可以在当前分支完成，但仍必须先检查 `git status`。

### 4. Worktree 使用规则

当任务需要并行探索、对比两种实现方案、或进行高风险重构时，优先使用 `git worktree` 创建隔离工作区，而不是在同一工作区反复切换和覆盖改动：

```bash
git worktree add ../mapcode-<task-name> -b <type>/<short-task-name>
```

不同 worktree 之间不得直接复制未审查的大段代码。需要合并时，应通过 commit、diff、patch 或明确的文件级变更说明完成。


### 5. Commit 粒度

Commit 必须保持小而清晰。一个 commit 只表达一个主要意图，不要把无关变更混在一起。

推荐拆分方式：

```text
1. MapEngine 数据结构
2. repo map 生成逻辑
3. PromptBuilder 接入
4. Trace/Report 字段扩展
5. CLI 参数和文档更新
6. 测试用例补充
```

禁止把大规模重命名、格式化、功能开发、bugfix、依赖升级混在同一个 commit 中。

### 6. Commit Message 规范

提交信息使用 Conventional Commits 风格：

```text
<type>(<scope>): <description>
```

常用类型：

```text
feat: 新功能
fix: 修复问题
refactor: 不改变外部行为的重构
test: 新增或修改测试
docs: 文档修改
chore: 构建、依赖、脚本、配置等杂项
perf: 性能优化
style: 格式调整，不改变逻辑
```

示例：

```text
feat(map-engine): add repo map context provider
refactor(prompt): route map context through PromptBuilder
test(map-engine): cover ranked file selection
docs(agent): add git workflow constraints
```

如果 commit 影响行为，应在 body 中说明为什么改、改了什么、如何验证。


### 7. 不提交生成物和敏感信息

不得提交以下内容：

```text
.env
.env.*
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
dist/
build/
*.log
*.tmp
.DS_Store
node_modules/
模型密钥
API Token
本地绝对路径
用户私有配置
大体积临时输出
```

如果 MapCode 运行产生 trace、history、report、cache 等文件，必须根据项目设计判断：
需要复现实验或演示的最小样例可以进入 `examples/` 或 `docs/assets/`；普通本地运行产物必须加入 `.gitignore`。

### 8. 大规模重命名和格式化规则

大规模 rename、format、import sort、目录迁移必须单独 commit。不得与功能逻辑修改混在一起。

推荐顺序：

```text
commit 1: rename files/modules only
commit 2: update imports and references
commit 3: implement behavior changes
commit 4: update tests and docs
```

这样可以保证 diff 可读、回滚可控、blame 历史清晰。

### 9. 远程操作限制

除非用户明确要求，否则不得执行：

```bash
git push
git push --tags
git pull --rebase
git merge
git rebase
gh pr create
gh pr merge
```

如果需要同步远程分支，必须先说明当前分支、远程分支、预期影响和冲突风险。

### 10 任务结束时必须给出 Git 摘要

每次完成修改后，必须提供：

```text
当前分支
修改文件列表
核心 diff 摘要
已运行的测试/检查
未运行的测试及原因
建议的 commit message
是否存在未提交改动
```

如果已经创建 commit，还必须给出 commit hash 和 commit message。

### 11 MapCode 项目的特殊约束

MapCode 的工程演进以 Pico 现有 runtime 为唯一代码底座。所有 MapEngine / RepoMap 能力都必须作为 Pico 现有模块的增量增强接入。Git 历史应清晰体现：

```text
Pico baseline
→ MapEngine 数据结构
→ RepoMap 生成能力
→ PromptBuilder 上下文注入
→ Trace/Report 可解释记录
→ CLI / README / 配置产品化命名
```

禁止通过新建空壳项目并从 Pico/Aider 复制零散代码片段的方式完成需求。涉及 Aider 能力迁移时，应优先体现为 MapEngine 模块的可审查增量 commit。



## Pico行数门禁

- Pico 自定义的 Python 文件行数门禁属于架构预警机制，不是不可突破的硬性限制。
- 新功能接入时，必须先根据模块职责、控制流内聚性、复用边界和可读性判断代码应放置的位置，禁止仅为了满足现有行数门禁而强行拆分完整功能或制造无意义的 helper 模块。
- 当新增代码确实属于现有模块的核心职责，拆分后会破坏功能完整性、增加隐式依赖、分散控制流或降低可读性时，应优先合理提高对应文件的行数门禁。
- 提高行数门禁时，必须说明新增代码为什么属于该模块、为什么不适合继续拆分，并同步更新架构门禁测试。
- 行数门禁不能被完全忽略。若文件同时承担多个独立职责、出现可复用逻辑、测试困难或阅读成本明显上升，应按职责拆分模块，不能通过持续提高门禁掩盖模块臃肿。
- 总体优先级固定为：功能完整接入与职责正确 > 控制流内聚和可读性 > 可复用性 > 现有行数门禁。
