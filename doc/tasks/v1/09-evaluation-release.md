# 09 Retrieval Evaluation And Release Tasks

## 模块目标

建立 MapCode v1 retrieval/context-selection 评测，验证固定 token budget、selector catalog、请求预算门禁、降级证据和真实 provider 演示，并完成发布文档。

## 相关设计

- 当前迁移前来源：`PRD_v1_1.md` 评测方案、`SPEC_v1_3.md` 17.6、18、19。
- 迁移后来源：`doc/PRD.md`、`doc/SPEC.md`。

## 模块依赖

- 阶段 8 全部门禁通过。

## 模块通用边界

- **允许修改**：固定 eval fixture、retrieval metrics、evaluator 接入、README/配置/演示文档和对应测试。
- **禁止修改**：为了提高指标改变已确认的 ranking、selector、预算或安全契约。
- **模块原则**：指标只能读取结构化 evidence/trace/report；真实 provider 演示用于验收，不替代离线门禁。

## 任务列表

### V1-F9-01：建立固定 retrieval fixture 和 ground truth

- **优先级**：P0
- **依赖**：V1-F8-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、固定跨文件 def/ref 场景
- **输出**：固定 Git Python fixture、请求与 ground_truth_files
- **允许修改路径**：`pico/tests/fixtures/map_engine_eval/`、retrieval eval tests/data
- **禁止修改边界**：不得让 ground truth 依赖模型主观判断
- **步骤**：建立可人工核对的 specific/fuzzy/symbol-only/catalog/over-budget/failure cases；增加“分析 `pico/` 文件夹内容”目录类 fuzzy、source/test 偏好和隐藏 candidate 拒绝场景。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_retrieval_eval.py -q
  ```
- **完成标准**：fixture 小、稳定，覆盖 `SPEC_v1_3.md` 定义的关键数据流。
- **回退条件**：ground truth 含糊、fixture 不可重复或依赖真实模型。

### V1-F9-02：实现 rendered-file、first-read 与 map budget 指标

- **优先级**：P0
- **依赖**：V1-F9-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、结构化 map evidence/trace
- **输出**：rendered-file hit、first-read hit、broad/focused tokens 和 chars 指标与 tests
- **允许修改路径**：retrieval metrics 模块与 tests
- **禁止修改边界**：不得从终端文本解析机器指标
- **步骤**：从 evidence/trace 读取 rendered files、首个 read_file、RenderingEvidence target/estimated tokens 和 used chars。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_retrieval_eval.py -q
  ```
- **完成标准**：指标来源明确、缺失数据有稳定结果，能区分 broad/focused 固定预算。
- **回退条件**：只记录字符数、从文本猜测 budget 或指标语义不稳定。

### V1-F9-03：实现完整 selector request 与 catalog truncation 指标

- **优先级**：P0
- **依赖**：V1-F9-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、selector/catalog evidence 与 trace
- **输出**：完整 selector request tokens、visible/candidate/rendered file/definition counts、catalog truncation 指标与 tests
- **允许修改路径**：retrieval metrics 模块与 tests
- **禁止修改边界**：不得复制完整 selector request/catalog 文本到评测结果
- **步骤**：读取 selector requested 摘要与 catalog evidence；统计完整 `system_prompt + user_prompt` token estimate、visible/candidate/rendered paths 和 truncated 次数。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_retrieval_eval.py -q
  ```
- **完成标准**：可评估模型实际可见路径、snapshot candidate 来源、catalog truncation 和完整 selector request 输入预算。
- **回退条件**：把 candidate_paths 数量误当作模型可见路径数量。

### V1-F9-04：实现 fallback、reduction、omission 与超预算指标

- **优先级**：P0
- **依赖**：V1-F9-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、selection/prompt/request budget evidence
- **输出**：focus truncation、selector calls、selector_request_over_budget、fallback、`base_prompt_reduction_applied`、repo map omission、request_over_budget 指标
- **允许修改路径**：retrieval metrics 模块与 tests
- **禁止修改边界**：不得把正常 broad fallback 计为 MapEngine failure
- **步骤**：从 evidence/report/trace 读取结构化事实；覆盖零样本、混合样本和本地预请求失败。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_retrieval_eval.py -q
  ```
- **完成标准**：`SPEC_v1_3.md` 定义的最小 retrieval 与请求预算指标全部可输出。
- **回退条件**：指标语义无法对应稳定事实源。

### V1-F9-05：接入 Pico evaluator

