package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link NormalizedArtifactLoader} 兼容性测试。 */
@DisplayName("NormalizedArtifactLoader 测试")
class NormalizedArtifactLoaderTest {

  @Test
  @DisplayName("支持 main/Python-era snake_case 归一化制品字段")
  void supportsSnakeCaseNormalizedArtifact() {
    Map<String, Object> artifact =
        Map.of(
            "schema_version",
            NormalizedConstants.SCHEMA_VERSION,
            "agent",
            "codex",
            "session",
            Map.of("session_key", "codex:s1", "session_id", "s1"),
            "calls",
            List.of(
                Map.of(
                    "call_id",
                    "codex-call-0001",
                    "call_index",
                    1,
                    "call_key",
                    "C1",
                    "scope",
                    "main",
                    "usage",
                    Map.of(
                        "fresh", 10, "cache_read", 20, "cache_write", 5, "output", 7, "total", 42),
                    "request",
                    Map.of("tool_result_ids", List.of("tool-result-1")),
                    "response",
                    Map.of("tool_call_ids", List.of("tool-call-1")))),
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
                    "codex-call-0001",
                    "result_consumed_by_call_id",
                    "codex-call-0001",
                    "duration_ms",
                    15)));

    var result = NormalizedArtifactLoader.fromMap(artifact);

    assertThat(result.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(result.calls()).hasSize(1);
    assertThat(result.calls().get(0).callId()).isEqualTo("codex-call-0001");
    assertThat(result.calls().get(0).usage().cacheRead()).isEqualTo(20);
    assertThat(result.calls().get(0).response().toolCallIds()).containsExactly("tool-call-1");
    assertThat(result.toolExecutions()).hasSize(1);
    assertThat(result.toolExecutions().get(0).toolCallId()).isEqualTo("tool-call-1");
  }
}
