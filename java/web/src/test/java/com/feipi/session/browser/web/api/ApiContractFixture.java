package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;

/** 资源 API 测试共享的确定性契约 fixture。 */
final class ApiContractFixture {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  static final ExpectedTotals ALL = new ExpectedTotals(3, 2, 2100, 900, 100, 950, 4050, 3);
  static final ExpectedTotals CLAUDE_CODE = new ExpectedTotals(2, 1, 1500, 900, 100, 750, 3250, 3);
  static final ExpectedTotals FAILED = CLAUDE_CODE;
  static final ExpectedTotals BETA = new ExpectedTotals(1, 1, 600, 0, 0, 200, 800, 0);

  private ApiContractFixture() {}

  static void insertThreeSessionFixture(IndexConnection connection) throws SQLException {
    insert(
        connection,
        "claude_code:s-alpha-001",
        "claude_code",
        "s-alpha-001",
        "Alpha refactor dashboard",
        "/repo/alpha",
        "alpha",
        "/repo/alpha",
        "claude-sonnet-4.5",
        "2026-06-01T10:00:00Z",
        "2026-06-01T10:10:00Z",
        600,
        120,
        2,
        2,
        4,
        1,
        1,
        1000,
        400,
        100,
        500);
    insert(
        connection,
        "codex:s-beta-001",
        "codex",
        "s-beta-001",
        "Codex cleanup",
        "/repo/beta",
        "beta",
        "/repo/beta",
        "gpt-5.4",
        "2026-06-01T11:00:00Z",
        "2026-06-01T11:05:00Z",
        300,
        90,
        1,
        1,
        1,
        0,
        0,
        600,
        0,
        0,
        200);
    insert(
        connection,
        "claude_code:s-alpha-002",
        "claude_code",
        "s-alpha-002",
        "Alpha fix failing tools",
        "/repo/alpha",
        "alpha",
        "/repo/alpha",
        "claude-sonnet-4.5",
        "2026-06-02T09:00:00Z",
        "2026-06-02T09:08:00Z",
        480,
        80,
        1,
        1,
        2,
        2,
        0,
        500,
        500,
        0,
        250);
  }

  static void insertNormalizedArtifactForAlpha(IndexConnection connection, Path tempDir)
      throws Exception {
    Path artifactPath = tempDir.resolve("alpha-001.normalized.json");
    Map<String, Object> artifact =
        Map.of(
            "schema_version",
            NormalizedConstants.SCHEMA_VERSION,
            "agent",
            "claude_code",
            "session",
            Map.of("session_key", "claude_code:s-alpha-001", "session_id", "s-alpha-001"),
            "calls",
            List.of(
                Map.of(
                    "call_id",
                    "alpha-call-1",
                    "call_index",
                    1,
                    "call_key",
                    "C1",
                    "scope",
                    "main",
                    "turn_id",
                    "turn-alpha-1",
                    "model",
                    "claude-sonnet-4.5",
                    "usage",
                    Map.of(
                        "fresh",
                        1000,
                        "cache_read",
                        400,
                        "cache_write",
                        100,
                        "output",
                        500,
                        "total",
                        2000),
                    "request",
                    Map.of("tool_result_ids", List.of()),
                    "response",
                    Map.of("tool_call_ids", List.of("tool-call-1"))),
                Map.ofEntries(
                    Map.entry("call_id", "alpha-sub-call-1"),
                    Map.entry("call_index", 2),
                    Map.entry("call_key", "C2"),
                    Map.entry("scope", "subagent"),
                    Map.entry("parent_call_id", "alpha-call-1"),
                    Map.entry("parent_tool_call_id", "tool-call-1"),
                    Map.entry("subagent_id", "sa-alpha"),
                    Map.entry("parent_tool_name", "Agent"),
                    Map.entry("turn_id", "turn-alpha-sub-1"),
                    Map.entry("model", "claude-sonnet-4.5"),
                    Map.entry(
                        "usage",
                        Map.of(
                            "fresh",
                            100,
                            "cache_read",
                            0,
                            "cache_write",
                            0,
                            "output",
                            10,
                            "total",
                            110)),
                    Map.entry("request", Map.of("tool_result_ids", List.of("sub-tool-1"))),
                    Map.entry("response", Map.of("tool_call_ids", List.of())))),
            "tool_executions",
            List.of(
                Map.of(
                    "tool_call_id",
                    "tool-call-1",
                    "name",
                    "exec_command",
                    "scope",
                    "main",
                    "declared_by_call_id",
                    "alpha-call-1",
                    "status",
                    "error: exit 1",
                    "duration_ms",
                    120),
                Map.of(
                    "tool_call_id",
                    "sub-tool-1",
                    "name",
                    "Read",
                    "scope",
                    "subagent",
                    "declared_by_call_id",
                    "alpha-sub-call-1",
                    "duration_ms",
                    80,
                    "subagent_id",
                    "sa-alpha")));
    MAPPER.writeValue(artifactPath.toFile(), artifact);
    String sql =
        "INSERT INTO session_artifacts"
            + " (session_key, artifact_type, path, schema_version, source_path,"
            + " source_mtime, size_bytes, created_at, updated_at)"
            + " VALUES (?, 'normalized', ?, ?, '/tmp/s-alpha-001.jsonl', 1, ?, 1, 1)";
    try (PreparedStatement ps = connection.writerConnection().prepareStatement(sql)) {
      ps.setString(1, "claude_code:s-alpha-001");
      ps.setString(2, artifactPath.toString());
      ps.setString(3, NormalizedConstants.SCHEMA_VERSION);
      ps.setLong(4, Files.size(artifactPath));
      ps.executeUpdate();
    }
  }

