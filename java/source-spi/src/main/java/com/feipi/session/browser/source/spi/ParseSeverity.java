package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 解析诊断严重级别。
 *
 * <p>对应 JSONL 解析过程中产生的诊断信息严重程度。 该枚举与 Python 端 {@code ParseSeverity} 对齐。
 */
@DomainModel
public enum ParseSeverity {

  /** 信息级别，不影响解析结果。 */
  @CoreField
  INFO,

  /** 警告级别，解析继续但数据可能不完整。 */
  @CoreField
  WARNING,

  /** 错误级别，对应条目无法解析。 */
  @CoreField
  ERROR;
}
