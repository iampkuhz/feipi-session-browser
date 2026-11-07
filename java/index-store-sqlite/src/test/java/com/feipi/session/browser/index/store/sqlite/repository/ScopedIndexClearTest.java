package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.api.write.IndexWriterPort;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/** 来源清理的端口向后兼容和实际 SQLite 外键、元数据关联回归。 */
class ScopedIndexClearTest {
  @Test
  void legacyPortDelegatesEmptyScopeButFailsExplicitlyWithoutErasingOtherSources() {
    var clears = new AtomicInteger();
    var writer =
        (IndexWriterPort)
            Proxy.newProxyInstance(
                IndexWriterPort.class.getClassLoader(),
                new Class<?>[] {IndexWriterPort.class},
                (proxy, method, args) -> {
                  if (method.isDefault())
                    return InvocationHandler.invokeDefault(proxy, method, args);
                  if (method.getName().equals("clearExistingIndex")
                      && method.getParameterCount() == 0) {
                    clears.incrementAndGet();
                    return null;
                  }
                  throw new UnsupportedOperationException("Unexpected fixture call");
                });
    writer.clearExistingIndex(Set.of());
    assertThat(clears).hasValue(1);
    assertThatThrownBy(() -> writer.clearExistingIndex(Set.of("codex")))
        .isInstanceOf(UnsupportedOperationException.class);
    assertThat(clears).hasValue(1);
  }

  @Test
  void sqliteClearsMultipleSelectedAgentsAndExactMetadataKeysWithoutTouchingGlobalState()
      throws Exception {
    try (var connection = DriverManager.getConnection("jdbc:sqlite::memory:")) {
      var writer = new SqliteIndexWriter(connection);
      writer.ensureSchema();
      try (var statement = connection.createStatement()) {
        statement.executeUpdate(
            "INSERT INTO sessions(session_key,session_id,agent,project_key,ended_at) VALUES"
                + " ('codex:a','a','codex','',''),('claude:a','a','claude_code','',''),('qoder:codex:a','a','qoder','','')");
        statement.executeUpdate(
            "INSERT INTO session_artifacts(session_key,artifact_type,path) SELECT"
                + " session_key,'normalized','/synthetic/' || session_key FROM sessions");
        statement.executeUpdate(
            "INSERT INTO index_metadata(key,value) SELECT 'scan_candidate_metadata:' ||"
                + " session_key,'fingerprint' FROM sessions");
        statement.executeUpdate(
            "INSERT INTO index_metadata(key,value) VALUES"
                + " ('scan_logic_version','10'),('published_generation','G-before')");
      }
      writer.clearExistingIndex(Set.of("codex", "claude_code"));
      assertThat(values(connection, "SELECT session_key FROM sessions"))
          .containsExactly("qoder:codex:a");
      assertThat(values(connection, "SELECT session_key FROM session_artifacts"))
          .containsExactly("qoder:codex:a");
      assertThat(values(connection, "SELECT key || '=' || value FROM index_metadata ORDER BY key"))
          .containsExactly(
              "published_generation=G-before",
              "scan_candidate_metadata:qoder:codex:a=fingerprint",
              "scan_logic_version=10");
      writer.clearExistingIndex(Set.of());
      assertThat(values(connection, "SELECT session_key FROM sessions")).isEmpty();
      assertThat(values(connection, "SELECT session_key FROM session_artifacts")).isEmpty();
      assertThat(values(connection, "SELECT key || '=' || value FROM index_metadata ORDER BY key"))
          .containsExactly("published_generation=G-before", "scan_logic_version=10");
    }
  }

  private static List<String> values(java.sql.Connection connection, String sql) throws Exception {
    List<String> values = new ArrayList<>();
    try (var statement = connection.createStatement();
        var rows = statement.executeQuery(sql)) {
      while (rows.next()) values.add(rows.getString(1));
    }
    return values;
  }
}
