# 任务：ac-010-contract-freeze

## 任务 1：运行质量门禁并记录基线

- [x] 运行 `./gradlew check`、`./gradlew qualityFull`、`./scripts/session-browser.sh test`、中文注释检查。

  **验证：** Gradle check 547 tests PASS；qualityFull PASS；session-browser 13 failed / 3619 passed（pre-existing，与 artifact normalization 无关）；中文注释检查 PASS。

## 任务 2：列出 Python normalized artifact symbol 和调用者

- [x] 搜索 `src/session_browser/` 中 normalized artifact 相关模块，找出 writer/reader/consumer/hash/association/repair 函数，记录调用者。

  **验证：** 14 个核心 symbol 已分类：5 writer、3 reader、3 validator、4 producer。调用者映射到 scanners、attribution、cli、writers。

## 任务 3：冻结 S2C 契约

- [x] 在 `openspec/changes/ac-010-contract-freeze/design.md` 中冻结 batch protocol v1.0、canonical path、meta/hash、session status、错误语义、三条 producer 路径。

  **验证：** design.md 包含 6 项冻结契约，每项有输入输出格式和 fixture 占位。

## 任务 4：记录 ownership matrix

- [x] 在 design.md 中记录当前 Python 拥有、S2C 后 Java 拥有、禁止提前实施的 S3-S5 边界。

  **验证：** ownership matrix 包含 5 个从 Python 转移的组件、4 个 Java 已有能力、5 个 S3-S5 禁止边界。

## 任务 5：生成 AC-CONTRACT-FROZEN.json marker

- [x] 在 `tmp/java-migration-run/` 下创建 AC-CONTRACT-FROZEN.json。

  **验证：** marker 包含 frozen_contracts、validation_results、ownership_transfer、python_symbols_cataloged、java_existing_capabilities。

## 任务 6：创建验收契约文件

- [x] 在 `docs/acceptance-contracts/features/AC_ARTIFACT_CUTOVER.md` 创建契约用例表。

  **验证：** 10 个契约用例，每个有 fixture 和 owning task。
