# Java 25 代码精简规约

## 核心原则

- **行为一致而非源码形状一致**：只要公开 API、协议值、序列化格式和测试结果不变，优先采用更适合长期维护的 Java 写法。
- **Java 原生优先**：纯不可变数据载体优先使用 record；只有当 record 不适用（如 enum 上的构造器/访问器样板）时才使用受控 Lombok。
- **受控 Lombok**：当前允许清单仅为 `@Getter` 和 `@RequiredArgsConstructor`。

## Lombok 约束

- `lombok.config` 禁止 `experimental`、`builder`、`sneakyThrows`（flagUsage = error）。
- `@DomainModel` 标注的类型允许使用 `@Getter` 和 `@RequiredArgsConstructor`，由 ArchUnit 规则 `coreDomainMustNotDependOnUnapprovedLombok` 执行。
- Lombok 不进入运行时 classpath（`compileOnly` + `annotationProcessor`）。
- 测试源码仅在实际使用时添加 `testCompileOnly` 和 `testAnnotationProcessor`。

## 枚举规则

- 外部枚举值必须通过 `private final` 字段显式声明。
- `getValue()` 返回显式赋值的字符串常量，不使用 `name().toLowerCase()`、`ordinal()` 或 `toString()`。
- 纯值枚举（只有 value 字段 + 赋值构造器 + 纯返回 getter）必须使用受控 Lombok。
- 含 `fromValue()` 等业务逻辑的枚举保留显式代码，但 value 字段和 getter 部分仍可使用 Lombok。

## 保留显式代码的例外

- 含校验、防御性复制、归一化的构造器必须显式保留。
- record 的紧凑构造器在存在不变量校验时保留。
- JavaBeans、Jackson 反射或框架要求的 API 不得为减少代码量而改变。
- 任何可能改变 `equals`、`hashCode`、`toString`、构造器可见性或 JSON 属性名的转换必须先补充契约测试。

## PMD 检测

- 自定义规则 `FeipiManualEnumValueBoilerplate` 检测纯手动枚举样板，提示改用受控 Lombok。
- 不使用 `@SuppressWarnings("PMD.")` 压制自定义 PMD 规则；遇到违规时直接修复源码。
- `noJavaSuppressWarnings` 质量门禁脚本扫描 `java/**/src/main/java/**/*.java`，发现 `@SuppressWarnings("PMD.` 即 FAIL。
- Java 标准编译器告警（`unchecked`、`deprecation` 等）的 `@SuppressWarnings` 不受此限制。
