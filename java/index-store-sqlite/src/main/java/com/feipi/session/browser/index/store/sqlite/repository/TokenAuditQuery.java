package com.feipi.session.browser.index.store.sqlite.repository;

import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.mapper.TokenProvenanceSqlMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.HexFormat;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;

/** 从已发布索引读取计量缺口；只向调用方交付脱敏字段。 */
public final class TokenAuditQuery {
  private static final Set<String> USAGE_CODES =
      Set.of("TOKEN_COUNTER_RESET", "TOKEN_USAGE_AMBIGUOUS", "TOKEN_NO_CUMULATIVE");
  private static final Pattern UUID_PATTERN =
      Pattern.compile("[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}");

  private TokenAuditQuery() {}

  /**
   * 扫描已发布索引范围内含未上报或来源未知的行。
   *
   * @param connection 已打开的扫描连接
   * @param artifactDir 允许读取的归一化制品目录
   * @param agent 指定来源，空字符串表示全部
   * @param sink 接收 TSV 行的回调
   * @return 写出的会话数
   * @throws SQLException 查询失败
   * @throws IOException 报告写入失败
   */
  public static long writeRows(Connection connection, Path artifactDir, String agent, Sink sink)
      throws SQLException, IOException {
    String sql =
        "SELECT s.session_key, s.session_id, s.agent, a.path, "
            + TokenProvenanceSqlMapper.COLUMNS
            + " FROM sessions s LEFT JOIN session_artifacts a"
            + " ON a.session_key = s.session_key AND a.artifact_type = 'normalized'"
            + " WHERE (token_contains_unknown = 1 OR token_contains_unavailable = 1)"
            + " AND (? = '' OR s.agent = ?) ORDER BY s.agent, s.session_key";
    Path root = artifactDir.toRealPath();
    long count = 0;
    try (var query = connection.prepareStatement(sql)) {
      query.setString(1, agent);
      query.setString(2, agent);
      try (var rows = query.executeQuery()) {
        while (rows.next()) {
          var precision = TokenProvenanceSqlMapper.read(rows);
          sink.write(
              String.join(
                  "\t",
                  safeAgent(rows.getString("agent")),
                  reference(rows.getString("session_key")),
                  idHint(rows.getString("session_id")),
                  precision.freshInput(),
                  precision.cacheRead(),
                  precision.cacheWrite(),
                  precision.output(),
                  Boolean.toString(precision.unknownSessionCount() > 0),
                  Boolean.toString(precision.unavailableSessionCount() > 0),
                  reasons(precision, root, rows.getString("path"))));
          count++;
        }
      }
    }
    return count;
  }

  /** 接收不含换行符的 TSV 数据行。 */
  @FunctionalInterface
  public interface Sink {
    /** 写出脱敏数据行；回调负责换行。 */
    void write(String row) throws IOException;
  }

  private static String reasons(TokenProvenance precision, Path root, String artifact) {
    Set<String> codes = new TreeSet<>();
    if (precision.unavailableSessionCount() > 0) codes.add("TOKEN_FIELD_UNAVAILABLE");
    if (precision.unknownSessionCount() > 0) {
      codes.add("TOKEN_PROVENANCE_UNRESOLVED");
      addArtifactCodes(root, artifact, codes);
    }
    return String.join(",", codes);
  }

  private static void addArtifactCodes(Path root, String artifact, Set<String> codes) {
    if (artifact == null || artifact.isBlank()) {
      codes.add("TOKEN_AUDIT_ARTIFACT_UNAVAILABLE");
      return;
    }
    Set<String> found = new TreeSet<>();
    try {
      Path path = Path.of(artifact).toRealPath();
      if (!path.startsWith(root) || !Files.isRegularFile(path)) {
        codes.add("TOKEN_AUDIT_ARTIFACT_UNAVAILABLE");
        return;
      }
      var content = NormalizedArtifactLoader.open(path);
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          for (var diagnostic : cursor.next().diagnostics()) {
            Object code = diagnostic.get("code");
            if (code instanceof String value && USAGE_CODES.contains(value)) found.add(value);
          }
        }
      }
      codes.addAll(found);
    } catch (IOException | RuntimeException e) {
      codes.add("TOKEN_AUDIT_ARTIFACT_UNAVAILABLE");
    }
  }

  private static String safeAgent(String agent) {
    return switch (agent) {
      case "codex", "claude_code", "qoder" -> agent;
      default -> "unknown";
    };
  }

  private static String reference(String sessionKey) {
    try {
      byte[] hash =
          MessageDigest.getInstance("SHA-256").digest(sessionKey.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(hash, 0, 8);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 unavailable", e);
    }
  }

  private static String idHint(String sessionId) {
    return UUID_PATTERN.matcher(sessionId).matches()
        ? "..." + sessionId.substring(sessionId.length() - 8)
        : "-";
  }
}
