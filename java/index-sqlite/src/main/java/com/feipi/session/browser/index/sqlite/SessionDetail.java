package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Objects;

/**
 * 会话详情聚合模型。
 *
 * <p>组合 {@link SessionRow} 基础行数据和归一化制品元信息，提供详情页所需的全部查询层数据。 不包含 HTTP 上下文或 Web view model， 由上层
 * presenter 消费。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionRow} 不得为 null。
 *   <li>{@code rounds} 不得为 null，使用不可变列表。
 *   <li>{@code payloadSources} 不得为 null，使用不可变列表。
 *   <li>{@code visibility} 不得为 null。
 * </ul>
 *
 * @param sessionRow 数据库会话行数据
 * @param rounds 归一化调用轮次列表
 * @param payloadSources 该会话可展开的 payload 来源列表
 * @param visibility 当前 payload 可见性策略
 * @param artifactPath 归一化制品路径，未关联制品时为空字符串
 * @param artifactSchemaVersion 制品 schema 版本，未关联制品时为空字符串
 * @param cacheKey 缓存键，包含制品 hash 和 index 版本信息
 */
public record SessionDetail(
    SessionRow sessionRow,
    List<CallRound> rounds,
    List<PayloadSource> payloadSources,
    PayloadVisibility visibility,
    String artifactPath,
    String artifactSchemaVersion,
    String cacheKey) {

  /**
   * 紧凑构造器，验证详情不变量并执行防御性拷贝。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public SessionDetail {
    Objects.requireNonNull(sessionRow, "sessionRow 不得为 null");
    Objects.requireNonNull(rounds, "rounds 不得为 null");
    Objects.requireNonNull(payloadSources, "payloadSources 不得为 null");
    Objects.requireNonNull(visibility, "visibility 不得为 null");

    rounds = List.copyOf(rounds);
    payloadSources = List.copyOf(payloadSources);
    artifactPath = artifactPath == null ? "" : artifactPath;
    artifactSchemaVersion = artifactSchemaVersion == null ? "" : artifactSchemaVersion;
    cacheKey = cacheKey == null ? "" : cacheKey;
  }

  /**
   * 创建不含制品关联的最小详情。
   *
   * @param sessionRow 数据库会话行
   * @param visibility 可见性策略
   * @return 仅包含行数据的详情实例
   */
  public static SessionDetail rowOnly(SessionRow sessionRow, PayloadVisibility visibility) {
    return new SessionDetail(sessionRow, List.of(), List.of(), visibility, "", "", "");
  }

  /** 详情包含的轮次数量。 */
  public int roundCount() {
    return rounds.size();
  }

  /** 详情包含的 payload 来源数量。 */
  public int payloadSourceCount() {
    return payloadSources.size();
  }

  /** 是否有关联的归一化制品。 */
  public boolean hasArtifact() {
    return !artifactPath.isEmpty();
  }
}
