# Feipi Session Browser

在本机浏览 **Claude Code、Codex 和 Qoder** 的历史会话，按项目查找对话、回看工具调用、查看 Token 用量。

## 预览

> 截图待补 · [如何提供截图](docs/images/screenshots/README.md)

<!-- 图片就绪后取消对应行的注释。
![项目与会话列表](docs/images/screenshots/sessions.png)
![会话详情与 Token 统计](docs/images/screenshots/session-detail.png)
-->

## 开始使用

从 [Releases](https://github.com/iampkuhz/feipi-session-browser/releases) 下载对应系统与架构的 **runtime** 包（自带 Java），解压后在 `app-cli` 目录运行：

```bash
./bin/run serve          # macOS / Linux
```

Windows 使用 `.\bin\run.bat serve`。

打开 **[localhost:8848](http://127.0.0.1:8848)**。服务会自动扫描本机会话；保持终端开启，按 `Ctrl-C` 停止。

<details>
<summary>从源码启动（无对应发行包时）</summary>

需要 Git、JDK 25 和 Bash，首次构建需联网。

```bash
git clone https://github.com/iampkuhz/feipi-session-browser.git
cd feipi-session-browser
./scripts/session-browser.sh deps
./scripts/session-browser.sh serve
```

</details>

原始会话只读，索引保存在本机。分享截图前请脱敏，不要将服务直接暴露到公网。

[文档](docs/README.md) · [配置示例](docs/examples/session-browser.env.example) · [反馈问题](https://github.com/iampkuhz/feipi-session-browser/issues)
