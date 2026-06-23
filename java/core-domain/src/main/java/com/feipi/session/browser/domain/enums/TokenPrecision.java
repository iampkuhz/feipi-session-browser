package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Token 计量精度枚举。
 *
 * <p>描述 token 计数值的可信程度，从精确计数到估算值。 用于归一化 token 分解时标识数据来源的可靠性。
 */
@DomainModel
@RequiredArgsConstructor
public enum TokenPrecision {
  /** 精确计数，来自 provider 原始 usage 数据。 */
  EXACT("exact"),

  /** Provider 上报值，未经归一化处理。 */
  PROVIDER_REPORTED("provider_reported"),

  /** 估算值，可能基于部分数据推算。 */
  ESTIMATED("estimated"),

  /** 不可用，无有效数据来源。 */
  UNKNOWN("unavailable");

  /** 稳定外部协议值。 */
  @Getter private final String value;
}