  private static void insert(
      IndexConnection connection,
      String sessionKey,
      String agent,
      String sessionId,
      String title,
      String projectKey,
      String projectName,
      String cwd,
      String model,
      String startedAt,
      String endedAt,
      double durationSeconds,
      double processSeconds,
      long userMessages,
      long assistantMessages,
      long toolCalls,
      long failedTools,
      long subagents,
      long fresh,
      long cacheRead,
      long cacheWrite,
      long output)
      throws SQLException {
    String sql =
        "INSERT INTO sessions"
            + " (session_key, agent, session_id, title, project_key, project_name, cwd,"
            + " started_at, ended_at, duration_seconds, model_execution_seconds,"
            + " tool_execution_seconds, model, git_branch, source,"
            + " user_message_count, assistant_message_count, tool_call_count,"
            + " output_tokens, fresh_input_tokens, cache_read_tokens, cache_write_tokens,"
            + " total_tokens, failed_tool_count, subagent_instance_count,"
            + " indexed_at, file_mtime, file_path)"
            + " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'main', 'fixture',"
            + " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)";
    try (PreparedStatement ps = connection.writerConnection().prepareStatement(sql)) {
      int i = 1;
      ps.setString(i++, sessionKey);
      ps.setString(i++, agent);
      ps.setString(i++, sessionId);
      ps.setString(i++, title);
      ps.setString(i++, projectKey);
      ps.setString(i++, projectName);
      ps.setString(i++, cwd);
      ps.setString(i++, startedAt);
      ps.setString(i++, endedAt);
      ps.setDouble(i++, durationSeconds);
      ps.setDouble(i++, processSeconds);
      ps.setString(i++, model);
      ps.setLong(i++, userMessages);
      ps.setLong(i++, assistantMessages);
      ps.setLong(i++, toolCalls);
      ps.setLong(i++, output);
      ps.setLong(i++, fresh);
      ps.setLong(i++, cacheRead);
      ps.setLong(i++, cacheWrite);
      ps.setLong(i++, fresh + cacheRead + cacheWrite + output);
      ps.setLong(i++, failedTools);
      ps.setLong(i++, subagents);
      ps.setString(i, "/tmp/" + sessionId + ".jsonl");
      ps.executeUpdate();
    }
  }

  record ExpectedTotals(
      long sessions,
      long projects,
      long fresh,
      long cacheRead,
      long cacheWrite,
      long output,
      long total,
      long failedTools) {}
}
