package com.feipi.session.browser.arch;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * 枚举外部值守卫架构测试。
 *
 * <p>验证所有对外暴露的枚举类型都具有显式外部值模式：
 *
 * <ul>
 *   <li>拥有 {@code private final String value} 字段，通过 {@code getValue()} 访问。
 *   <li>拥有 {@code static fromValue(String)} 工厂方法，用于从外部协议值反序列化。
 * </ul>
 *
 * <p>这确保了枚举不依赖 {@code name()} 或 {@code ordinal()} 进行序列化/反序列化， 从而在枚举常量重命名或重排时不会破坏 JSON/CLI/API 兼容性。
 */
@DisplayName("Enum external value guard")
final class EnumExternalValueGuardTest {

  private EnumExternalValueGuardTest() {}

  /**
   * 需要检查的对外暴露枚举列表。
   *
   * <p>仅包含序列化到 JSON、CLI 或 API 响应的枚举。内部 SPI 状态枚举（如 {@code SourceOutcome}） 不在此列表中。
   */
  private static Stream<Arguments> externalEnums() {
    List<Arguments> enums = new ArrayList<>();

    // 领域层枚举：core-domain/enums/
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.CallStatus"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.TokenProvider"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.TokenSourceKind"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.CallScope"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.TokenTotalSemantics"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.TokenPrecision"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.enums.MigrationPhase"));

    // 领域层归一化枚举：core-domain/normalized/
    enums.add(Arguments.of("com.feipi.session.browser.domain.normalized.SourceUnitDirection"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.normalized.SourceFileRole"));
    enums.add(Arguments.of("com.feipi.session.browser.domain.normalized.NormalizedAgent"));

    // 查询接口层枚举：query-api/
    enums.add(Arguments.of("com.feipi.session.browser.query.api.SessionSortField"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.ProjectSortField"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.DiagnosticSeverity"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.PayloadSourceKind"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.PayloadVisibility"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.SortOrder"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.FailureStatus"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.SessionAnomalyKey"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.DiagnosticIssue"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.AnomalyType"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.AnomalySeverity"));
    enums.add(Arguments.of("com.feipi.session.browser.query.api.RoundSignalKey"));

    // 源适配器 SPI 层枚举：source-spi/
    enums.add(Arguments.of("com.feipi.session.browser.source.spi.SourceId"));
    enums.add(Arguments.of("com.feipi.session.browser.source.spi.ParseIssueType"));
    enums.add(Arguments.of("com.feipi.session.browser.source.spi.ParseSeverity"));

    return enums.stream();
  }

  /**
   * 每个对外枚举必须拥有 {@code getValue()} 方法，返回非 null 的外部协议字符串值。
   *
   * <p>这确保枚举常量有稳定的序列化标识，不依赖 {@code name()}。
   */
  @ParameterizedTest(name = "{0}")
  @MethodSource("externalEnums")
  @DisplayName("对外枚举必须拥有 getValue() 方法返回显式外部值")
  void enumMustHaveGetValueMethod(String className) throws Exception {
    Class<?> enumClass = Class.forName(className);
    assertThat(enumClass.isEnum()).as("%s 必须是枚举", className).isTrue();

    Method getValue = enumClass.getMethod("getValue");
    assertThat(getValue).as("%s 必须有 getValue() 方法", className).isNotNull();
    assertThat(Modifier.isPublic(getValue.getModifiers()))
        .as("%s.getValue() 必须是 public", className)
        .isTrue();

    // 验证每个枚举常量的 value 字段非 null 且非空
    for (Object constant : enumClass.getEnumConstants()) {
      Object value = getValue.invoke(constant);
      assertThat(value)
          .as("%s.%s 的 value 不得为 null", className, ((Enum<?>) constant).name())
          .isNotNull();
      assertThat(value.toString())
          .as("%s.%s 的 value 不得为空字符串", className, ((Enum<?>) constant).name())
          .isNotEmpty();
    }
  }

  /**
   * 每个对外枚举必须拥有 {@code fromValue(String)} 静态工厂方法，用于安全反序列化。
   *
   * <p>这确保枚举不依赖 {@code ordinal()} 或 {@code valueOf()} 进行反序列化。
   */
  @ParameterizedTest(name = "{0}")
  @MethodSource("externalEnums")
  @DisplayName("对外枚举必须拥有 fromValue(String) 静态工厂方法")
  void enumMustHaveFromValueMethod(String className) throws Exception {
    Class<?> enumClass = Class.forName(className);
    assertThat(enumClass.isEnum()).as("%s 必须是枚举", className).isTrue();

    Method fromValue = enumClass.getMethod("fromValue", String.class);
    assertThat(fromValue).as("%s 必须有 fromValue(String) 方法", className).isNotNull();
    assertThat(Modifier.isStatic(fromValue.getModifiers()))
        .as("%s.fromValue() 必须是 static", className)
        .isTrue();
    assertThat(Modifier.isPublic(fromValue.getModifiers()))
        .as("%s.fromValue() 必须是 public", className)
        .isTrue();
  }

  /**
   * 每个对外枚举的 {@code fromValue} 方法必须对 null 输入抛出异常。
   *
   * <p>不允许静默返回 null 或默认值。
   */
  @ParameterizedTest(name = "{0}")
  @MethodSource("externalEnums")
  @DisplayName("fromValue(null) 必须抛出异常")
  void fromValueMustRejectNull(String className) throws Exception {
    Class<?> enumClass = Class.forName(className);
    Method fromValue = enumClass.getMethod("fromValue", String.class);

    org.junit.jupiter.api.Assertions.assertThrows(
        Exception.class,
        () -> fromValue.invoke(null, (Object) null),
        className + ".fromValue(null) 必须抛出异常");
  }

  /**
   * 每个对外枚举的 {@code fromValue} 方法必须对非法输入抛出异常。
   *
   * <p>不允许静默返回默认值或 null。
   */
  @ParameterizedTest(name = "{0}")
  @MethodSource("externalEnums")
  @DisplayName("fromValue(unknown) 必须抛出异常")
  void fromValueMustRejectUnknown(String className) throws Exception {
    Class<?> enumClass = Class.forName(className);
    Method fromValue = enumClass.getMethod("fromValue", String.class);

    org.junit.jupiter.api.Assertions.assertThrows(
        Exception.class,
        () -> fromValue.invoke(null, "__definitely_not_a_valid_value__"),
        className + ".fromValue(unknown) 必须抛出异常");
  }

  /**
   * 每个对外枚举的 {@code fromValue} 方法必须能正确解析其所有常量的 value。
   *
   * <p>验证 value -> enum 的往返一致性：{@code fromValue(enum.getValue()) == enum}。
   */
  @ParameterizedTest(name = "{0}")
  @MethodSource("externalEnums")
  @DisplayName("fromValue(getValue()) 往返一致性")
  void fromValueMustRoundTrip(String className) throws Exception {
    Class<?> enumClass = Class.forName(className);
    Method getValue = enumClass.getMethod("getValue");
    Method fromValue = enumClass.getMethod("fromValue", String.class);

    for (Object constant : enumClass.getEnumConstants()) {
      String value = (String) getValue.invoke(constant);
      Object resolved = fromValue.invoke(null, value);
      assertThat(resolved)
          .as(
              "%s.fromValue(\"%s\") 必须返回 %s.%s",
              className, value, className, ((Enum<?>) constant).name())
          .isSameAs(constant);
    }
  }
}
