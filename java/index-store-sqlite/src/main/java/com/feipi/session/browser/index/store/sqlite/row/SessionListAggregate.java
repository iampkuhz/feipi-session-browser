package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 过滤后会话列表的聚合总量。
 *
 * <p>对应 Python {@code get_sessions_list_aggregate} 查询结果，用于会话列表头部展示。 所有字段非负，由 SQL {@code COUNT} 和
 * {@code COALESCE(SUM(...), 0)} 保证。
 *
 * @param sessionCount 符合过滤条件的会话总数
 * @param projectCount 符合过滤条件的去重项目数
 * @param totalTokens 符合过滤条件的 token 总量，无匹配行时为 0
 * @param tokenProvenance 相同查询范围的四段计量来源
 */
public record SessionListAggregate(
    /* 符合过滤条件的会话总数。 */ @PositiveOrZero long sessionCount,
    /* 符合过滤条件的去重项目数。 */ @PositiveOrZero long projectCount,
    /* 符合过滤条件的 token 总量，无匹配行时为 0。 */ @PositiveOrZero long totalTokens,
    /* 相同查询范围的四段计量来源。 */ TokenProvenance tokenProvenance)
    implements com.feipi.session.browser.index.api.query.SessionListAggregate {

  /** 紧凑构造器，校验 record component 约束。 */
  public SessionListAggregate {
    tokenProvenance =
        tokenProvenance == null
            ? TokenProvenance.unknown(Math.max(0, sessionCount))
            : tokenProvenance;
    ValidationSupport.validateCanonicalConstructor(
        SessionListAggregate.class, sessionCount, projectCount, totalTokens, tokenProvenance);
  }

  /** 兼容未提供精度的旧调用点，不把旧数值推断为上报。 */
  public SessionListAggregate(long sessionCount, long projectCount, long totalTokens) {
    this(
        sessionCount,
        projectCount,
        totalTokens,
        TokenProvenance.unknown(Math.max(0, sessionCount)));
  }
}
