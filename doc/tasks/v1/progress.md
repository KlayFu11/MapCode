# MapCode v1 总体进度

> 本文件是 MapCode 产品 v1 的唯一任务进度来源；当前任务设计依据为 `SPEC_v1_3.md`、`PRD_v1_1.md`、`FuncFlow_v1_3.md`。
> 只有任务实现完成、验证命令通过、用户审查通过并完成对应 commit 后，才能勾选。

## 当前阶段

- `vibe-prac` 阶段三：已依据 `SPEC_v1_3.md`、`PRD_v1_1.md`、`FuncFlow_v1_3.md` 完成任务重新对齐，等待进入阶段四实现。
- 事实优先级：`SPEC > PRD > FuncFlow`。
- 首个可执行任务：`V1-F0-01 校准根目录 Git baseline 与 .gitignore`

## 阶段 0：固定施工地基

- [ ] V1-F0-01 校准根目录 Git baseline 与 `.gitignore` (P0, 无依赖)
- [ ] V1-F0-02 统一规则入口、文档导航和事实优先级 (P0, 依赖 V1-F0-01)
- [ ] V1-F0-03 迁移正式文档至 `doc/` 并归档旧版本 (P0, 依赖 V1-F0-02)
- [ ] V1-F0-04 记录 Pico/Aider 基线来源、只读用途和许可证边界 (P0, 依赖 V1-F0-03)
- [ ] V1-F0-05 校准项目级任务文件、进度账本和执行 Prompt (P0, 依赖 V1-F0-03)
- [ ] V1-F0-06 创建根目录 `.venv` 并验证 Pico baseline (P0, 依赖 V1-F0-01)
- [ ] V1-F0-07 完成 MapEngine 依赖兼容性实验 (P0, 依赖 V1-F0-06)
- [ ] V1-F0-08 增加正式运行依赖和许可证说明 (P0, 依赖 V1-F0-07)

## 阶段 1：模块边界与数据契约

- [ ] V1-F1-01 创建 MapEngine 配置和版本常量 (P0, 依赖 V1-F0-08)
- [ ] V1-F1-02 定义索引基础 DTO (P0, 依赖 V1-F1-01)
- [ ] V1-F1-03 定义 ranking、rendering 与 cache evidence DTO (P0, 依赖 V1-F1-02)
- [ ] V1-F1-04 定义 PromptAnalysis、MapContextEvidence 与 MapResult (P0, 依赖 V1-F1-03)
- [ ] V1-F1-05 定义 SelectorCandidateCatalog DTO (P0, 依赖 V1-F1-04)
- [ ] V1-F1-06 定义 SelectorModelRequest 与 selector 决策 DTO (P0, 依赖 V1-F1-05)
- [ ] V1-F1-07 定义 MapContext 与 artifact DTO (P0, 依赖 V1-F1-06)
- [ ] V1-F1-08 定义 runtime-owned ModelRequestBudget (P0, 依赖 V1-F1-07)
- [ ] V1-F1-09 定义 prompt render 与 build result DTO (P0, 依赖 V1-F1-08)
- [ ] V1-F1-10 增加 MapEngine 与预算架构边界测试 (P0, 依赖 V1-F1-09)

## 阶段 2：Git Python 索引与缓存

- [ ] V1-F2-01 实现 Git tracked/staged 文件枚举 (P0, 依赖 V1-F1-10)
- [ ] V1-F2-02 实现 Python-only、denylist 和非 Git 降级 (P0, 依赖 V1-F2-01)
- [ ] V1-F2-03 使用 tree-sitter query 提取 definitions (P0, 依赖 V1-F2-02)
- [ ] V1-F2-04 提取 references 并隔离单文件失败 (P0, 依赖 V1-F2-03)
- [ ] V1-F2-05 构建 SymbolIndex 和稳定 snapshot id (P0, 依赖 V1-F2-04)
- [ ] V1-F2-06 实现 index/cache 读取与 cache hit (P0, 依赖 V1-F2-05)
- [ ] V1-F2-07 实现版本失效、文件变化与 cache 失败 evidence (P0, 依赖 V1-F2-06)

## 阶段 3：确定性 MapEngine

