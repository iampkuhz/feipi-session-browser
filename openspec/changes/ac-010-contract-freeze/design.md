# 设计：AC-010 当前状态验签、Artifact 所有权与 Cutover 契约冻结

## 1. 当前仓库健康状态

| 验证命令 | 结果 | Exit code |
|---|---|---|
| `./gradlew check` | PASS - 547 tests, 0 failed/skipped | 0 |
| `./gradlew qualityFull` | PASS - JaCoCo 报告生成完成 | 0 |
| `./scripts/session-browser.sh test` | 13 failed / 3619 passed | 1 (pre-existing) |
| `python3 scripts/quality/check_code_comment_language.py --jobs auto` | PASS - 196 files | 0 |

session-browser 13 个失败均为 pre-existing（timeline preview tool count 和 release version contract），与 artifact normalization 无关。

## 2. Python normalized artifact 调用图

### 2.1 核心模块：`src/session_browser/normalized/`

| 模块 | 关键 symbol | 职责 |
|---|---|---|
| `artifacts.py` | `normalized_artifact_path()` | 生成 canonical artifact 路径 |
| `artifacts.py` | `write_normalized_session_artifact()` | 写入 JSON artifact + meta（含 schema validate） |
| `artifacts.py` | `persist_normalized_session_artifact()` | write + SQLite upsert_session_artifact |
| `artifacts.py` | `persist_current_normalized_session_artifact_reference()` | 复用已有 artifact 引用 |
| `artifacts.py` | `find_current_normalized_session_artifact()` | 查找当前有效 artifact |
| `artifacts.py` | `read_normalized_session_artifact()` | 读取 JSON artifact |
| `artifacts.py` | `_write_artifact_meta()` / `_read_artifact_meta()` / `_artifact_meta_matches()` | meta 侧车文件读写与一致性校验 |
| `models.py` | `NormalizedSessionArtifact` | artifact 数据模型 |
| `models.py` | `validate_normalized_artifact_model()` | 结构化模型校验 |
| `schema.py` | `validate_normalized_session()` | schema + semantic 完整校验 |
| `semantic.py` | semantic check functions | 语义层校验 |
| `constants.py` | `NORMALIZED_SCHEMA_VERSION` | 版本号常量 |

### 2.2 调用者映射

| Producer 路径 | 调用链 |
|---|---|
| `scanners.full_scan()` | -> `_persist_normalized_artifact_safe()` -> `persist_normalized_session_artifact()` -> `write_normalized_session_artifact()` |
| `scanners.incremental_scan()` | 同上 + `persist_current_normalized_session_artifact_reference()` 复用 |
| `scanners` (codex path) | -> `_build_codex_normalized_for_scan()` -> 同上 |

| Consumer 路径 | 调用链 |
|---|---|
| `scanners.full_scan()` / `incremental_scan()` | -> `find_current_normalized_session_artifact()` -> `read_normalized_session_artifact()` -> `_summary_from_normalized_artifact()` |
| `scanners` (current artifact reuse) | -> `find_current_normalized_session_artifact()` -> `_summary_from_current_artifact()` |
| `attribution/context.py` | -> `read_normalized_session_artifact()` |
| `attribution/agents/claude_code_attribution_builder.py` | -> `read_normalized_session_artifact()` |
| `attribution/agents/qoder_attribution_builder.py` | -> `read_normalized_session_artifact()` |
| `cli.py` | -> `find_current_normalized_session_artifact()` (CLI 入口) |
| `index/writers.py` | -> `upsert_session_artifact()` (SQLite association) |

| Hash/Verify 路径 | 调用链 |
|---|---|
| `artifacts._artifact_meta_matches()` | 被 `find_current_normalized_session_artifact()` 调用 |
| `models.validate_normalized_artifact_model()` | 被 `schema.validate_normalized_session()` 调用 |
| `schema.validate_normalized_session()` | 被 `write_normalized_session_artifact()` 调用 |

| Repair 路径 | 调用链 |
|---|---|
| `artifacts.persist_normalized_session_artifact()` | 重建 artifact 并写入 |
| `_should_force_normalized_artifact_rebuild()` | scanners 中判断是否强制重建 |

### 2.3 三条 artifact producer 路径

1. **Full scan**：`full_scan()` -> 对每个 session 调用 `_persist_normalized_artifact_safe()` -> 全量重建
2. **Incremental scan**：`incremental_scan()` -> 优先 `persist_current_normalized_session_artifact_reference()` 复用 -> 仅对变更 session 重建
3. **Tiered (codex)**：`_build_codex_normalized_for_scan()` -> codex 特殊 normalized 构建 -> 同 persist 路径

## 3. Java 已有 normalized batch 能力

