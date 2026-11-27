package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class CodexLegacyExclusiveMirrorTest {
  @TempDir Path directory;

  @ParameterizedTest
  @ValueSource(strings = {"valid", "bad-cut", "null-cache", "negative-cache", "positive-cache"})
  void attachedForkUsesOnlyTheVerifiedParentCounterOffset(String scenario) throws Exception {
    int boundaryError = "bad-cut".equals(scenario) ? 1 : 0;
    String cache =
        switch (scenario) {
          case "null-cache" -> ",\"cache_write_input_tokens\":null";
          case "negative-cache" -> ",\"cache_write_input_tokens\":-1";
          case "positive-cache" -> ",\"cache_write_input_tokens\":1";
          default -> "";
        };
    boolean unknown = !"valid".equals(scenario);
    String parentId = "00000000-0000-0000-0000-000000000011";
    String childId = "00000000-0000-0000-0000-000000000012";
    var sessions = Files.createDirectories(directory.toRealPath().resolve("sessions"));
    String prefix =
        """
        {"ordinal":0,"type":"session_meta","payload":{"id":"%s"}}
        {"ordinal":1,"type":"token_usage_record","payload":{"usage":{"input_tokens":10,"cached_input_tokens":5,"cache_write_input_tokens":0,"output_tokens":7},"thread_token_usage":{"input_tokens":10,"cached_input_tokens":5,"cache_write_input_tokens":0,"output_tokens":7}}}
        {"ordinal":2,"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":6,"cached_input_tokens":3,"output_tokens":4}}}}
        """
            .formatted(parentId);
    Files.writeString(
        sessions.resolve("rollout-synthetic-" + parentId + ".jsonl"),
        prefix + "outside the exact fork prefix\n");
    Path child = sessions.resolve("rollout-synthetic-" + childId + ".jsonl");
    Files.writeString(
        child,
        """
        {"ordinal":3,"type":"session_meta","payload":{"id":"%s","forked_from_id":"%s","attached_thread":true,"history_mode":"paginated","forked_from_ordinal_exclusive":3,"history_base":{"thread_id":"%s","end_ordinal_exclusive":3,"end_byte_offset":%d}}}
        {"ordinal":4,"type":"token_usage_record","payload":{"response_id":"r1","turn_id":"t1","usage":{"input_tokens":3,"cached_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3},"thread_token_usage":{"input_tokens":13,"cached_input_tokens":7,"cache_write_input_tokens":0,"output_tokens":10}}}
        {"ordinal":5,"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":9,"cached_input_tokens":5,"output_tokens":7},"last_token_usage":{"input_tokens":3,"cached_input_tokens":2,"output_tokens":3%s}}}}
        """
            .formatted(childId, parentId, parentId, prefix.length() + boundaryError, cache));
    var adapter = new CodexSourceAdapter();
    try (var result =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(child), "codex:" + childId, "", Map.of()),
                null)) {
      assertThat(
              result.diagnostics().stream().anyMatch(d -> d.code().equals("TOKEN_USAGE_AMBIGUOUS")))
          .isEqualTo(unknown);
      assertThat(adapter.singleFileMetadata(child))
          .containsEntry("tokenContainsUnknown", Boolean.toString(unknown));
      assertThat(result.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(6);
    }
  }

  @Test
  void completeExclusiveLegacyLastUsageKeepsIncrementalMirrorOwnership() throws Exception {
    Path file = directory.resolve("synthetic-exclusive-mirror.jsonl");
    Files.writeString(
        file,
        """
        {"type":"token_usage_record","payload":{"response_id":"r1","turn_id":"t1","usage":{"input_tokens":3,"cached_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3},"thread_token_usage":{"input_tokens":3,"cached_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3}}}
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":1,"cache_read_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3}}}}
        {"type":"token_usage_record","payload":{"response_id":"r2","turn_id":"t2","usage":{"input_tokens":3,"cached_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3},"thread_token_usage":{"input_tokens":6,"cached_input_tokens":4,"cache_write_input_tokens":0,"output_tokens":6}}}
        {"type":"event_msg","payload":{"type":"task_started","turn_id":"t3"}}
        {"type":"token_usage_record","payload":{"response_id":"r3","turn_id":"t3","usage":{"input_tokens":3,"cached_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3},"thread_token_usage":{"input_tokens":9,"cached_input_tokens":6,"cache_write_input_tokens":0,"output_tokens":9}}}
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":2,"cache_read_input_tokens":4,"cache_write_input_tokens":0,"output_tokens":6},"last_token_usage":{"input_tokens":1,"cache_read_input_tokens":2,"cache_write_input_tokens":0,"output_tokens":3}}}}
        """);
    var adapter = new CodexSourceAdapter();
    try (var result =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "codex:exclusive", "", Map.of()), null)) {
      assertThat(result.diagnostics()).noneMatch(d -> d.code().equals("TOKEN_USAGE_AMBIGUOUS"));
      var records = result.records();
      assertThat(
              records.stream().filter(r -> r.callId().orElse("").startsWith("token_usage_record:")))
          .hasSize(3);
      assertThat(records.stream().mapToLong(r -> r.usage().inputTokens()).sum()).isEqualTo(3);
      assertThat(records.stream().mapToLong(r -> r.usage().cacheReadInputTokens()).sum())
          .isEqualTo(6);
      assertThat(records.stream().mapToLong(r -> r.usage().cacheCreationInputTokens()).sum())
          .isZero();
      assertThat(records.stream().mapToLong(r -> r.usage().outputTokens()).sum()).isEqualTo(9);
      assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(18);
    }
  }
}
