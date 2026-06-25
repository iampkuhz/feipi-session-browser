package com.feipi.session.browser.application;

import com.feipi.session.browser.domain.enums.MigrationPhase;
import java.util.Objects;

/**
 * 迁移阶段配置读取器。
 *
 * <p>从环境变量或显式指定的字符串值解析 {@link MigrationPhase}。 非法值时 fail-fast 并抛出带有清晰错误信息的异常。
 *
 * <h2>配置来源优先级</h2>
 *
 * <ol>
 *   <li>显式指定的值（通过 {@link #resolve(String)} 或构造器注入）
 *   <li>环境变量 {@value #ENV_VAR}
 *   <li>默认值 {@link MigrationPhase#OFF}
 * </ol>
 *
 * <p>环境变量名称为 {@code FEIPI_MIGRATION_PHASE}。
 */
public final class MigrationPhaseConfig {

  /** 环境变量名称。 */
  public static final String ENV_VAR = "FEIPI_MIGRATION_PHASE";

  private final MigrationPhase phase;

  /**
   * 使用指定的迁移阶段构造配置。
   *
   * @param phase 迁移阶段，不得为 null
   */
  public MigrationPhaseConfig(MigrationPhase phase) {
    this.phase = Objects.requireNonNull(phase, "迁移阶段不得为 null");
  }

  /**
   * 从环境变量读取迁移阶段配置。
   *
   * <p>读取 {@value #ENV_VAR} 环境变量。如果未设置或为空，返回 {@link MigrationPhase#DEFAULT}。 如果值非法，通过 {@link
   * MigrationPhase#fromValue(String)} fail-fast 抛出异常。
   *
   * @return 解析后的配置实例
   */
  public static MigrationPhaseConfig fromEnvironment() {
    return fromEnvironment(System::getenv);
  }

  /**
   * 从给定的环境变量提供者读取迁移阶段配置。
   *
   * <p>主要用于测试，允许注入自定义的环境变量查找逻辑。
   *
   * @param envProvider 环境变量提供者函数，接受变量名返回变量值
   * @return 解析后的配置实例
   */
  public static MigrationPhaseConfig fromEnvironment(EnvironmentProvider envProvider) {
    Objects.requireNonNull(envProvider, "环境变量提供者不得为 null");
    String raw = envProvider.get(ENV_VAR);
    if (raw == null || raw.trim().isEmpty()) {
      return new MigrationPhaseConfig(MigrationPhase.DEFAULT);
    }
    return new MigrationPhaseConfig(MigrationPhase.fromValue(raw));
  }

  /**
   * 从字符串值解析迁移阶段配置。
   *
   * <p>如果值为 null 或空白，返回默认配置 ({@link MigrationPhase#OFF})。
   *
   * @param value 配置字符串值
   * @return 解析后的配置实例
   * @throws IllegalArgumentException 如果值非法
   */
  public static MigrationPhaseConfig resolve(String value) {
    if (value == null || value.trim().isEmpty()) {
      return new MigrationPhaseConfig(MigrationPhase.DEFAULT);
    }
    return new MigrationPhaseConfig(MigrationPhase.fromValue(value));
  }

  /**
   * 获取当前配置的迁移阶段。
   *
   * @return 迁移阶段枚举值
   */
  public MigrationPhase getPhase() {
    return phase;
  }

  /**
   * 是否处于完全关闭状态。
   *
   * @return 如果阶段为 {@link MigrationPhase#OFF} 返回 true
   */
  public boolean isOff() {
    return phase == MigrationPhase.OFF;
  }

  /**
   * 是否启用了 shadow 模式。
   *
   * <p>shadow 模式下 Java 路径参与执行但只生成对比日志。
   *
   * @return 如果阶段为 {@link MigrationPhase#SHADOW} 返回 true
   */
  public boolean isShadow() {
    return phase == MigrationPhase.SHADOW;
  }

  /**
   * 是否启用了 assist 模式。
   *
   * <p>assist 模式下 Java 路径只参与诊断，不影响主路径。
   *
   * @return 如果阶段为 {@link MigrationPhase#ASSIST} 返回 true
   */
  public boolean isAssist() {
    return phase == MigrationPhase.ASSIST;
  }

  /**
   * 是否启用了 enforce 模式。
   *
   * <p>enforce 模式下 Java 路径在 fixture/validation 通过后可作为候选默认。
   *
   * @return 如果阶段为 {@link MigrationPhase#ENFORCE} 返回 true
   */
  public boolean isEnforce() {
    return phase == MigrationPhase.ENFORCE;
  }

  /**
   * 是否启用了任何 Java-first 替代路径。
   *
   * @return 如果阶段不是 {@link MigrationPhase#OFF} 返回 true
   */
  public boolean isJavaFirstEnabled() {
    return phase != MigrationPhase.OFF;
  }

  /** 环境变量提供者函数式接口。 */
  @FunctionalInterface
  public interface EnvironmentProvider {
    /**
     * 获取环境变量值。
     *
     * @param name 环境变量名称
     * @return 环境变量值，未设置时返回 null
     */
    String get(String name);
  }
}
