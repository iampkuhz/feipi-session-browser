package com.feipi.session.browser.application;

import com.feipi.session.browser.application.diagnostics.AnomalyDetector;
import com.feipi.session.browser.application.sessiondetail.NormalizedArtifactReader;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.query.SessionDetailPort;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Objects;
import java.util.Optional;

/**
 * 会话详情查询 use case。
 *
 * <p>组合 {@link SessionDetailPort} 和 {@link NormalizedArtifactReader}，装配完整的会话详情。 支持异常检测和可选缓存。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>sessionKey 格式由调用方保证，本 use case 信任已验证的键。
 *   <li>制品加载由 {@link NormalizedArtifactReader} 在入口完成文件存在性和 JSON 结构校验。
 *   <li>装配逻辑信任已验证的 {@link SessionRecord} 和 {@link NormalizedSessionArtifact}。
 * </ul>
 */
public final class SessionDetailUseCase {

  private final SessionDetailPort repository;
  private final NormalizedArtifactReader artifactReader;
  private final int schemaVersion;

  /**
   * 创建会话详情 use case。
   *
   * @param repository 会话详情仓库
   * @param artifactReader 归一化制品读取器
   * @param schemaVersion 当前 schema 版本号
   */
  public SessionDetailUseCase(
      SessionDetailPort repository, NormalizedArtifactReader artifactReader, int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
    this.artifactReader = Objects.requireNonNull(artifactReader, "artifactReader 不得为 null");
    this.schemaVersion = schemaVersion;
  }

  /**
   * 查询并装配会话详情。
   *
   * <p>查找会话行，加载归一化制品（如有），装配为完整详情模型。无制品时返回行级详情。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return 装配完成的详情，会话不存在时返回 empty
   * @throws IOException 制品文件读取失败
   */
  public Optional<SessionDetail> getDetail(String sessionKey, PayloadVisibility visibility)
      throws IOException {
    return getDetailContext(sessionKey, visibility).map(DetailContext::detail);
  }

  /**
   * 查询并装配会话详情，同时返回已加载的归一化制品。
   *
   * <p>HTTP/API 适配层如需基于归一化制品构建 round/payload 投影，可消费本方法返回的上下文，避免直接依赖具体制品加载器。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return 详情上下文，会话不存在时返回 empty
   * @throws IOException 制品文件读取失败
   */
  public Optional<DetailContext> getDetailContext(String sessionKey, PayloadVisibility visibility)
      throws IOException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    Optional<SessionRecord> rowOpt = repository.findSession(sessionKey);
    if (rowOpt.isEmpty()) {
      return Optional.empty();
    }

    SessionRecord row = rowOpt.get();
    var artifactRow = repository.findNormalizedArtifact(sessionKey);
    if (artifactRow.isEmpty()) {
      return Optional.of(new DetailContext(SessionDetail.rowOnly(row, visibility), null));
    }

    Path artifactPath = Path.of(artifactRow.get().path());
    NormalizedSessionArtifact artifact = artifactReader.load(artifactPath);
    SessionDetail detail =
        SessionDetailAssembler.assemble(
            row, artifact, visibility, artifactRow.get().path(), schemaVersion);
    return Optional.of(new DetailContext(detail, artifact));
  }

  /**
   * 查询会话详情并附加异常检测。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return 详情和异常摘要，会话不存在时返回 empty
   * @throws IOException 制品文件读取失败
   */
  public Optional<AnnotatedDetail> getDetailWithAnomalies(
      String sessionKey, PayloadVisibility visibility) throws IOException {
    Optional<AnnotatedDetailContext> contextOpt =
        getDetailContextWithAnomalies(sessionKey, visibility);
    if (contextOpt.isEmpty()) {
      return Optional.empty();
    }

    AnnotatedDetailContext context = contextOpt.get();
    return Optional.of(new AnnotatedDetail(context.detail(), context.anomalies()));
  }

  /**
   * 查询并装配会话详情、异常摘要和归一化制品上下文。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return 带异常摘要的详情上下文，会话不存在时返回 empty
   * @throws IOException 制品文件读取失败
   */
  public Optional<AnnotatedDetailContext> getDetailContextWithAnomalies(
      String sessionKey, PayloadVisibility visibility) throws IOException {
    Optional<DetailContext> contextOpt = getDetailContext(sessionKey, visibility);
    if (contextOpt.isEmpty()) {
      return Optional.empty();
    }

    DetailContext context = contextOpt.get();
    SessionAnomalySummary anomalies = AnomalyDetector.detect(context.detail().sessionRow());
    return Optional.of(new AnnotatedDetailContext(context.detail(), anomalies, context.artifact()));
  }

  /**
   * 已装配的详情及其归一化制品上下文。
   *
   * @param detail 会话详情
   * @param artifact 已加载归一化制品；无制品时为 null
   */
  public record DetailContext(
      /* 会话详情。 */
      @NotNull SessionDetail detail,

      /* 已加载归一化制品；无制品时为 null。 */
      NormalizedSessionArtifact artifact) {

    /**
     * 紧凑构造器，验证详情不变量。
     *
     * @throws NullPointerException 当 detail 为 null 时
     */
    public DetailContext {
      ValidationSupport.validateCanonicalConstructor(DetailContext.class, detail, artifact);
    }
  }

  /**
   * 附带异常摘要的会话详情。
   *
   * @param detail 会话详情
   * @param anomalies 异常摘要
   */
  public record AnnotatedDetail(
      /* 会话详情。 */
      @NotNull SessionDetail detail,

      /* 异常摘要。 */
      @NotNull SessionAnomalySummary anomalies) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AnnotatedDetail {
      ValidationSupport.validateCanonicalConstructor(AnnotatedDetail.class, detail, anomalies);
    }
  }

  /**
   * 附带异常摘要和归一化制品的会话详情。
   *
   * @param detail 会话详情
   * @param anomalies 异常摘要
   * @param artifact 已加载归一化制品；无制品时为 null
   */
  public record AnnotatedDetailContext(
      /* 会话详情。 */
      @NotNull SessionDetail detail,

      /* 异常摘要。 */
      @NotNull SessionAnomalySummary anomalies,

      /* 已加载归一化制品；无制品时为 null。 */
      NormalizedSessionArtifact artifact) {

    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AnnotatedDetailContext {
      ValidationSupport.validateCanonicalConstructor(
          AnnotatedDetailContext.class, detail, anomalies, artifact);
    }
  }
}
