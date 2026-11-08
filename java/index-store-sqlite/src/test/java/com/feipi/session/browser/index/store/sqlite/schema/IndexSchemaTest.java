package com.feipi.session.browser.index.store.sqlite.schema;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;

/** 当前发行版只打开本版索引，不修复或重写其他格式。 */
class IndexSchemaTest {

  @Test
  void sameReleaseReopensWithoutChangingRows() throws SQLException {
    try (var conn = SqliteTestHelper.createInMemoryConnection();
        var stmt = conn.createStatement()) {
      IndexSchema.prepareRelease(conn, "1.0.0");
      stmt.executeUpdate("INSERT INTO index_metadata(key, value) VALUES ('test_data', 'original')");
      IndexSchema.prepareRelease(conn, "1.0.0");
      try (var rows = stmt.executeQuery("SELECT value FROM index_metadata WHERE key='test_data'")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getString(1)).isEqualTo("original");
      }
      assertThatThrownBy(() -> IndexSchema.prepareRelease(conn, "1.1.0"))
          .isInstanceOf(SQLException.class)
          .hasMessageContaining("其他发行版");
    }
  }

  @Test
  void existingUnrecognizedSchemaIsNotRebuiltInPlace() throws SQLException {
    try (var conn = SqliteTestHelper.createInMemoryConnection();
        var stmt = conn.createStatement()) {
      stmt.executeUpdate("CREATE TABLE sessions (previous_value TEXT)");
      stmt.executeUpdate("INSERT INTO sessions VALUES ('preserved')");
      assertThatThrownBy(() -> IndexSchema.prepareRelease(conn, "1.0.0"))
          .isInstanceOf(SQLException.class)
          .hasMessageContaining("全新的索引目录");
      try (var rows = stmt.executeQuery("SELECT previous_value FROM sessions")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getString(1)).isEqualTo("preserved");
      }
    }
  }
}
