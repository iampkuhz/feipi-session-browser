# AC-010 验收契约：Artifact Cutover 契约冻结

## 范围

| 维度 | 说明 |
|---|---|
| 契约 ID | AC-010 |
| Stage | S2C - Canonical Artifact Cutover |
| Kind | PLAN |
| 目标 | 冻结 batch protocol、canonical path、meta/hash、session status、错误语义、producer 路径契约 |

## 契约用例

| 用例 ID | 优先级 | 场景 | 断言 | fixture | owning task |
|---|---|---|---|---|---|
| AC-010-01 | P0 | batch protocol v1.0 header | NDJSON header 包含 protocolVersion, startedAt | fixture: batch-header.json | AC-020 |
| AC-010-02 | P0 | batch result ok | result 包含 requestId, sessionKey, artifactPath, metaPath, hashes | fixture: batch-result-ok.json | AC-020 |
| AC-010-03 | P0 | batch result error | error result 包含 sanitized error message | fixture: batch-result-error.json | AC-020 |
| AC-010-04 | P0 | canonical path 格式 | `<output-root>/<sourceId>/<safe-key>/<session-id>/normalized.json` | fixture: canonical-path.json | AC-030 |
| AC-010-05 | P0 | meta/hash 一致性 | dataSha256 与 data 文件 SHA-256 匹配 | fixture: meta-hash-match.json | AC-030 |
| AC-010-06 | P0 | meta 缺失拒绝 | meta 文件缺失时 validate() 返回 false | fixture: meta-missing.json | AC-030 |
| AC-010-07 | P1 | safe path component | 特殊字符被安全替换 | fixture: safe-path-component.json | AC-030 |
| AC-010-08 | P0 | full scan producer | full_scan 对每个 session 生成 artifact pair | fixture: full-scan.json | AC-040 |
| AC-010-09 | P0 | incremental scan producer | 未变 session 复用已有 artifact | fixture: incremental-reuse.json | AC-040 |
| AC-010-10 | P0 | tiered codex producer | codex rollout 生成 normalized artifact | fixture: codex-tiered.json | AC-040 |

## 边界约束

- S2C 不修改 production code
- S3/S4/S5 组件不在本 stage 实施
- 所有 Python 侧 artifact 代码在 S2C 期间保持只读
