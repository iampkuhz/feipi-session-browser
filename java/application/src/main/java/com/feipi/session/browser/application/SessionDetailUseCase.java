package com.feipi.session.browser.application;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.sqlite.AnomalyDetector;
import com.feipi.session.browser.index.sqlite.NormalizedArtifactLoader;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionDetailAssembler;
import com.feipi.session.browser.index.sqlite.SessionDetailRepository;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import java.io.IOException;
import java.nio.file.Path;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

/**
 * 会话详情查询 use case。
 *
 * <p>组合 {@link SessionDetailRepository} 和 {@link NormalizedArtifactLoader}，装配完整的会话详情。 支持异常检测和可选缓存。
 *
 * <p>校验放置：
 *
 * <ul>
 *   <li>sessionKey 格式由调用方保证，本 use case 信任已验证的键。
 *   <li>制品加载由 {@link NormalizedArtifactLoader} 在入口完成文件存在性和 JSON 结构校验。
 *   <li>装配逻辑信任已验证的 {@link SessionRow} 和 {@link NormalizedSessionArtifact}。
 * </ul>
 */
public final class SessionDetailUseCase {

  private final SessionDetailRepository repository;
  private final int schemaVersion;

  /**
   * 创建会话详情 use case。
   *
   * @param repository 会话详情仓库
   * @param schemaVersion 当前 schema 版本号
   */
  public SessionDetailUseCase(SessionDetailRepository repository, int schemaVersion) {
    this.repository = Objects.requireNonNull(repository, "repository 不得为 null");
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
   * @throws SQLException 数据库查询失败
   * @throws IOException 制品文件读取失败
   */
  public Optional<SessionDetail> getDetail(String sessionKey, PayloadVisibility visibility)
      throws SQLException, IOException {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    Optional<SessionRow> rowOpt = repository.findSessionRow(sessionKey);
    if (rowOpt.isEmpty()) {
      return Optional.empty();
    }

    SessionRow row = rowOpt.get();

    // 查找归一化制品
    var artifactRow = repository.findNormalizedArtifact(sessionKey);
    if (artifactRow.isEmpty()) {
      return Optional.of(SessionDetail.rowOnly(row, visibility));
    }

    // 加载制品
    Path artifactPath = Path.of(artifactRow.get().path());
    NormalizedSessionArtifact artifact = NormalizedArtifactLoader.load(artifactPath);

    SessionDetail detail =
        SessionDetailAssembler.assemble(
            row, artifact, visibility, artifactRow.get().path(), schemaVersion);
    return Optional.of(detail);
  }

  /**
   * 查询会话详情并附加异常检测。
   *
   * @param sessionKey 会话主键
   * @param visibility payload 可见性策略
   * @return 详情和异常摘要，会话不存在时返回 empty
   * @throws SQLException 数据库查询失败
   * @throws IOException 制品文件读取失败
   */
  public Optional<AnnotatedDetail> getDetailWithAnomalies(
      String sessionKey, PayloadVisibility visibility) throws SQLException, IOException {
    Optional<SessionDetail> detailOpt = getDetail(sessionKey, visibility);
    if (detailOpt.isEmpty()) {
      return Optional.empty();
    }

    SessionDetail detail = detailOpt.get();
    SessionAnomalySummary anomalies = AnomalyDetector.detect(detail.sessionRow());
    return Optional.of(new AnnotatedDetail(detail, anomalies));
  }

  /**
   * 附带异常摘要的会话详情。
   *
   * @param detail 会话详情
   * @param anomalies 异常摘要
   */
  public record AnnotatedDetail(SessionDetail detail, SessionAnomalySummary anomalies) {
    /**
     * 紧凑构造器，验证不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     */
    public AnnotatedDetail {
      Objects.requireNonNull(detail, "detail 不得为 null");
      Objects.requireNonNull(anomalies, "anomalies 不得为 null");
    }
  }
}
