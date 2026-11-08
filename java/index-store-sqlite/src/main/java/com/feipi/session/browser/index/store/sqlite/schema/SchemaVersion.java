package com.feipi.session.browser.index.store.sqlite.schema;

import com.feipi.session.browser.common.validation.ParamChecks;

/**
 * Schema 版本号，独立于 scan logic version。
 *
 * @param version 正整数版本号，从 1 开始
 */
public record SchemaVersion(int version) {

  /**
   * 创建版本号。
   *
   * @param version 正整数版本号
   * @throws IllegalArgumentException 版本号小于 1
   */
  public SchemaVersion {
    ParamChecks.atLeast(version, 1, "schema version");
  }
}
