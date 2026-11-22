package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceReadingEvidence;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexForkReadingEvidenceTest {
  private static final String PARENT = "00000000-0000-0000-0000-000000000001";
  private static final String CHILD = "00000000-0000-0000-0000-000000000002";
  private static final ObjectMapper JSON = new ObjectMapper();

  @TempDir Path folder;

  @Test
  void usesOnlyExactPrefixAndResetsHistoryAtReplacement() throws Exception {
    var sources = Files.createDirectories(folder.toRealPath().resolve("sessions/2021/01/01"));
    var parent = sources.resolve("rollout-" + PARENT + ".jsonl");
    var child = Files.createFile(sources.resolve("rollout-" + CHILD + ".jsonl"));
    String prefix =
        """
        {"ordinal":0,"type":"session_meta","payload":{"id":"%s"}}
        {"ordinal":1,"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"expired contents"}]}}
        {"ordinal":2,"type":"compacted","payload":{"replacement_history":[{"type":"message","role":"developer","content":[{"type":"input_text","text":"same base"},{"type":"input_text","text":"abcdefgh"}]}]}}
        {"ordinal":3,"type":"response_item","payload":{"type":"custom_tool_call_output","output":[{"type":"input_text","text":"abcdefgh"},{"type":"input_image","image_url":"ignored"}]}}
        """
            .formatted(PARENT);
    Files.writeString(parent, prefix + "future is not even JSON\n");
    int exact = prefix.getBytes(StandardCharsets.UTF_8).length;
    assertThat(CodexForkReadingEvidence.read(child, metadata(4, exact), null))
        .containsExactly(
            new SourceReadingEvidence("fork_instructions", "1:8:2"),
            new SourceReadingEvidence("fork_tool_result", "1:8:2"));
    assertThat(CodexForkReadingEvidence.read(child, metadata(4, exact - 1), null)).isEmpty();
    assertThat(CodexForkReadingEvidence.read(child, metadata(3, exact), null)).isEmpty();
    assertThat(CodexForkReadingEvidence.read(child, metadata(4, exact), () -> true)).isEmpty();
  }

  @Test
  void rejectsLinkedRolloutsOutsideTheVerifiedTree() throws Exception {
    var root = folder.toRealPath();
    var sources = Files.createDirectories(root.resolve("sessions/2021/01/01"));
    var outside = Files.createFile(root.resolve("outside.jsonl"));
    var child = Files.createFile(sources.resolve("rollout-" + CHILD + ".jsonl"));
    Files.createSymbolicLink(sources.resolve("rollout-" + PARENT + ".jsonl"), outside);
    assertThat(CodexForkReadingEvidence.read(child, metadata(4, 100), null)).isEmpty();
  }

  private static com.fasterxml.jackson.databind.JsonNode metadata(int ordinal, int offset)
      throws Exception {
    return JSON.readTree(
        """
        {"ordinal":%d,"type":"session_meta","payload":{"id":"%s","forked_from_id":"%s",
        "base_instructions":{"text":"same base"},"attached_thread":true,"history_mode":"paginated",
        "forked_from_ordinal_exclusive":%d,"history_base":{"thread_id":"%s","end_ordinal_exclusive":%d,"end_byte_offset":%d}}}
        """
            .formatted(ordinal, CHILD, PARENT, ordinal, PARENT, ordinal, offset));
  }
}
