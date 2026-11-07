package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.index.api.query.RoundAssembler;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadSourceKind;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * 会话详情装配器。
 *
 * <p>将 {@link SessionRecord} 和 {@link NormalizedSessionArtifact} 组合为 {@link SessionDetail}。 装配逻辑包括：
 *
 * <ul>
 *   <li>将归一化调用按轮次分组（主会话调用顺序分配，子 agent 调用关联到父调用轮次）。
 *   <li>从调用和工具执行生成 payload 来源列表。
 *   <li>构建包含制品 hash 和 index 版本的缓存键。
 * </ul>
 *
 * <p>校验放置：本类信任已验证的 {@link SessionRecord} 和 {@link NormalizedSessionArtifact}， 不重复 domain 层校验。
 */
public final class SessionDetailAssembler {

  /** 防止外部实例化。 */
  private SessionDetailAssembler() {}

  /**
   * 将会话行和归一化制品装配为详情模型。
   *
   * @param sessionRow 数据库会话行
   * @param artifact 归一化制品，不得为 null
   * @param visibility payload 可见性策略
   * @param artifactPath 制品路径
   * @param indexVersion index schema 版本号
   * @return 装配完成的会话详情
   */
  public static SessionDetail assemble(
      SessionRecord sessionRow,
      NormalizedSessionArtifact artifact,
      PayloadVisibility visibility,
      String artifactPath,
      int indexVersion) {
    Objects.requireNonNull(sessionRow, "sessionRow 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    List<CallRound> rounds = RoundAssembler.buildRounds(artifact, sessionRow.userMessageCount());
    List<PayloadSource> payloadSources = buildPayloadSources(artifact.calls(), visibility);
    String cacheKey = buildCacheKey(artifactPath, indexVersion);

    return new SessionDetail(
        sessionRow,
        rounds,
        payloadSources,
        visibility,
        artifactPath,
        artifact.schemaVersion(),
        cacheKey);
  }

  /** 装配完整会话的计数，不保留大内容正文。 */
  public static SessionDetail assemble(
      SessionRecord row,
      com.feipi.session.browser.domain.normalized.NormalizedSessionContent content,
      PayloadVisibility visibility,
      String path,
      int version)
      throws java.io.IOException {
    var legacy = content.legacyArtifact();
    if (legacy.isPresent()) {
      return assemble(row, legacy.get(), visibility, path, version);
    }
    var reader = new SessionContentReader(content, row.userMessageCount());
    return new SessionDetail(
        row,
        List.of(),
        List.of(),
        visibility,
        path,
        content.header().schemaVersion(),
        buildCacheKey(path, version),
        reader.roundIndex().roundCount(),
        Math.toIntExact(Math.multiplyExact(content.header().totals().get("calls"), 2L)));
  }

  /**
   * 将调用列表按轮次分组。
   *
   * <p>主会话调用按顺序分配到独立轮次，子 agent 调用合并到其父调用所在的轮次。 没有父调用的子 agent 调用创建独立轮次。
   *
   * @param calls 归一化调用列表，按遍历顺序排列
   * @return 轮次列表
   */
  public static List<CallRound> buildRounds(List<NormalizedCall> calls) {
    return RoundAssembler.buildRounds(calls);
  }

  /**
   * 使用共享分组逻辑构建轮次和工具失败关联。
   *
   * @param calls 按遍历顺序排列的调用
   * @param toolExecutions 已观测的工具执行
   * @return 逻辑轮次列表
   */
  public static List<CallRound> buildRounds(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {
    return RoundAssembler.buildRounds(calls, toolExecutions);
  }

  /**
   * 从调用列表生成 payload 来源。
   *
   * <p>为每个调用生成请求和响应 payload 来源。归一化调用始终代表一次 LLM 交互， 具有请求和响应两侧内容。 标准可见性仅遮蔽敏感值，不表示内容截断。
   *
   * <p>内容解析通过 source unit 引用完成，本层只负责生成标识符和可见性标记。
   *
   * @param calls 归一化调用列表
   * @param visibility payload 可见性
   * @return payload 来源列表
   */
  static List<PayloadSource> buildPayloadSources(
      List<NormalizedCall> calls, PayloadVisibility visibility) {
    boolean truncated = false;
    List<PayloadSource> sources = new ArrayList<>();

    for (NormalizedCall call : calls) {
      boolean isSubagent = call.scope() == CallScope.SUBAGENT;
      String prefix = isSubagent ? "sa" : "main";

      // 每次调用都有请求和响应两侧
      PayloadSourceKind requestKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_REQUEST : PayloadSourceKind.LLM_REQUEST;
      sources.add(
          new PayloadSource(
              prefix + ":req:" + call.callId(),
              requestKind,
              call.callId(),
              "Request " + call.callKey(),
              truncated));

      PayloadSourceKind responseKind =
          isSubagent ? PayloadSourceKind.SUBAGENT_RESPONSE : PayloadSourceKind.LLM_RESPONSE;
      sources.add(
          new PayloadSource(
              prefix + ":resp:" + call.callId(),
              responseKind,
              call.callId(),
              "Response " + call.callKey(),
              truncated));
    }
    return sources;
  }

  /**
   * 构建缓存键，包含制品路径和 index 版本号。
   *
   * <p>缓存键用于 session data cache，保证制品更新或 index schema 变化时缓存失效。
   *
   * @param artifactPath 制品路径
   * @param indexVersion index schema 版本
   * @return 格式为 {@code artifact:<path>:v<version>} 的缓存键
   */
  public static String buildCacheKey(String artifactPath, int indexVersion) {
    if (artifactPath == null || artifactPath.isEmpty()) {
      return "novalue:v" + indexVersion;
    }
    return "artifact:" + artifactPath + ":v" + indexVersion;
  }
}
