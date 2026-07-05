package com.feipi.session.browser.index.sqlite;

/** SQLite 行对象共享校验工具。 */
final class RowValidators {

  private RowValidators() {}

  /**
   * 校验 double 数值非负。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   */
  static void requireNonNegative(double value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }

  /**
   * 校验 long 数值非负。
   *
   * @param value 字段值
   * @param fieldName 字段名称
   */
  static void requireNonNegative(long value, String fieldName) {
    if (value < 0) {
      throw new IllegalArgumentException(fieldName + " 必须非负; got " + value);
    }
  }
}
