package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedCollaborationAction;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/** 只持紧凑键和事实；任务/结果正文仍由原 source catalog 提供。 */
final class CollaborationActions {
  private final Map<String, List<Entry>> entries = new HashMap<>();

  void accept(SourceRecord record) {
    record.collaboration().forEach(fact -> accept(fact, record.locator()));
  }

  void accept(
      com.feipi.session.browser.domain.source.SourceCollaborationEvidence fact, String locator) {
    var values = entries.computeIfAbsent(fact.toolCallId(), ignored -> new ArrayList<>());
    if (values.size() < 255)
      values.add(new Entry(fact, fact.sourceLocator().isEmpty() ? locator : fact.sourceLocator()));
    else if (values.size() == 255)
      values.add(
          new Entry(
              new com.feipi.session.browser.domain.source.SourceCollaborationEvidence(
                  fact.toolCallId(),
                  fact.kind(),
                  fact.phase(),
                  Optional.empty(),
                  Optional.empty(),
                  "facts_truncated"),
              locator));
  }

  NormalizedToolExecution apply(NormalizedToolExecution tool, Optional<String> actor) {
    var facts =
        entries.getOrDefault(tool.toolCallId(), List.of()).stream()
            .map(
                entry -> {
                  var fact = entry.fact();
                  return new NormalizedCollaborationAction(
                      fact.kind(),
                      fact.phase(),
                      actor.filter(id -> !id.startsWith("unknown-sidechain:")),
                      fact.targetId(),
                      entry.locator(),
                      fact.reportedStatus(),
                      fact.reason(),
                      actor.filter(id -> id.startsWith("unknown-sidechain:")).isPresent()
                          ? "anonymous_sidechain"
                          : actor.isPresent()
                              ? "explicit_instance"
                              : tool.scope()
                                      == com.feipi.session.browser.domain.enums.CallScope.MAIN
                                  ? "main_context"
                                  : "actor_unknown");
                })
            .toList();
    return tool.withCollaboration(facts);
  }

  /**
   * 一条紧凑源事实及原点。
   *
   * @param fact 明确协议事实
   * @param locator 原始记录定位符
   */
  private record Entry(
      com.feipi.session.browser.domain.source.SourceCollaborationEvidence fact, String locator) {}
}
