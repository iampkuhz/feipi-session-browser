## 模块定位

本仓库 Java 模块按分层架构组织：

- **core-domain** — 领域模型和核心接口，不依赖外部框架。
- **source-spi** — 数据源 SPI 接口定义。
- **sources** — 各数据源实现（Claude、Codex、Qoder 等）。
- **artifact-normalized** — 标准化产物模型。
- **normalization-engine** — 归一化引擎，将原始数据转换为标准产物。
- **index-api** — 索引与查询端口。
- **index-store-sqlite** — SQLite 索引实现层。
- **scan-engine** — 扫描引擎。
- **application** — 应用层（query API、分页、DTO）。
- **web** — Web 层（API controller、UI 模板）。
- **common** — 公共工具。
- **java:app-cli** — CLI composition root 与发行入口。

依赖方向：CLI/API → application → 各 engine → core-domain。禁止反向依赖。

## 分层检查

- API 层（`web`、`application`）不直接访问底层实现（`index-store-sqlite`、`sources`）；具体实现只在 `java:app-cli` composition root 组装。
- Service 层不写 UI 模板。
- Repo 层不做渲染或格式化。
- Domain 层不依赖任何上层模块。

分层规则由 `config/architecture/java-modules.yaml` 中的 `allowedProjectDeps` 和 `forbiddenImports` 强制。

## DTO / Mapper / DAO / Repo / Service 分层

命名和分层遵循现有模式：

- **DTO** — 放在 `application` 或 `web` 模块的 `dto` 或 `api` 包下。
- **Mapper** — 与被映射对象同模块，命名 `*Mapper` 或 `*Mapping`。
- **DAO/Repo** — 放在对应数据模块，命名 `*Repository` 或 `*Dao`。
- **Service** — 放在 `application` 或业务模块，命名 `*Service`。

不新发明分层。新类应参照相邻已有类的包路径和命名风格。

## API / CLI 边界

- API controller 只接收请求参数和返回 DTO，不暴露内部实体。
- CLI 入口只做参数解析和调用 Service，不包含业务逻辑。
- API snapshot 文件（`config/api-snapshots/`）记录公共 API 签名，修改 API 时必须同步更新。

## 测试和 fixture

- 单元测试放在 `src/test/java/` 对应包下。
- 架构测试放在 `java:tests:architecture`。
- 契约测试放在 `java:tests:contracts`。
- 测试支持工具放在 `java:tests:support`。
- 测试 fixture 优先使用真实数据样本的脱敏子集，不要编造无意义 mock。

## 常见反模式

- API controller 直接解析文件系统。
- UI 模板依赖 Java 内部实体（应通过 DTO 传递）。
- Repo 返回未脱敏 request/response 原文。
- 测试只 mock 不覆盖真实样例。
- 新增 product Python 逻辑（本仓库 Java 功能不应引入 Python 产品代码变更）。
- 为通过编译删除 gate 或禁用质量检查。
- 添加 `@SuppressWarnings` 掩盖问题（应修复根因）。
- 新增 skip（`@Disabled`、`Assumptions.assumeTrue` 跳过测试）。
- 跨模块直接 import 被 `forbiddenImports` 禁止的包。
- 在 `core-domain` 中引入 Spring 或其他框架依赖。
