# 02 Symbol Index Tasks

## 模块目标

构建 Git tracked/staged Python-only 文件枚举、tree-sitter Definition/Reference 提取、SymbolIndex、稳定 snapshot id 和可降级 cache。

## 相关设计

- 当前迁移前来源：`SPEC_v1_3.md` 7.3、7.4、16、17.1。
- 迁移后来源：`doc/SPEC.md`。

## 模块依赖

- 阶段 1 全部门禁通过。

## 模块通用边界

- **允许修改**：`pico/pico/features/map_engine/source_files.py`、`symbol_index.py`、`queries/python-tags.scm`、对应测试与 fixture。
- **禁止修改**：GraphRanker、ContextRenderer、MapEngine runtime 接入、Pico core、Aider 源码。
- **模块原则**：source_files 只枚举路径；SymbolIndex 只负责解析、结构和 cache，不承担 ranking/rendering。

## 任务列表

### V1-F2-01：实现 Git tracked/staged 文件枚举

- **优先级**：P0
- **依赖**：V1-F1-10
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：Git index 路径枚举 helper 与 fixture tests
- **允许修改路径**：`source_files.py`、`pico/tests/test_map_engine_source_files.py`
- **禁止修改边界**：不得递归扫描文件系统或解析文件内容
- **步骤**：通过 `git ls-files --cached -z` 枚举 repo-relative path；支持从仓库子目录启动。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_source_files.py -q
  ```
- **完成标准**：tracked 与 staged 新文件可枚举，路径稳定且 repo-relative。
- **回退条件**：依赖 shell 文本分行导致空格/特殊字符路径错误。

### V1-F2-02：实现 Python-only、denylist 和非 Git 降级

- **优先级**：P0
- **依赖**：V1-F2-01
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：过滤规则、跳过原因与降级异常
- **允许修改路径**：`source_files.py`、`test_map_engine_source_files.py`
- **禁止修改边界**：不得在 Git 失败时递归扫描
- **步骤**：保留当前存在普通 `.py` 文件；排除 `.git/`、`.pico/`、虚拟环境、缓存和生成目录；记录删除/排除项。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_source_files.py -q
  ```
- **完成标准**：untracked、非 Python、删除文件和 denylist 文件均不进入索引输入。
- **回退条件**：Git 失败后出现文件系统 fallback。

### V1-F2-03：使用 tree-sitter query 提取 definitions

- **优先级**：P0
- **依赖**：V1-F2-02
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：MapCode-owned Python query、definition parser
- **允许修改路径**：`queries/python-tags.scm`、`symbol_index.py`、`pico/tests/test_map_engine_symbol_index.py`
- **禁止修改边界**：不得直接读取或导入 Aider query；不得实现 references fallback
- **步骤**：复制并标注允许迁移的 query；解析 class/function/constant definitions；输出 0-based line。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_symbol_index.py -q
  ```
- **完成标准**：固定 Python fixture 提取预期 definitions，许可证归属完整。
- **回退条件**：query/API 兼容性与 V1-F0-07 结论不一致。

### V1-F2-04：提取 references 并隔离单文件失败

- **优先级**：P0
- **依赖**：V1-F2-03
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：reference records、单文件 skipped evidence
- **允许修改路径**：`symbol_index.py`、`test_map_engine_symbol_index.py`
- **禁止修改边界**：不得因单文件失败中断整个索引
- **步骤**：提取 Python call references；单文件读取、解码、parse/query 异常转为 skipped file。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_symbol_index.py -q
  ```
- **完成标准**：fixture definitions/references 正确；损坏文件被跳过且其他文件继续。
- **回退条件**：异常被吞掉且没有 evidence，或整个索引失败。

### V1-F2-05：构建 SymbolIndex 和稳定 snapshot id

- **优先级**：P0
- **依赖**：V1-F2-04
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：包含 `all_defs`、definitions、references、file_records 的只读 SymbolIndex 与 canonical snapshot id
- **允许修改路径**：`symbol_index.py`、`test_map_engine_symbol_index.py`
- **禁止修改边界**：不得运行 PageRank 或生成 prompt 文本
- **步骤**：构建 `all_defs`、`definitions_by_symbol`、`definitions_by_file`、`references_by_file`、`file_records`；按 SPEC canonical JSON 规则生成 snapshot id；保证后续 PromptAnalyzer、focused symbol 前缀和 SelectorCandidateCatalog 读取同一 snapshot。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_symbol_index.py -q
  ```
- **完成标准**：相同有序文件元数据和版本产生相同 snapshot id；同一 snapshot 可同时提供 symbol 命中、精确 DefinitionRecord 和全量 candidate paths。
- **回退条件**：snapshot id 受 dict 插入顺序或 ranking policy 影响。

### V1-F2-06：实现 index/cache 读取与 cache hit

- **优先级**：P0
- **依赖**：V1-F2-05
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：`.pico/map_engine/index.json`、`cache.meta.json` 读写与复用
- **允许修改路径**：`symbol_index.py`、`test_map_engine_symbol_index.py`
- **禁止修改边界**：不得写入 session、RunStore 或 trace
- **步骤**：按 mtime/size/version 复用未变化文件；持久化结构化索引和 metadata。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_symbol_index.py -q
  ```
- **完成标准**：cache hit 时未修改文件不重复解析。
- **回退条件**：cache 与当前工作树内容来源混淆，或 cache 写失败中断索引。

### V1-F2-07：实现版本失效、文件变化与 cache 失败 evidence

- **优先级**：P0
- **依赖**：V1-F2-06
- **输入**：当前最新 SPEC/FuncFlow、依赖任务产物、任务允许修改路径中的真实源码与测试
- **输出**：完整 CacheEvidence 与失效测试
- **允许修改路径**：`symbol_index.py`、`test_map_engine_symbol_index.py`
- **禁止修改边界**：不得将 cache 错误升级为 Pico runtime 错误
- **步骤**：覆盖 parser/query/schema 版本变化、文件新增/修改/删除、cache read/write failure。
- **验证命令**：
  ```powershell
  .\.venv\Scripts\python.exe -m pytest pico\tests\test_map_engine_source_files.py pico\tests\test_map_engine_symbol_index.py -q
  .\.venv\Scripts\python.exe -m ruff check pico\pico\features\map_engine pico\tests
  ```
- **完成标准**：CacheEvidence 可区分 hit/miss/read_failed 与 write 状态；阶段 2 门禁全部通过。
- **回退条件**：失效策略不能稳定复现或错误阻断 MapEngine。
