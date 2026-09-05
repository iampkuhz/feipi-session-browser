# Repository Root Layout Spec

## Requirements

### Requirement: 受控顶层保持 14 项

仓库 SHALL 仅保留 11 个受控顶层目录：`.agents/`、`.claude/`、`.codex/`、`.github/`、`.qoder/`、`docs/`、`harness/`、`java/`、`openspec/`、`scripts/`、`skills/`，以及 `.gitignore`、`AGENTS.md`、`README.md` 三个文件。旧入口 SHALL NOT 通过副本、转发文件或软链接恢复。

#### Scenario: 验证未提交的目录迁移

- **Given** Git index 可能仍包含已移除的旧路径
- **When** 验证受控工作树布局
- **Then** 检查 SHALL 包含实际存在的 tracked 文件与未被忽略的新文件，顶层集合精确为 14 项
- **And** Git 元数据、ignored 本地数据、venv、依赖缓存与其他 worktree SHALL 不因顶层计数被删除

### Requirement: 测试与配置按职责拥有

Python 工程工具测试 SHALL 位于 `scripts/tests/`；浏览器验证 SHALL 位于 `java/tests/playwright/`；产品合成样本 SHALL 共用 `java/tests/fixtures/`，渲染样本位于其 `rendering/` 子目录，不复制样本。Java 架构、Checkstyle、PMD 和 CPD 配置 SHALL 位于 `java/gradle/config/`；Web 基线 SHALL 位于 `java/tests/quality-gates/config/`；跨语言术语 SHALL 单一存储于 `scripts/gates/config/technical-terms.json`；用户环境示例 SHALL 位于 `docs/examples/`。

#### Scenario: 移动质量工具输入

- **Given** 工具配置或测试改变目录
- **When** 执行 Gate、测试发现或基线更新
- **Then** 读取路径、写回路径、触发规则与隐私和禁止 skip 检查 SHALL 使用同一新布局
- **And** 原测试身份、断言、样本内容与质量阈值 MUST 保留

### Requirement: Python 工具显式选择工程配置

`pyproject.toml`、`uv.lock`、`.python-version` 和 `.pre-commit-config.yaml` SHALL 位于 `scripts/`。调用者 SHALL 显式使用项目/配置路径；pytest SHALL 从仓库根执行并固定 rootdir。安装 pre-commit SHALL 指定 `--config scripts/.pre-commit-config.yaml`，MUST NOT 强制覆盖用户自定义 hook。

#### Scenario: 从仓库根运行工具

- **Given** 顶层无 Python 或 pre-commit 转发配置
- **When** 执行工具安装、测试或 hooks
- **Then** 工具 SHALL 读取 `scripts/` 内的唯一配置，仓库资源仍按仓库根定位

### Requirement: 源版本与发行版本共享单一真源

源码版本 SHALL 存放于 `java/gradle/VERSION`；生成构建信息与发行包 SHALL 使用此文件。发行包自身根目录 MUST 保留 `VERSION`，不改变 CLI 版本或用户命令。

#### Scenario: 构建自包含发行包

- **Given** 源码顶层不存在 VERSION
- **When** 生成归档并运行包内 CLI
- **Then** 包根 VERSION、CLI 版本与源码真源 SHALL 一致

### Requirement: 发行工具与实际构建 JDK 一致

发行任务 SHALL 使用实际 Gradle JVM 所属 JDK 的 `jdeps` 和 `jlink`，不分别从 shell PATH 或 JAVA_HOME 选择另一套安装。发行任务 MUST 声明 JDK 身份、release 文件、工具以及 runtime 模块输入，避免切换 JDK 后错误复用旧 runtime。

#### Scenario: 使用 JDK25 重新验收

- **Given** 本机可能同时存在多个 JDK，交互式 shell 与子进程的默认 Java 不同
- **When** 显式设置 JDK25 的 JAVA_HOME/PATH 并重新构建发行包
- **Then** Gradle、测试进程及包内 runtime SHALL 均被验证为25
- **And** 同一 JDK 输入的后续构建 SHALL 可正确复用缓存