- [ ] V1-F3-01 实现 PromptAnalyzer identifier 与 Branch 判断 (P0, 依赖 V1-F2-07)
- [ ] V1-F3-02 实现文件路径唯一匹配与歧义过滤 (P0, 依赖 V1-F3-01)
- [ ] V1-F3-03 构建文件级 def/ref 图和稳定 fallback (P0, 依赖 V1-F3-02)
- [ ] V1-F3-04 实现 broad PageRank 和 ranking evidence (P0, 依赖 V1-F3-03)
- [ ] V1-F3-05 实现 focused PPR、boost 和 contributors (P0, 依赖 V1-F3-04)
- [ ] V1-F3-06 固定 effective_symbol_hits DefinitionRecord 候选前缀 (P0, 依赖 V1-F3-05)
- [ ] V1-F3-07 使用 TreeContext 渲染结构摘要 (P0, 依赖 V1-F3-06)
- [ ] V1-F3-08 实现固定 focused/broad token budget 与 truncation (P0, 依赖 V1-F3-07)
- [ ] V1-F3-09 从同一 snapshot 生成 SelectorCandidateCatalog (P0, 依赖 V1-F3-08)
- [ ] V1-F3-10 实现 MapEngine 公共接口和 lazy index (P0, 依赖 V1-F3-09)
- [ ] V1-F3-11 增加离线 MapEngine fixture 演示 (P0, 依赖 V1-F3-10)

## 阶段 4：Pico Runtime 基础接入

- [ ] V1-F4-01 增加 `.pico.toml [features]` 和 `--map-engine` (P0, 依赖 V1-F3-11)
- [ ] V1-F4-02 解析 ModelRequestBudget 配置契约 (P0, 依赖 V1-F4-01)
- [ ] V1-F4-03 Runtime 装配 MapEngine、预算对象和 current map (P0, 依赖 V1-F4-02)
- [ ] V1-F4-04 child runtime 关闭 MapEngine 并保留预算 (P0, 依赖 V1-F4-03)
- [ ] V1-F4-05 RunStore 增加原子 JSON artifact (P0, 依赖 V1-F4-03)
- [ ] V1-F4-06 TaskState 增加 MapContext 与模型调用摘要 (P0, 依赖 V1-F4-03)
- [ ] V1-F4-07 注册 retrieval trace phase 与事件 (P0, 依赖 V1-F4-03)
- [ ] V1-F4-08 实现 Coordinator 数据适配与 selector catalog 接口 (P0, 依赖 V1-F4-05/V1-F4-06/V1-F4-07)
- [ ] V1-F4-09 实现 MapEngineConsoleReporter (P0, 依赖 V1-F4-08)
- [ ] V1-F4-10 扩展 provider 双角色 selector 请求适配 (P0, 依赖 V1-F4-04)

## 阶段 5：PromptPurpose 与 Repo Map 注入

- [ ] V1-F5-01 引入 PromptPurpose 和 PromptBuildResult (P0, 依赖 V1-F4-09/V1-F4-10)
- [ ] V1-F5-02 迁移 Runtime wrapper 与 main model 调用点 (P0, 依赖 V1-F5-01)
- [ ] V1-F5-03 迁移 prompt preview 调用点 (P0, 依赖 V1-F5-02)
- [ ] V1-F5-04 迁移 evaluation 与 step-limit summary 调用点 (P0, 依赖 V1-F5-03)
- [ ] V1-F5-05 实现统一主模型导航模板与 fallback notice (P0, 依赖 V1-F5-04)
- [ ] V1-F5-06 ContextManager 组装独立 repo_map section (P0, 依赖 V1-F5-05)
- [ ] V1-F5-07 为完整 repo map 预留输入空间并缩减 base prompt (P0, 依赖 V1-F5-06)
- [ ] V1-F5-08 实现 repo map 原子注入或整段省略 (P0, 依赖 V1-F5-07)
- [ ] V1-F5-09 验证 feature disabled、无 MapContext 与四种 purpose (P0, 依赖 V1-F5-08)

## 阶段 6：Branch A 与最终模型门禁

