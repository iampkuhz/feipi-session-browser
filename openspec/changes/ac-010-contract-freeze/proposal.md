# 提案：ac-010-contract-freeze

## 问题

S2C stage（Canonical Artifact Cutover）需要一个明确的起点，验证当前仓库状态健康，冻结 Java batch 与 Python artifact producer/consumer 之间的契约边界，并记录 ownership 转移矩阵。

## 范围

包含：

- 运行当前质量门禁，确认 547 个 Java 测试和 3619 个 Python 测试基线。
- 列出 Python normalized artifact 所有 symbol 和调用者，分 writer/reader/validator/producer 四类。
- 冻结 batch protocol v1.0、canonical path、meta/hash、session status、错误语义、三条 producer 路径契约。
- 记录 ownership matrix：当前 Python 拥有、S2C 后 Java 拥有、禁止提前实施的 S3-S5 边界。
- 生成 AC-CONTRACT-FROZEN.json marker。

不包含（非目标）：

- 不修改 production code。
- 不实施 Java SQLite association writer、batch consumer/reader、freshness check。
- 不触碰 Web UI / API presenter / Attribution engine / Session detail page Java backend / Python 完全移除。

## 验证策略

- `./gradlew check --configuration-cache`
- `./gradlew qualityFull --configuration-cache`
- `./scripts/session-browser.sh test`（记录 pre-existing 失败，不要求修复）
- `python3 scripts/quality/check_code_comment_language.py --jobs auto`
