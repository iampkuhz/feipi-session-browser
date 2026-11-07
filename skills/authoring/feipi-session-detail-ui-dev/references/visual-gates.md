# Visual Gates 参考

开发反馈见本 skill。以下命令仅用于规则定位及显式 baseline 维护。

## Baseline 文件与显式维护

- `java/tests/quality-gates/config/web-quality-baselines.json` 的 `rules.layout-inline-style.entries` — 行内样式基线。
- `java/tests/quality-gates/config/web-quality-baselines.json` 的 `rules.raw-innerhtml.entries` — innerHTML 基线。

修改 baseline 前必须确认变更是有意为之，不是为了绕过 gate。完成审阅后，才可显式执行唯一 Gradle task：

```bash
./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates \
  -PfeipiJavaQualityRules=layout-inline-style \
  -PfeipiJavaQualityBaselineUpdateRules=layout-inline-style

./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates \
  -PfeipiJavaQualityRules=raw-innerhtml \
  -PfeipiJavaQualityBaselineUpdateRules=raw-innerhtml
```

CSS ownership 没有可维护 baseline；运行 catalog 顶层 Gate `webStaticRules` 时，内部使用 Java
`css-ownership` rule 并保留隔离 artifact。单 rule 命令只用于内部 rule 诊断：

```bash
./java/gradlew -p java :java:tests:quality-gates:runJavaQualityGates -PfeipiJavaQualityRules=css-ownership
```
