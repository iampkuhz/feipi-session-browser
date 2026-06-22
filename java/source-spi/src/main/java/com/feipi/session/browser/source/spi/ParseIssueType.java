package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 解析问题类型。
 *
 * <p>标识 JSONL 解析过程中遇到的具体问题类别。 该枚举与 Python 端 {@code ParseIssue} 对齐。
 */
@DomainModel
public enum ParseIssueType {

  /** JSON 格式损坏，无法解析。 */
  @CoreField
  BAD_JSON,

  /** 合法 JSON 但非对象类型，已跳过。 */
  @CoreField
  NON_OBJECT_SKIPPED,

  /** 检测到拼接对象边界（{@code }{ }），已拆分处理。 */
  @CoreField
  CONCATENATED_OBJECTS;
}
