package com.feipi.session.browser.index.store.sqlite.mapper;

import com.feipi.session.browser.domain.normalized.TokenProvenance;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

/** 同一 SELECT/WHERE/GROUP BY 中组合四段精度与会话覆盖，不能用 token 数字或 agent 推断。 */
public final class TokenProvenanceSqlMapper {

  /** 会话行持久化的完整计量来源列。 */
  public static final String COLUMNS =
      "fresh_input_token_precision, cache_read_token_precision, cache_write_token_precision, "
          + "output_token_precision, token_estimation_method, token_contains_estimated, "
          + "token_contains_unavailable, token_contains_unknown";

  private TokenProvenanceSqlMapper() {}

  /** 与既有数字聚合共享参与行的 SELECT 片段，不包含开头逗号。 */
  public static String aggregateColumns() {
    List<String> expressions = new ArrayList<>();
    for (String column :
        List.of(
            "fresh_input_token_precision",
            "cache_read_token_precision",
            "cache_write_token_precision",
            "output_token_precision")) {
      expressions.add(
          "CASE WHEN COUNT(DISTINCT "
              + column
              + ") > 1 THEN 'mixed' "
              + "ELSE COALESCE(MIN("
              + column
              + "), 'unknown') END AS "
              + column);
    }
    expressions.add(
        "COALESCE(GROUP_CONCAT(DISTINCT NULLIF(token_estimation_method, '')), '') AS"
            + " token_estimation_method");
    for (String column :
        List.of(
            "token_contains_estimated", "token_contains_unavailable", "token_contains_unknown")) {
      expressions.add("COALESCE(SUM(" + column + "), 0) AS " + column);
    }
    return String.join(", ", expressions);
  }

  /** 读取单会话行或同范围的聚合 SELECT；覆盖列在前者为 0/1，后者为 SUM。 */
  public static TokenProvenance read(ResultSet rs) throws SQLException {
    return new TokenProvenance(
        rs.getString("fresh_input_token_precision"), rs.getString("cache_read_token_precision"),
        rs.getString("cache_write_token_precision"), rs.getString("output_token_precision"),
        rs.getString("token_estimation_method"), rs.getLong("token_contains_estimated"),
        rs.getLong("token_contains_unavailable"), rs.getLong("token_contains_unknown"));
  }
}
