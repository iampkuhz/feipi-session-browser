package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** {@link ScanLogManager} 事务语义测试。 */
class ScanLogManagerTest {

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    IndexSchema.withDefaults().ensureSchema(conn);
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void startScanInsertsRunningEntry() throws SQLException {
    long id = ScanLogManager.startScan(conn, 1000.0);

    assertThat(id).isGreaterThan(0);

    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery("SELECT status, mode, started_at FROM scan_log WHERE id = " + id)) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("status")).isEqualTo("running");
      assertThat(rs.getString("mode")).isEqualTo("full");
      assertThat(rs.getDouble("started_at")).isEqualTo(1000.0);
    }
  }

  @Test
  void completeScanUpdatesStatusAndCounts() throws SQLException {
    long id = ScanLogManager.startScan(conn, 1000.0);

    ScanLogManager.completeScan(conn, id, 2000.0, Map.of("claude_code", 5, "codex", 3, "qoder", 1));

    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT status, finished_at, claude_count, codex_count, qoder_count FROM scan_log WHERE id = "
                    + id)) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("status")).isEqualTo("success");
      assertThat(rs.getDouble("finished_at")).isEqualTo(2000.0);
      assertThat(rs.getInt("claude_count")).isEqualTo(5);
      assertThat(rs.getInt("codex_count")).isEqualTo(3);
      assertThat(rs.getInt("qoder_count")).isEqualTo(1);
    }
  }

  @Test
  void failScanUpdatesStatusToFailure() throws SQLException {
    long id = ScanLogManager.startScan(conn, 1000.0);

    ScanLogManager.failScan(conn, id, 2000.0, Map.of());

    try (Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT status FROM scan_log WHERE id = " + id)) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("status")).isEqualTo("failure");
    }
  }

  @Test
  void missingSourceCountsDefaultToZero() throws SQLException {
    long id = ScanLogManager.startScan(conn, 1000.0);

    ScanLogManager.completeScan(conn, id, 2000.0, Map.of("claude_code", 10));

    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT claude_count, codex_count, qoder_count FROM scan_log WHERE id = " + id)) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getInt("claude_count")).isEqualTo(10);
      assertThat(rs.getInt("codex_count")).isZero();
      assertThat(rs.getInt("qoder_count")).isZero();
    }
  }
}
