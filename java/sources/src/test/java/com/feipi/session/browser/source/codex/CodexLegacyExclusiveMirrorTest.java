package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexLegacyExclusiveMirrorTest {
  @TempDir Path directory;

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
