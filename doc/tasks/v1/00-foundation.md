# 00 Foundation Tasks

## 模块目标

在任何 MapEngine 代码实现前，建立可审计的 Git 基线、长期文档目录、项目虚拟环境、依赖兼容性结论和阶段三任务治理文件。

## 当前输入文档

- `AGENT.md`
- `PRD_v1_1.md`
- `SPEC_v1_3.md`
- `FuncFlow_v1_3.md`
- `pico/pyproject.toml`

## 模块依赖

- 无。

## 模块通用边界

- **允许修改**：根目录治理文件、`doc/`、`.planning/`、`pico/pyproject.toml`、`pico/README.md`、许可证说明文件、独立实验文件。
- **禁止修改**：`aider/`、`pico_origin/`、MapEngine 与 Pico runtime 功能源码。
- **模块门禁**：根目录 Git 可审计；baseline 测试通过；依赖实验通过；正式文档引用一致。

## 任务列表

### V1-F0-01：校准根目录 Git baseline 与 `.gitignore`

- **优先级**：P0
- **依赖**：无
- **输入**：`AGENT.md` 中 Git 规则、当前已初始化 Git、当前 tracked/ignored 文件清单
- **输出**：符合项目治理规则的根 `.gitignore`、Git index 与可审查 baseline
- **允许修改路径**：`.gitignore`、Git index；不得删除工作区中的参考基线文件
- **禁止修改边界**：不得改动任何现有源码和文档内容；不得执行 push
- **步骤**：
  1. 审计当前 tracked/ignored 文件，确认 `aider/`、`pico_origin/` 已被错误追踪，`doc/`、`.planning/` 已被错误忽略。
  2. 校准根 `.gitignore`：排除 `.venv/`、`.pico/`、缓存、敏感文件、`aider/`、`pico_origin/`，允许项目事实文档、施工计划和 `pico/` 实现进入审计。
  3. 仅从 Git index 取消追踪 `aider/`、`pico_origin/`，不得删除本地工作区参考基线。
  4. 输出校准后的 baseline 文件清单供用户审查。
- **验证命令**：
  ```powershell
  git status --short --branch
  git check-ignore -v aider pico_origin .venv .pico
  git ls-files aider pico_origin doc .planning
  ```
- **完成标准**：Git 已初始化；`aider/`、`pico_origin/` 不再被追踪；`doc/`、`.planning/` 和项目事实可进入 Git 审计；用户审查通过后创建 baseline 校准 commit。
- **回退条件**：参考基线或敏感/运行产物进入追踪范围。

### V1-F0-02：统一规则入口、文档导航和事实优先级

- **优先级**：P0
- **依赖**：V1-F0-01
- **输入**：`AGENT.md`、已确认的 `SPEC > PRD > FuncFlow` 规则
- **输出**：项目唯一规则入口与准确导航
- **允许修改路径**：`AGENT.md`，必要时重命名为 `AGENTS.md`
- **禁止修改边界**：不得改变 MapCode v1 功能范围
- **步骤**：
  1. 统一规则文件名和所有内部引用。
  2. 删除与 `SPEC > PRD > FuncFlow` 冲突的规则。
  3. 保留并核验 Pico 行数门禁原则。
- **验证命令**：
  ```powershell
  Select-String -Path .\AGENT*.md -Pattern "SPEC > PRD > FuncFlow|pico行数门禁|功能完整接入与职责正确"
  ```
- **完成标准**：项目只有一套事实优先级和一个规则入口。
- **回退条件**：规则修改引入新的冲突或改变需求边界。

### V1-F0-03：迁移正式文档至 `doc/` 并归档旧版本

- **优先级**：P0
- **依赖**：V1-F0-02
- **输入**：根目录最新与旧版 PRD/SPEC/FuncFlow
- **输出**：`doc/PRD.md`、`doc/SPEC.md`、`doc/FuncFlow.md`、`doc/archive/`
- **允许修改路径**：`doc/`、规则文件、文档内部链接
- **禁止修改边界**：不得在迁移时重写已确认的需求和设计语义
- **步骤**：
  1. 将最新版本迁移为长期事实文件。
  2. 将旧版本移入 `doc/archive/`。
  3. 更新规则文件和任务文件中的文档引用。
  4. 对迁移前后最新文档执行内容一致性检查。
- **验证命令**：
  ```powershell
  Get-ChildItem -Recurse .\doc
  Select-String -Path .\AGENT*.md,.\doc\tasks\*.md -Pattern "PRD_v1_1.md|SPEC_v1_3.md|FuncFlow_v1_3.md"
  ```
- **完成标准**：长期事实只从 `doc/PRD.md`、`doc/SPEC.md`、`doc/FuncFlow.md` 读取，旧版明确归档。
- **回退条件**：迁移造成内容丢失、链接失效或出现两套正式事实源。

