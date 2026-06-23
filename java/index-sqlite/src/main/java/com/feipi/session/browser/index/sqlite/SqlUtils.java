package com.feipi.session.browser.index.sqlite;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

/**
 * 仓库层共享的 SQL 工具方法。
 *
 * <p>集中放置跨仓库重复的辅助逻辑：null 转空字符串、参数绑定、WHERE 子句值对象。 包级私有，不暴露到 repository 之外。
 */
final class SqlUtils {

  /** 防止实例化。 */
  private SqlUtils() {}

  /**
   * null 转空字符串。
   *
   * <p>SQLite TEXT 列的 null 值统一为空字符串，与 domain record 紧凑构造器的默认值语义一致。
   *
   * @param value 原始字符串，可能为 null
   * @return 非 null 字符串
   */
  static String nullToEmpty(String value) {
    return value == null ? "" : value;
  }

  /**
   * 将参数列表绑定到 {@link PreparedStatement}。
   *
   * <p>支持 {@link String}、{@link Long}、{@link Integer} 三种类型。 其他类型跳过绑定（当前仓库不产生其他参数类型）。
   *
   * @param ps 目标 statement
   * @param params 参数列表，顺序与 {@code ?} 占位符一致
   * @param startIndex 起始参数索引（从 1 开始）
   * @return 下一个可用参数索引
   * @throws SQLException 绑定失败
   */
  static int bindParams(PreparedStatement ps, List<Object> params, int startIndex)
      throws SQLException {
    int index = startIndex;
    for (Object param : params) {
      if (param instanceof String s) {
        ps.setString(index, s);
      } else if (param instanceof Long l) {
        ps.setLong(index, l);
      } else if (param instanceof Integer i) {
        ps.setInt(index, i);
      }
      index++;
    }
    return index;
  }

  /**
   * 不可变 WHERE 子句和参数列表。
   *
   * <p>{@code whereFragment} 为空字符串或 {@code WHERE ...} 形式。 {@code params} 为对应的绑定参数，顺序与 {@code ?}
   * 占位符一致。
   *
   * @param whereFragment WHERE 子句片段
   * @param params 绑定参数列表
   */
  record WhereClauses(String whereFragment, List<Object> params) {

    // 构造不变量：字段不得为 null
    WhereClauses {
      if (whereFragment == null) {
        throw new NullPointerException("whereFragment 不得为 null");
      }
      if (params == null) {
        throw new NullPointerException("params 不得为 null");
      }
    }
  }
}