- **优先级**：P0
- **依赖**：V1-F9-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、完整 retrieval metrics
- **输出**：MapEngine retrieval eval 入口和结构化结果
- **允许修改路径**：Pico evaluator/metrics 最小接缝、retrieval eval tests
- **禁止修改边界**：不得改变现有 evaluator 默认行为
- **步骤**：增加独立 retrieval eval 入口；输出复现信息、固定 budget、catalog 和 ModelRequestBudget 指标。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_retrieval_eval.py pico\tests\test_metrics.py -q
  ```
- **完成标准**：固定 fixture 可一条命令输出结构化指标。
- **回退条件**：MapEngine eval 与现有 evaluator 紧耦合导致回归。

### V1-F9-06：运行完整离线回归和架构边界检查

- **优先级**：P0
- **依赖**：V1-F9-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、全部实现与测试
- **输出**：完整测试、Ruff、门禁与行数审查记录
- **允许修改路径**：仅当前任务计划/进度/发现记录；发现问题时回退对应实现任务
- **禁止修改边界**：不得为通过门禁删除断言、跳过测试或制造无意义模块
- **步骤**：运行完整 suite；检查 feature-off、固定 budget、请求硬门禁、catalog、证据链和所有提高过的行数门禁。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：完整离线门禁通过，无未解释回归或门禁调整。
- **回退条件**：任何失败未定位根因，或存在为门禁制造的无意义模块。

### V1-F9-07：使用真实 provider 演示 Branch A

- **优先级**：P0
- **依赖**：V1-F9-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、固定 Git Python fixture、真实 provider 配置
- **输出**：真实 specific 请求演示记录与 artifacts
- **允许修改路径**：运行 artifacts、当前任务记录、必要用户文档
- **禁止修改边界**：不得记录密钥或用真实模型结果替代离线断言
- **步骤**：启用 MapEngine；发出明确文件/符号请求；核验精确 DefinitionRecord 前缀、4,096-token focused map、首个 read_file、prompt、artifacts、trace/report 和最终请求门禁。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pico --cwd .\pico\tests\fixtures\map_engine_eval --map-engine "fix token validation in JWTAuth"
  ```
- **完成标准**：真实模型完成 Branch A，证据链可复盘，敏感信息未落盘。
- **回退条件**：模型/网络问题无法区分于代码问题，或证据链不完整。

### V1-F9-08：使用真实 provider 演示 Branch B 和预算降级

- **优先级**：P0
- **依赖**：V1-F9-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、固定 fixture、真实 provider 配置
- **输出**：真实 fuzzy 交互、catalog、broad fallback、selector/request over-budget 与增强层失败演示记录
- **允许修改路径**：运行 artifacts、当前任务记录、必要用户文档
- **禁止修改边界**：不得记录密钥或跳过失败路径证据检查
- **步骤**：使用“分析 `pico/` 文件夹内容”等目录类请求演示 confirmed focused、目录软偏好、source/test 偏好、catalog 已展示但 broad map 外文件建议、隐藏 candidate 拒绝、one-shot fallback、selector_request_over_budget、repo map omission、最终请求超预算和受控 MapEngine failure；核验真实 provider payload 中 system/user 角色确实分离，且 selector 只执行文件检索。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pico --cwd .\pico\tests\fixtures\map_engine_eval --map-engine --repl
  ```
- **完成标准**：真实 Branch B、双角色 selector、catalog、预算门禁与失败降级符合离线 acceptance。
- **回退条件**：真实链路暴露 SPEC/实现不一致，必须回退对应设计或任务。

### V1-F9-09：更新 README、配置、演示步骤和项目总进度

- **优先级**：P0
- **依赖**：V1-F9-08
- **输入**：当前最新 SPEC/PRD/FuncFlow、离线/真实验收记录
- **输出**：最终用户文档、预算配置、演示说明、全部完成进度
- **允许修改路径**：README、配置示例、doc/、项目总进度
- **禁止修改边界**：不得声明未经验证的模型窗口或隐藏失败/限制
- **步骤**：记录启用方式、ModelRequestBudget CLI/TOML、固定 map budget、catalog、artifact、eval、失败降级和后续方向；完成最终门禁并更新总账。
- **验证命令**：
  ```powershell
  Select-String -Path .\pico\README.md,.\doc\*.md -Pattern "ModelRequestBudget|32768|1024|4096|8192|SelectorCandidateCatalog|selector_request_over_budget"
  ```
- **完成标准**：所有项目任务完成、最终门禁通过、MapCode v1 可按文档复现与演示。
- **回退条件**：文档与真实行为不一致，或总进度存在未完成任务。
