package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Java-first 迁移阶段枚举。
 *
 * <p>控制 Java-first 替代路径的执行模式，从完全关闭到强制执行。 用于在 Python 到 Java 迁移过程中实现灰度切换和安全回退。
 *
 * <h2>四态语义</h2>
 *
 * <ul>
 *   <li>{@link #OFF} — 不启用任何 Java-first 替代路径，完全走原有链路。
 *   <li>{@link #SHADOW} — Java 路径参与执行但只生成对比日志，不影响输出。
 *   <li>{@link #ASSIST} — 只参与诊断，不影响主路径。
 *   <li>{@link #ENFORCE} — 只有在 fixture/validation 通过后才可候选默认。
 * </ul>
 *
 * <p>默认值为 {@link #OFF}，确保不破坏既有链路。
 */
@DomainModel
@RequiredArgsConstructor
public enum MigrationPhase {
  /** 不启用任何 Java-first 替代路径。 */
  OFF("off"),

  /** Java 路径参与执行但只生成对比日志，不影响输出。 */
  SHADOW("shadow"),

  /** 只参与诊断，不影响主路径。 */
  ASSIST("assist"),

  /** 只有在 fixture/validation 通过后才可候选默认。 */
  ENFORCE("enforce");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  private static final Map<String, MigrationPhase> BY_VALUE =
      Arrays.stream(values())
          .collect(Collectors.toUnmodifiableMap(MigrationPhase::getValue, Function.identity()));

  /** 默认迁移阶段，始终为 {@link #OFF}。 */
  public static final MigrationPhase DEFAULT = OFF;

  /**
   * 从外部协议值解析迁移阶段。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的迁移阶段枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知阶段
   * @throws NullPointerException 如果值为 null
   */
  public static MigrationPhase fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("迁移阶段值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    MigrationPhase phase = BY_VALUE.get(normalized);
    if (phase == null) {
      throw new IllegalArgumentException(
          "非法的迁移阶段值: '" + value + "'。允许值: off, shadow, assist, enforce");
    }
    return phase;
  }
}
