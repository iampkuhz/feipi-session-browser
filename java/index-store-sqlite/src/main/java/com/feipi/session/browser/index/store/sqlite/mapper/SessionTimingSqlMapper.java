package com.feipi.session.browser.index.store.sqlite.mapper;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.SessionTiming;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;

/** SQLite单列保存中性计时map，旧行默认空对象，不从旧执行数字反推来源。 */
public final class SessionTimingSqlMapper {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};

  private SessionTimingSqlMapper() {}

  /** 编码直接timing对象，不包含外层session/timing包装。 */
  public static String encode(SessionTiming timing) {
    try {
      return MAPPER.writeValueAsString(timing.toMetadata().get("timing"));
    } catch (JsonProcessingException e) {
      throw new IllegalArgumentException("Cannot encode session timing", e);
    }
  }

  /** 读取新计时列；旧库经schema修复得到{}并保留unknown。 */
  public static SessionTiming read(ResultSet rs) throws SQLException {
    String json = rs.getString("timing_json");
    if (json == null || json.isBlank()) {
      return SessionTiming.unknown(null);
    }
    try {
      return SessionTiming.fromMetadata(Map.of("timing", MAPPER.readValue(json, MAP_TYPE)));
    } catch (JsonProcessingException e) {
      throw new SQLException("Invalid session timing metadata", e);
    }
  }
}