| 模块 | 类 | 状态 |
|---|---|---|
| `core-domain` | `NormalizedSessionArtifact`, `NormalizedCall`, `NormalizedToolExecution` 等 | 已完成：域模型 record |
| `normalization-engine` | `NormalizationEngine`, `CallBuilder`, `TokenAccountant` | 已完成：scan -> artifact 转换 |
| `artifact-normalized` | `NormalizedArtifactWriter` | 已完成：JSON write + meta + hash validate |
| `artifact-normalized` | `CanonicalJsonWriter` | 已完成：canonical JSON 序列化（enum/path 定制） |
| `app-cli` | `NormalizedBatchCommand` | 已完成：stdin/stdout batch protocol v1.0 |

### Java 尚未实现（S2C 范围）

- SQLite association writer（`upsert_session_artifact` Java 等价）
- Artifact consumer / reader in batch mode
- Freshness check（meta 一致性校验 in batch）
- Incremental/tiered scan 调度

## 4. 冻结契约

### 4.1 Batch Protocol

```
输入：NDJSON lines
  - header: { protocolVersion, startedAt }
  - request: { type:"request", requestId, sourceId, rootPath }
  - input: { type:"input", requestId, filePath, sessionKey }

输出：NDJSON lines
  - result: { type:"result", requestId, sessionKey, status, artifactPath, metaPath, hashes, error? }
  - end: { type:"end", completedAt, summary }
```

- Protocol version: `1.0`
- 所有路径使用 OS-native 绝对路径
- hash: SHA-256 of data file content

### 4.2 Canonical Path

```
<output-root>/<sourceId>/<safe-project-key>/<session-id>/normalized.json
<output-root>/<sourceId>/<safe-project-key>/<session-id>/normalized.meta.json
```

- `safe-project-key` 通过 `_safe_path_component()` 生成
- pair 原子性：data + meta 必须成对出现，缺失任一则 invalid

### 4.3 Meta/Hash

```json
{
  "schemaVersion": "<int>",
  "generatedAt": "<ISO-8601>",
  "sourceId": "<string>",
  "sessionKey": "<string>",
  "sourceFiles": [{"path": "<abs>", "sha256": "<hex>"}],
  "dataSha256": "<hex>"
}
```

- meta 必须与 data 内容 hash 一致
- `find_current_normalized_session_artifact()` 验证 meta 匹配才返回

### 4.4 Session Status

| Status | 含义 |
|---|---|
| `ok` | 成功生成 artifact |
| `error` | 生成失败（含 sanitized error message） |
| `skipped` | fingerprint 未变，复用已有 artifact |

### 4.5 错误和取消语义

- 单 session 失败不中断 batch
- error message 中的路径信息被 sanitize（去除绝对路径前缀）
- batch 整体 exit code：0 = 全部成功或 skipped；非 0 = 有 error

### 4.6 三条 Producer 路径契约

| 路径 | 输入 | 输出 | S2C 变化 |
|---|---|---|---|
| Full | all session roots | 全量 artifact 重建 | Java batch 接管 |
| Incremental | changed sessions only | 复用或重建 | Java batch 接管 |
| Tiered (codex) | codex rollout path | codex-specific normalized | Java batch 接管 |

## 5. Ownership Matrix

### 当前（S2C 前）

| 组件 | Owner | 语言 |
|---|---|---|
| Source file discovery | Python `scanners.py` | Python |
| Normalized artifact write | Python `artifacts.py` | Python |
| Normalized artifact read | Python `artifacts.py` | Python |
| Artifact meta hash/verify | Python `artifacts.py` | Python |
| SQLite association | Python `writers.py` | Python |
| Schema validation | Python `schema.py` | Python |
| Batch NDJSON protocol | Java `NormalizedBatchCommand` | Java (已有) |
| NormalizedSession model | Java `core-domain` | Java (已有) |
| NormalizationEngine | Java `normalization-engine` | Java (已有) |
| Artifact JSON writer | Java `NormalizedArtifactWriter` | Java (已有) |

### S2C 结束后

| 组件 | Owner | 语言 |
|---|---|---|
| Batch normalization (full/incremental/tiered) | Java | Java |
| Artifact JSON write + meta | Java `NormalizedArtifactWriter` | Java |
| Artifact hash/verify | Java `NormalizedArtifactWriter.validate()` | Java |
| Batch protocol I/O | Java `NormalizedBatchCommand` | Java |
| SQLite association write | Java (新增) | Java |
| Artifact consumer (batch read) | Java (新增) | Java |
| Source file discovery (for batch) | Java via SourceAdapter | Java |

### S2C 不触碰（禁止提前实施）

| 组件 | 所属 stage |
|---|---|
| Web UI / API presenter | S3 |
| Attribution engine Java port | S3 |
| Session detail page Java backend | S4 |
| Python 完全移除 | S5 |
| SQLite read path Java 迁移 | S3+ |

## 6. 风险

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| session-browser 13 个 pre-existing 测试失败 | 已知 | 低 | 与 artifact normalization 无关，不阻塞 S2C |
| Python/Java artifact 格式 diverge | 中 | 高 | 冻结 schema version + canonical path 契约；Java writer 必须通过 fixture 对齐测试 |
| batch protocol 扩展需求 | 低 | 中 | v1.0 冻结；后续通过 version bump 演进 |