### V1-F0-04：记录 Pico/Aider 基线来源、只读用途和许可证边界

- **优先级**：P0
- **依赖**：V1-F0-03
- **输入**：`aider/LICENSE.txt`、Aider RepoMap/query 来源、Pico 基线目录
- **输出**：`doc/baselines.md` 与许可证归属说明
- **允许修改路径**：`doc/baselines.md`、必要的许可证说明文件
- **禁止修改边界**：不得修改或追踪 `aider/`、`pico_origin/`
- **步骤**：
  1. 记录两个只读基线的用途和获取来源。
  2. 记录允许迁移的 Aider query/算法范围和 Apache 2.0 归属要求。
  3. 明确禁止 `import aider.*` 和整体复制 `RepoMap`。
- **验证命令**：
  ```powershell
  Select-String -Path .\doc\baselines.md -Pattern "aider|pico_origin|Apache|import aider"
  git status --short
  ```
- **完成标准**：新会话无需依赖聊天即可理解参考基线和许可证边界。
- **回退条件**：来源、许可证或只读规则不明确。

### V1-F0-05：校准项目级任务文件、进度账本和执行 Prompt

- **优先级**：P0
- **依赖**：V1-F0-03
- **输入**：`doc/tasks/`、`.planning/2026-06-10-mapcode-v1-construction-plan/`
- **输出**：迁移后引用准确的任务文件、`doc/tasks/v1/progress.md`、`doc/prompt.md`
- **允许修改路径**：`doc/tasks/`、`doc/prompt.md`、当前施工计划目录
- **禁止修改边界**：不得提前勾选未完成实现任务
- **步骤**：
  1. 将任务输入引用切换到 `doc/PRD.md`、`doc/SPEC.md`、`doc/FuncFlow.md`。
  2. 检查任务 ID、依赖与总进度账本一致。
  3. 检查执行 Prompt 能直接启动 V1-F0-06。
- **验证命令**：
  ```powershell
  Select-String -Path .\doc\tasks\*.md,.\doc\prompt.md -Pattern "PRD_v1_1.md|SPEC_v1_3.md|FuncFlow_v1_3.md"
  ```
- **完成标准**：旧根目录正式文档名不再被活动任务引用。
- **回退条件**：任务依赖或进度总账出现不一致。

### V1-F0-06：创建根目录 `.venv` 并验证 Pico baseline

- **优先级**：P0
- **依赖**：V1-F0-01
- **输入**：`pico/pyproject.toml`、当前 Pico tests
- **输出**：根目录 `.venv`、baseline 测试与 Ruff 记录
- **允许修改路径**：仅 `.venv/` 运行环境和当前任务日志
- **禁止修改边界**：不得为通过 baseline 修改 Pico 源码或测试
- **步骤**：
  1. 使用系统 Python 创建根目录 `.venv`。
  2. 以 editable/dev 方式安装当前 Pico。
  3. 运行完整 baseline 测试与 Ruff。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：记录 baseline 通过结果；若已有失败，形成明确基线清单并经用户决定。
- **回退条件**：环境不可复现或 baseline 状态不清楚。

### V1-F0-07：完成 MapEngine 依赖兼容性实验

- **优先级**：P0
- **依赖**：V1-F0-06
- **输入**：Aider Python query、`grep-ast.TreeContext`、tree-sitter、`networkx`
- **输出**：`experiment_map_engine_dependencies.py` 与实验结论
- **允许修改路径**：根目录实验文件、当前 `.planning` 日志
- **禁止修改边界**：不得将实验代码接入 Pico；不得修改 Aider
- **步骤**：
  1. 对最小 Python fixture 提取 definition/reference。
  2. 使用 TreeContext 渲染结构摘要。
  3. 构建最小文件图并运行 PageRank/PPR。
  4. 记录版本、API 差异和许可证要求。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe .\experiment_map_engine_dependencies.py
  ```
- **完成标准**：三项能力均可运行，失败时能给出确定的替代方案和 SPEC 修正建议。
- **回退条件**：依赖不可兼容，或实验结果要求改变技术设计。

### V1-F0-08：增加正式运行依赖和许可证说明

- **优先级**：P0
- **依赖**：V1-F0-07
- **输入**：依赖实验结论
- **输出**：更新后的 `pico/pyproject.toml` 与许可证归属说明
- **允许修改路径**：`pico/pyproject.toml`、许可证说明、配置/安装文档
- **禁止修改边界**：不得加入未经实验验证的依赖
- **步骤**：
  1. 添加 v1 所需最小运行依赖。
  2. 记录 query 或移植代码的来源和修改说明。
  3. 重新安装并运行 baseline。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pip install -e ".\pico[dev]"
  .\.venv\Scripts\python.exe -m pytest pico\tests -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：全新环境可安装，baseline 保持通过，许可证说明完整。
- **回退条件**：依赖破坏安装、baseline 或许可证边界。
