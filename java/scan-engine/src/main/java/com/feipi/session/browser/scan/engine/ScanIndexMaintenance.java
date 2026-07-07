package com.feipi.session.browser.scan.engine;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import org.slf4j.Logger;

/** 扫描索引维护操作的共享入口。 */
final class ScanIndexMaintenance {

  private ScanIndexMaintenance() {}

  /** 清理现有 sessions 与 session_artifacts 数据，用于重建索引。 */
  static void clearExistingIndex(Connection conn, Logger log) throws SQLException {
    try (PreparedStatement stmt = conn.prepareStatement("DELETE FROM session_artifacts")) {
      stmt.executeUpdate();
    }
    try (PreparedStatement stmt = conn.prepareStatement("DELETE FROM sessions")) {
      stmt.executeUpdate();
    }
    log.info("已清理旧 index 数据（sessions + session_artifacts）");
  }
}
