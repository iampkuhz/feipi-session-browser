package com.feipi.session.browser.cli;

import com.feipi.session.browser.index.store.sqlite.repository.TokenAuditQuery;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.sql.Connection;
import java.sql.SQLException;

/** 仅在显式请求时为已发布扫描落盘一份本机 TSV。 */
final class ScanTokenAudit {
  private static final String HEADER =
      "agent\tsessionRef\tidHint\tfreshInput\tcacheRead\tcacheWrite\toutput"
          + "\tcontainsUnknown\tcontainsUnavailable\treasonCodes";

  private ScanTokenAudit() {}

  static void write(Connection connection, RuntimePaths paths, String agent, long scanLogId)
      throws IOException, SQLException {
    String filename = "token-audit-" + scanLogId + ".tsv";
    Path target = paths.dataDir().resolve(filename);
    Path temp =
        Files.createTempFile(
            paths.dataDir(),
            ".token-audit-",
            ".tmp",
            PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));
    try {
      long count;
      try (var writer = Files.newBufferedWriter(temp)) {
        writer.write(HEADER);
        writer.newLine();
        count =
            TokenAuditQuery.writeRows(
                connection,
                paths.artifactDir(),
                agent,
                row -> {
                  writer.write(row);
                  writer.newLine();
                });
      }
      Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
      System.out.printf(
          "TOKEN_AUDIT scanLogId=%d affectedSessions=%d report=%s%n", scanLogId, count, filename);
    } finally {
      Files.deleteIfExists(temp);
    }
  }
}
