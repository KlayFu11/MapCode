# 08 Evidence And Observability Tasks

## 模块目标

完成 MapCode v1 的 trace、repo-map artifact、map evidence artifact、report、CLI/TUI 展示，以及 selector catalog、请求预算、base prompt reduction、omission 和超预算降级证据一致性。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 第十三、十四、十六、十七章。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 7 全部门禁通过。

## 模块通用边界

- **允许修改**：runtime trace payload、MapContext evidence 组装、report、reporter 消费接缝、CLI/REPL/TUI 与对应测试。
- **禁止修改**：MapEngine 算法、Branch 选择规则、ContextManager 新注入行为。
- **模块原则**：`map-evidence-001.json` 是完整检索与控制事实源；trace/report 是摘要；terminal 是已有 evidence 的投影。

## 任务列表

### V1-F8-01：写入完整 retrieval 与预算 trace

- **优先级**：P0
- **依赖**：V1-F7-07
- **输入**：当前最新 SPEC/PRD/FuncFlow、阶段 7 事件与预算事实
- **输出**：index/analyzed/ranked/selected/selector/confirmed/generated/failed 与预算摘要事件 tests
- **允许修改路径**：`map_context.py`、`runtime_events.py`、runtime evidence tests
- **禁止修改边界**：不得新增旁路 writer、复制完整 map/catalog 或把正常 fallback 记为 failed
- **步骤**：经 `runtime.emit_trace()` 写 run-level 摘要；selector requested 记录 snapshot/candidate/rendered/visible/input chars/call，其中 selector input chars 表示完整 `system_prompt + user_prompt` 双角色请求；prompt_built 明确记录 render、reservation、`base_prompt_reduction_applied`、omission、request_over_budget。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_evidence_acceptance.py pico\tests\test_runtime_evidence_acceptance.py -q
  ```
- **完成标准**：trace 可按时间顺序复盘检索、selector catalog、控制决策和最终请求门禁。
- **回退条件**：trace 复制完整 map/evidence/catalog 或旁路脱敏。

### V1-F8-02：保证 repo-map artifact 与首次实际注入一致

- **优先级**：P0
- **依赖**：V1-F8-01
- **输入**：当前最新 SPEC/PRD/FuncFlow、首次 main_model build-local render
- **输出**：`repo-map-001.txt` 与一致性 tests
- **允许修改路径**：`map_context.py`、RunStore 最小适配、evidence tests
- **禁止修改边界**：不得保存 MapEngine candidate body 代替实际注入 section
- **步骤**：将首次主模型实际使用的完整 repo_map section 或空注入结果固定写入 `repo-map-001.txt`；不重复写后续 build。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：artifact 文本逐字等于首次主模型实际使用的 repo_map section；整段省略时为空文本。
- **回退条件**：后续 prompt build 覆盖、重复写 artifact，或保存二次裁剪文本。

### V1-F8-03：写入结构化 map evidence artifact

- **优先级**：P0
- **依赖**：V1-F8-02
- **输入**：当前最新 SPEC/PRD/FuncFlow、MapContextResult、selection、PromptInjectionEvidence
- **输出**：完整 MapEvidenceArtifact JSON 与 schema tests
- **允许修改路径**：`map_context.py`、evidence tests
- **禁止修改边界**：不得保存完整 repo map/catalog 文本或 evidence artifact 自身路径
- **步骤**：组装 run envelope、broad/active result、selection、catalog 摘要、prompt injection、budget metadata 和 repo-map path。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：JSON 可回答为什么选择文件、catalog/selector 如何工作、使用什么预算，以及 `base_prompt_reduction_applied`、omission、over-budget 的结构化事实。
- **回退条件**：evidence 从最终字符串反推或包含循环路径引用。

### V1-F8-04：report 增加 MapContext、预算与模型调用摘要

- **优先级**：P0
- **依赖**：V1-F8-03
- **输入**：当前最新 SPEC/PRD/FuncFlow、TaskState 与 final evidence
- **输出**：report map_context/model_calls/request_budget 摘要与 tests
- **允许修改路径**：`runtime.py` report 构建职责位置、TaskState 摘要、相关 tests
- **禁止修改边界**：不得复制完整 evidence、catalog 或 repo map
- **步骤**：加入 enabled/id/branch/stage/focus/rendered/snapshot/calls/artifact paths，以及 budget source、reduction、omission、request_over_budget 摘要。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_evidence_acceptance.py pico\tests\test_runtime_evidence_acceptance.py -q
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_architecture_boundaries.py -q
  ```
- **完成标准**：report 是轻量最终汇总；total_model_calls 与 TaskState 完整字段一致。
- **回退条件**：report 膨胀为完整 evidence 副本，或使用 last_prompt_metadata 替代事实源。

### V1-F8-05：CLI/REPL 展示 reporter 事件

- **优先级**：P1
- **依赖**：V1-F8-04
- **输入**：当前最新 SPEC/PRD/FuncFlow、reporter/runtime 用户事件
- **输出**：CLI one-shot/REPL 用户可见 index/broad/focused/fallback/failure/budget 摘要
- **允许修改路径**：CLI/REPL 消费接缝、reporter 与 tests
- **禁止修改边界**：不得在 CLI/REPL 运行检索、预算门禁或产生新事实
- **步骤**：按调用前时机展示 reporter payload；无 artifact 时不显示路径；保持 one-shot/REPL 行为一致。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_pico.py pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：CLI/REPL 只展示 evidence 已有事实，时机符合 SPEC。
- **回退条件**：展示逻辑进入 MapEngine/ContextManager，或 UI 产生不可证明事实。

### V1-F8-06：TUI 展示 reporter 事件

- **优先级**：P1
- **依赖**：V1-F8-05
- **输入**：当前最新 SPEC/PRD/FuncFlow、与 CLI/REPL 相同的 runtime 事件
- **输出**：TUI retrieval 与 budget 状态展示
- **允许修改路径**：TUI 消费接缝与 tests
- **禁止修改边界**：不得建立独立检索或预算状态
- **步骤**：消费相同 reporter/runtime 事件；验证 broad 在 selector 前、final 在主模型前显示。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_tui.py pico\tests\test_map_context_evidence_acceptance.py -q
  ```
- **完成标准**：TUI 与 CLI/REPL 使用同一事件事实，展示时机一致。
- **回退条件**：TUI 建立独立检索状态或展示无法由 evidence 证明的信息。

### V1-F8-07：增加证据一致性、redaction 和降级测试

- **优先级**：P0
- **依赖**：V1-F8-06
- **输入**：当前最新 SPEC/PRD/FuncFlow、阶段 8 全部证据面
- **输出**：完整证据链 acceptance suite
- **允许修改路径**：evidence/runtime/report/CLI/TUI acceptance tests
- **禁止修改边界**：不得通过放宽断言隐藏证据不一致
- **步骤**：覆盖 Branch A/B、catalog、完整 selector request 摘要、`visible_paths`、隐藏 candidate 拒绝、selector_request_over_budget、base prompt reduction、repo map omission、最终请求超预算、artifact failure、redaction 和各层一致性；验证 evidence 不把 `candidate_paths` 混同为允许返回的可见路径。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_context_evidence_acceptance.py pico\tests\test_runtime_evidence_acceptance.py pico\tests\test_tui.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico pico\tests
  ```
- **完成标准**：阶段 8 门禁通过；完整双角色 selector request 摘要与可见路径校验事实一致；完整证据链可离线复盘。
- **回退条件**：任何层产生其他层无法证明的新事实。
