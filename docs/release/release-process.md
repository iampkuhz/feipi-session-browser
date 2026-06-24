# 发布流程

本文档描述 Feipi Session Browser Java 版本的发布流程。

## 版本管理

- **VERSION 文件**是版本号唯一真源，位于仓库根目录。
- 版本格式：`X.Y` 或 `X.Y.Z`，可选后缀如 `-rc.1`、`-alpha.1`。
- 所有构建、发行包和 GitHub Release 均从 VERSION 文件读取版本号。

## 发布流程

### 1. 准备发布

```bash
# 确认版本号
cat VERSION

# 验证工作区干净
git status

# 运行本地验证
./gradlew check
```

### 2. 创建 Release Candidate

```bash
# 验证模式（不创建 tag）
scripts/release/create-release-candidate.sh --dry-run

# 正式发布模式（创建 annotated tag）
scripts/release/create-release-candidate.sh
```

脚本验证：
- VERSION 文件格式合法
- 工作区无未提交改动
- tag 不存在重复
- `./gradlew check` 全部通过

### 3. 推送 Tag 触发 CI

```bash
git push origin v$(cat VERSION)
```

推送后 GitHub Actions 自动执行 release workflow：
1. **validate**：VERSION 与 tag 一致性校验
2. **quality**：`./gradlew check` 全量测试
3. **build**：四平台并行构建（macOS arm64/x64、Linux x64、Windows x64）
4. **verify-and-drill**：checksum 交叉验证 + 升级/回滚 drill
5. **publish-release**：创建 GitHub Release

### 4. 手动 Release Candidate（不发布）

通过 GitHub UI `workflow_dispatch` 触发，设置 `publish=false`，只构建验证不创建 Release。

## 失败原子性

Release workflow 采用阶段化设计：

- 任一前置阶段失败，后续阶段不执行。
- `publish-release` 仅在 `validate` 和 `verify-and-drill` 全部通过且 `publish=true` 时执行。
- 不发布 partial release。

## 升级/回滚 Drill

`scripts/release/drill-upgrade-rollback.sh` 在 CI 中自动执行，验证：

1. 四平台发行产物完整性
2. VERSION 一致性
3. 发行包包含 VERSION 文件
4. Checksum manifest 覆盖全部产物
5. 升级路径结构验证
6. 回滚安全性结构验证

## 校验放置

| 校验 | Trust boundary | 位置 |
|---|---|---|
| VERSION 与 tag 一致性 | CI 入口 | `release.yml` validate job |
| 工作区干净 | CI 入口 | `create-release-candidate.sh` |
| 测试通过 | 质量门禁 | `release.yml` quality job |
| Distribution SHA-256 | 发布边界 | `generate-checksums.sh` |
| Checksum 交叉验证 | 汇总阶段 | `release.yml` verify-and-drill job |
| Secret 泄漏扫描 | 汇总阶段 | `release.yml` verify-and-drill job |
| 消费者验证 | 下载后 | `generate-checksums.sh --verify` |

## 四平台产物

| 平台 | 架构 | 归档格式 | 产物名 |
|---|---|---|---|
| macOS | arm64 | tar.gz | `app-cli-runtime-macos-arm64.tar.gz` |
| macOS | x64 | tar.gz | `app-cli-runtime-macos-x64.tar.gz` |
| Linux | x64 | tar.gz | `app-cli-runtime-linux-x64.tar.gz` |
| Windows | x64 | zip | `app-cli-runtime-windows-x64.zip` |

每个平台额外产出 `app-cli-X.Y.zip`（标准 distribution，需系统 JDK）。
