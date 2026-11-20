package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** 追加输入安全摘要不回退为初始任务或整包结构化内容。 */
class CollaborationTaskPreviewTest {
  @Test
  void messagesAndStructuredTextAreMaskedBoundedAndNonTextStaysUnknown() {
    var preview =
        new CollaborationTaskPreview(
            Set.of("message", "items", "image", "large"),
            Set.of("message", "items", "image", "large"));
    preview.observe(
        Map.of("call_id", "message", "arguments", Map.of("message", "synthetic ".repeat(40))));
    preview.observe(
        Map.of(
            "call_id",
            "items",
            "arguments",
            Map.of(
                "items",
                List.of(
                    Map.of("type", "mention", "name", "drive", "path", "app://google_drive"),
                    Map.of("type", "text", "text", "api_key=synthetic")))));
    preview.observe(
        Map.of(
            "call_id",
            "image",
            "arguments",
            Map.of(
                "prompt",
                "not a task",
                "items",
                List.of(Map.of("type", "image", "image_url", "synthetic://image")))));
    preview.observe(Map.of("call_id", "large", "arguments", Map.of("message", "x".repeat(65_537))));
    assertThat(preview.get("message")).hasSize(180);
    assertThat(preview.get("items")).isEqualTo("api_key=[REDACTED]");
    assertThat(preview.get("image"))
        .startsWith("追加内容摘要未安全解析")
        .doesNotContain("not a task", "synthetic://image");
    assertThat(preview.get("large")).startsWith("追加内容摘要未安全解析");
  }
}
