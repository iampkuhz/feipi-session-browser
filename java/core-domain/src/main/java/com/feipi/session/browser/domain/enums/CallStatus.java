package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 调用状态枚举。
 *
 * <p>标识一次 LLM 调用的最终执行结果状态。 用于 token 归因、错误统计和会话质量分析。
 */
@DomainModel
@RequiredArgsConstructor
public enum CallStatus {
  /** 调用成功完成。 */
  OK("ok"),

  /** 调用执行出错。 */
  ERROR("error"),

  /** 调用已正常完成（与 OK 语义相近，保留兼容）。 */
  COMPLETED("completed");

  /** 稳定外部协议值。 */
  @Getter private final String value;
}
