package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

/**
 * Full scan 运行配置。
 *
 * <p>封装一次 full scan 所需的全部参数。不可变、线程安全。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sourceEntries} 不得为空。
 *   <li>{@code artifactOutputDir} 不得为 null。
 *   <li>{@code parseParallelism} 为正整数。
 * </ul>
 *
 * @param sourceEntries 待扫描的源适配器与根目录配对列表
 * @param artifactOutputDir 归一化制品输出目录
 * @param agentFilter 可选的 agent 过滤集合，空表示不过滤
 * @param parseParallelism 解析并行度上限，至少为 1
 */
public record ScanConfig(
    /* 待扫描的源适配器与根目录配对列表。 */
    @NotNull List<SourceEntry> sourceEntries,

    /* 归一化制品输出目录。 */
    @NotNull Path artifactOutputDir,

    /* 可选的 agent 过滤集合，空表示不过滤。 */
    Set<String> agentFilter,

    /* 解析并行度上限，至少为 1。 */
    @Positive int parseParallelism) {

  /**
   * 源适配器与根目录配对。
   *
   * @param adapter 源适配器实例
   * @param rootPath 源根目录路径
   */
  public record SourceEntry(
      /* 源适配器实例。 */
      @NotNull SourceAdapter adapter,

      /* 源根目录路径。 */
      @NotNull Path rootPath) {

    /**
     * 紧凑构造器，验证非 null。
     *
     * @throws NullPointerException 当任一字段为 null 时
     */
    public SourceEntry {
      ValidationSupport.validateCanonicalConstructor(SourceEntry.class, adapter, rootPath);
    }
  }

  /**
   * 紧凑构造器，验证不变量并执行防御性拷贝。
   *
   * @throws IllegalArgumentException 当 sourceEntries 为空或 parseParallelism 非法时
   */
  public ScanConfig {
    ValidationSupport.validateCanonicalConstructor(
        ScanConfig.class, sourceEntries, artifactOutputDir, agentFilter, parseParallelism);
    if (sourceEntries.isEmpty()) {
      throw new IllegalArgumentException("sourceEntries 不得为空");
    }
    sourceEntries = List.copyOf(sourceEntries);
    agentFilter = agentFilter == null ? Set.of() : Set.copyOf(agentFilter);
  }

  /**
   * 创建使用默认配置的配置。
   *
   * @param sourceEntries 待扫描的源适配器与根目录配对列表
   * @param artifactOutputDir 归一化制品输出目录
   * @return 新配置实例
   */
  public static ScanConfig defaults(List<SourceEntry> sourceEntries, Path artifactOutputDir) {
    return new ScanConfig(sourceEntries, artifactOutputDir, Set.of(), 1);
  }

  /**
   * 判断指定 agent 是否通过过滤器。
   *
   * @param agentValue agent 协议值
   * @return 过滤器为空或包含该 agent 时返回 {@code true}
   */
  public boolean isAgentAllowed(String agentValue) {
    return agentFilter.isEmpty() || agentFilter.contains(agentValue);
  }
}