- [ ] V1-F6-01 Engine 在首次主模型 build 前执行 Branch A preparation (P0, 依赖 V1-F5-09)
- [ ] V1-F6-02 首次 main model build 后持久化 artifacts (P0, 依赖 V1-F6-01)
- [ ] V1-F6-03 prepared MapContext 替换为 finalized 对象 (P0, 依赖 V1-F6-02)
- [ ] V1-F6-04 retry/tool loop 复用同一 MapContext (P0, 依赖 V1-F6-03)
- [ ] V1-F6-05 preparation 或 artifact 失败时重建无 map prompt (P0, 依赖 V1-F6-03)
- [ ] V1-F6-06 repo map 无法共存时重建无 map prompt (P0, 依赖 V1-F6-05)
- [ ] V1-F6-07 执行最终请求硬门禁与模型调用计数 (P0, 依赖 V1-F6-06)
- [ ] V1-F6-08 所有退出路径统一清理 current map (P0, 依赖 V1-F6-04/V1-F6-05/V1-F6-06/V1-F6-07)
- [ ] V1-F6-09 增加 Branch A scripted acceptance test (P0, 依赖 V1-F6-08)

## 阶段 7：Branch B Selector 与确认流

- [ ] V1-F7-01 实现 selector request builder、parser 和 visible path 校验 (P0, 依赖 V1-F6-09)
- [ ] V1-F7-02 Engine 获取同 snapshot catalog 并执行 selector 请求预算门禁 (P0, 依赖 V1-F7-01)
- [ ] V1-F7-03 Engine 复用双角色 provider adapter 调用 selector (P0, 依赖 V1-F7-02)
- [ ] V1-F7-04 实现整组二选一确认协议 (P0, 依赖 V1-F7-03)
- [ ] V1-F7-05 实现 one-shot、超预算、取消和无效输出 fallback (P0, 依赖 V1-F7-04)
- [ ] V1-F7-06 confirmed focus 生成 focused map 并复用 snapshot (P0, 依赖 V1-F7-05)
- [ ] V1-F7-07 验证事件、展示、预算与模型调用顺序 (P0, 依赖 V1-F7-06)

## 阶段 8：完整证据链与可观测性

- [ ] V1-F8-01 写入完整 retrieval 与预算 trace (P0, 依赖 V1-F7-07)
- [ ] V1-F8-02 保证 repo-map artifact 与首次实际注入一致 (P0, 依赖 V1-F8-01)
- [ ] V1-F8-03 写入结构化 map evidence artifact (P0, 依赖 V1-F8-02)
- [ ] V1-F8-04 report 增加 MapContext、预算与模型调用摘要 (P0, 依赖 V1-F8-03)
- [ ] V1-F8-05 CLI/REPL 展示 reporter 事件 (P1, 依赖 V1-F8-04)
- [ ] V1-F8-06 TUI 展示 reporter 事件 (P1, 依赖 V1-F8-05)
- [ ] V1-F8-07 增加证据一致性、redaction 和降级测试 (P0, 依赖 V1-F8-06)

## 阶段 9：Retrieval Eval 与发布验收

- [ ] V1-F9-01 建立固定 retrieval fixture 和 ground truth (P0, 依赖 V1-F8-07)
- [ ] V1-F9-02 实现 rendered-file、first-read 与 map budget 指标 (P0, 依赖 V1-F9-01)
- [ ] V1-F9-03 实现完整 selector request 与 catalog truncation 指标 (P0, 依赖 V1-F9-02)
- [ ] V1-F9-04 实现 fallback、reduction、omission 与超预算指标 (P0, 依赖 V1-F9-03)
- [ ] V1-F9-05 接入 Pico evaluator (P0, 依赖 V1-F9-04)
- [ ] V1-F9-06 运行完整离线回归和架构边界检查 (P0, 依赖 V1-F9-05)
- [ ] V1-F9-07 使用真实 provider 演示 Branch A (P0, 依赖 V1-F9-06)
- [ ] V1-F9-08 使用真实 provider 演示 Branch B 和预算降级 (P0, 依赖 V1-F9-07)
- [ ] V1-F9-09 更新 README、配置、演示步骤和项目总进度 (P0, 依赖 V1-F9-08)

## 当前阻塞

- 阻塞项：无设计阻塞；根目录 Git 已初始化，但 baseline 尚未满足 V1-F0-01 门禁。
- 影响范围：所有实现阶段必须等待阶段 0 门禁。
- 需要决策：无。

## 最近完成

- 日期：2026-06-12
- 完成任务：依据最新 `SPEC_v1_3.md`、`FuncFlow_v1_3.md` 对齐项目施工计划
- 验证命令：计划一致性、依赖、字段、覆盖、旧语义与只读边界检查
- 结果：三处均为 87 个唯一任务且差异为 0；阶段分布为 `8/10/7/11/10/9/9/7/7/9`；字段、依赖、旧语义、核心覆盖和允许修改路径违规均为 0。
