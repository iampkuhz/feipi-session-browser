package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 只为当前事实页识别明确 prompt/message 字段；不将整包 JSON 当任务摘要。 */
final class CollaborationTaskPreview {
  private static final ObjectMapper JSON = new ObjectMapper();
  private final Set<String> selected;
  private final Set<String> inputIds;
  private final Map<String, String> previews = new java.util.HashMap<>();
  private int remaining = 262_144;

  CollaborationTaskPreview(Set<String> selected) {
    this(selected, Set.of());
  }

  CollaborationTaskPreview(Set<String> selected, Set<String> inputIds) {
    this.selected = selected;
    this.inputIds = inputIds;
  }

  void observe(Object value) {
    visit(value, 0, new int[] {1024});
  }

  private void visit(Object value, int depth, int[] nodes) {
    if (depth > 8 || nodes[0]-- <= 0 || !(value instanceof Map<?, ?> map)) return;
    String id = String.valueOf(map.get("call_id"));
    if ("null".equals(id)) id = String.valueOf(map.get("id"));
    if (selected.contains(id) && !previews.containsKey(id)) {
      Object input = map.containsKey("input") ? map.get("input") : map.get("arguments");
      if (input instanceof String text && text.length() <= 65_536 && text.length() <= remaining) {
        remaining -= text.length();
        try {
          input = JSON.readValue(text, Object.class);
        } catch (java.io.IOException ignored) {
          input = null;
        }
      }
      if (input instanceof Map<?, ?> fields) {
        if (inputIds.contains(id)) {
          if (fields.get("message") instanceof String message) save(id, message);
          else if (fields.get("items") instanceof List<?> items) {
            for (var item : items) {
              if (nodes[0]-- <= 0) break;
              if (item instanceof Map<?, ?> block
                  && "text".equals(block.get("type"))
                  && block.get("text") instanceof String text) {
                save(id, text);
                if (previews.containsKey(id)) break;
              }
            }
          }
          return;
        }
        for (String field : List.of("prompt", "message", "description")) {
          if (fields.get(field) instanceof String text) {
            save(id, text);
            if (previews.containsKey(id)) break;
          }
        }
      }
    }
    if (map.get("content") instanceof List<?> blocks) {
      for (var block : blocks) {
        if (nodes[0] <= 0) break;
        visit(block, depth + 1, nodes);
      }
    }
  }

  private void save(String id, String text) {
    if (text.isBlank() || text.length() > 65_536 || text.length() > remaining) return;
    remaining -= text.length();
    String safe = SensitiveFieldPolicy.DEFAULT.applyMasking(text);
    previews.put(id, safe.substring(0, Math.min(180, safe.length())));
  }

  String get(String id) {
    return previews.getOrDefault(
        id, inputIds.contains(id) ? "追加内容摘要未安全解析；按需查看追加输入 Input 原文" : "任务摘要未安全解析；按需查看任务 Input 原文");
  }
}
