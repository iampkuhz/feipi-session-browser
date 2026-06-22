package com.feipi.session.browser.source.spi;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/**
 * 符合 SPI 契约的测试用假适配器。
 *
 * <p>用于 contract test 验证 SPI 接口行为。不执行实际文件 I/O；
 * 所有行为通过构造时注入的数据驱动。
 *
 * <p>该适配器保证：
 *
 * <ul>
 *   <li>发现结果按路径排序（确定性）。
 *   <li>指纹包含固定内容哈希。
 *   <li>解析结果可配置为四种状态之一。
 * </ul>
 */
public final class FakeSourceAdapter implements SourceAdapter {

  private final SourceId sourceId;
  private final List<Candidate> candidates;
  private final SourceOutcome parseOutcome;

  /**
   * 创建指定源标识和候选列表的假适配器。
   *
   * @param sourceId 源标识
   * @param candidates 预配置的候选项列表
   * @param parseOutcome 解析操作返回的结果状态
   */
  public FakeSourceAdapter(
      SourceId sourceId, List<Candidate> candidates, SourceOutcome parseOutcome) {
    Objects.requireNonNull(sourceId, "sourceId 不得为 null");
    Objects.requireNonNull(candidates, "candidates 不得为 null");
    Objects.requireNonNull(parseOutcome, "parseOutcome 不得为 null");
    this.sourceId = sourceId;
    this.candidates = List.copyOf(candidates);
    this.parseOutcome = parseOutcome;
  }

  /**
   * 创建使用默认成功状态的假适配器。
   *
   * @param sourceId 源标识
   * @param candidates 预配置的候选项列表
   */
  public FakeSourceAdapter(SourceId sourceId, List<Candidate> candidates) {
    this(sourceId, candidates, SourceOutcome.SUCCESS);
  }

  @Override
  public SourceId sourceId() {
    return sourceId;
  }

  @Override
  public SourceRoot checkRoot(Path rootPath) {
    return new SourceRoot(rootPath, rootPath, false, false, true);
  }

  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    List<Candidate> sorted =
        candidates.stream()
            .sorted(Comparator.comparing(c -> c.fingerprint().path()))
            .toList();
    return BoundedStream.of(
        sorted, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
  }

  @Override
  public SourceFingerprint fingerprint(Path filePath) {
    return new SourceFingerprint(
        filePath.toString(), sourceId, 0, 0, Optional.of("fake-hash"));
  }

  @Override
  public SourceResult parse(Candidate candidate, Optional<CancellationSignal> cancellation) {
    if (cancellation.isPresent() && cancellation.get().isCancelled()) {
      return new SourceResult.Skipped(List.of(), "cancelled");
    }
    List<SourceDiagnostic> emptyDiag = List.of();
    return switch (parseOutcome) {
      case SUCCESS -> new SourceResult.Success(emptyDiag, 1);
      case RETRYABLE_INCOMPLETE -> new SourceResult.RetryableIncomplete(emptyDiag, "fake retry");
      case SKIPPED -> new SourceResult.Skipped(emptyDiag, "fake skip");
      case FATAL -> new SourceResult.Fatal(emptyDiag, "fake fatal");
    };
  }

  /**
   * 创建符合 SPI 契约的测试候选项。
   *
   * @param path 文件路径
   * @param sessionKey 会话键
   * @param sourceId 源标识
   * @return 测试候选项
   */
  public static Candidate testCandidate(String path, String sessionKey, SourceId sourceId) {
    SourceFingerprint fp = new SourceFingerprint(path, sourceId, 100, 1000L, Optional.of("abc"));
    return new Candidate(fp, sessionKey, "test-project", java.util.Map.of());
  }

  /**
   * 创建包含一条诊断信息的测试诊断。
   *
   * @param severity 严重级别
   * @param issueType 问题类型
   * @param lineNo 行号
   * @return 测试诊断
   */
  public static SourceDiagnostic testDiagnostic(
      ParseSeverity severity, ParseIssueType issueType, int lineNo) {
    return new SourceDiagnostic(
        severity, issueType, "测试诊断信息: " + issueType, lineNo, Optional.of("preview"));
  }

  /**
   * 创建测试用的源根。
   *
   * @param rootPath 根路径
   * @param pathEscape 是否模拟路径逃逸
   * @return 测试源根
   */
  public static SourceRoot testSourceRoot(Path rootPath, boolean pathEscape) {
    return new SourceRoot(rootPath, rootPath, false, pathEscape, false);
  }
}
