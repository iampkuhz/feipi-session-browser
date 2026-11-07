# Feipi Session Browser

在本机浏览 **Claude Code、Codex 和 Qoder** 的历史会话，按项目查找对话、回看工具调用、查看 Token 用量。

## 预览

> 截图待补 · [如何提供截图](docs/images/screenshots/README.md)

<!-- 图片就绪后取消对应行的注释。
![项目与会话列表](docs/images/screenshots/sessions.png)
![会话详情与 Token 统计](docs/images/screenshots/session-detail.png)
-->

## 下载发行包

新发行仅支持 Apple Silicon（macOS arm64）。从 [GitHub Releases](https://github.com/iampkuhz/feipi-session-browser/releases) 下载 macOS arm64 runtime 包和 `MANIFEST.SHA256`。核对后解压，运行包内的 `bin/run serve`，打开终端给出的地址。包内置 Java，不需要 Git 或 Gradle。

见[安装、更新与失败恢复](docs/release/README.md#安装更新与恢复)。维护或修改源码时，使用下面的开发入口。

## 从源码开始使用

需要 Git、JDK 25 和 Bash，首次构建需联网。

### 1. 拉取代码

```bash
git clone https://github.com/iampkuhz/feipi-session-browser.git
cd feipi-session-browser
```

### 2. 构建并启动

在仓库根目录运行（已拉取代码可直接从这一步开始）：

```bash
./scripts/session-browser.sh deps
./scripts/session-browser.sh serve
```

`deps` 构建启动器并检查运行环境；每次执行 `serve` 前会执行 Gradle 增量构建，不运行测试。

### 3. 浏览会话

打开 **[localhost:8848](http://127.0.0.1:8848)**。服务会自动扫描本机会话；保持终端开启，按 `Ctrl-C` 停止。

原始会话只读，索引保存在本机。分享截图前请脱敏，不要将服务直接暴露到公网。

[文档](docs/README.md) · [配置示例](docs/examples/session-browser.env.example) · [反馈问题](https://github.com/iampkuhz/feipi-session-browser/issues)
