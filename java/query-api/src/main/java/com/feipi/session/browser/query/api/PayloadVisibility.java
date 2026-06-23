package com.feipi.session.browser.query.api;

/**
 * payload 可见性策略枚举。
 *
 * <p>控制会话详情 API 返回的 payload 内容是否包含敏感字段。 单一 owner 管理全部可见性规则，避免多处分散判断。
 *
 * <ul>
 *   <li>{@link #STANDARD}：敏感字段默认隐藏，只返回摘要级 payload。
 *   <li>{@link #FULL}：展开全部 payload 内容，包括请求和响应正文。
 * </ul>
 */
public enum PayloadVisibility {

  /** 标准可见性：敏感字段默认隐藏。 */
  STANDARD,

  /** 完整可见性：展开全部 payload 正文。 */
  FULL
}
