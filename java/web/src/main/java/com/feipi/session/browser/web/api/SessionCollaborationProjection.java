package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import io.javalin.http.BadRequestResponse;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 冻结内容的协作事实投影；只保留紧凑身份，不缓存全量任务、结果或关系列表。 */
final class SessionCollaborationProjection {
  private SessionCollaborationProjection() {}

  static String context(NormalizedCall call) {
    return SessionContextLabels.context(call);
  }

  static boolean matches(NormalizedCall call, String agent) {
    return agent.isEmpty() || agent.equals(context(call));
  }

  static Page read(
      NormalizedSessionContent content,
      String scope,
      String cursor,
      int limit,
      String selection,
      String view)
      throws IOException {
    return read(content, scope, cursor, limit, selection, view, new EvidenceWindow(scope, ""));
  }

  static Page read(
      NormalizedSessionContent content,
      String scope,
      String cursor,
      int limit,
      String selection,
      String view,
      EvidenceWindow evidence)
      throws IOException {
    long offset = cursor == null ? 0 : SessionContentCursor.decode(cursor, scope);
    var calls = new LinkedHashMap<String, Origin>();
    var actors = new LinkedHashMap<String, Participant>();
    var labels = new SessionContextLabels();
    var parents = new LinkedHashMap<String, Set<String>>();
    var childTools = new LinkedHashMap<String, Set<String>>();
    var reasons = new LinkedHashMap<String, Long>();
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        for (var call : unit.calls()) {
          String key = context(call);
          actors.putIfAbsent(
              key, new Participant(key, labels.register(call), call.subagentId().orElse(""), true));
          call.parentToolCallId().ifPresent(tool -> addChild(childTools, tool, key));
          calls.put(
              call.callId(), new Origin(key, call.callIndex(), call.parentToolCallId().orElse("")));
        }
        for (var diagnostic : unit.diagnostics()) {
          String code =
              String.valueOf(diagnostic.getOrDefault("code", diagnostic.getOrDefault("type", "")));
          if (code.startsWith("SUBAGENT_")) reasons.merge(code, 1L, Long::sum);
        }
      }
    }
    // 第一遍工具只累计完整总数、参与者和至多两个不同父节点；不持有每条 action。
    long delegates = 0;
    long exchanges = 0;
    long inputs = 0;
    long errors = 0;
    Long firstError = null;
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var tool : reader.next().toolExecutions()) {
          var origin = calls.get(tool.declaredByCallId());
          String actor =
              SessionContextLabels.executionContext(tool, origin == null ? null : origin.actor());
          if (actor.isEmpty()) actor = "unknown:" + tool.declaredByCallId();
          if (origin != null || !tool.collaboration().isEmpty())
            actors.putIfAbsent(actor, new Participant(actor, labels.register(actor), "", false));
          for (var action : tool.collaboration()) {
            String target =
                target(
                    action.targetId(),
                    tool.toolCallId(),
                    "delegate".equals(action.kind()) ? childTools : Map.of());
            if (!target.isEmpty() && !"input".equals(action.kind()))
              actors.putIfAbsent(
                  target,
                  new Participant(
                      target, labels.register(target), action.targetId().orElse(""), false));
            reasons.merge(action.reason(), 1L, Long::sum);
            if (declaration(action.kind(), action.phase())) {
              delegates++;
              if (!target.isEmpty()) {
                var set = parents.computeIfAbsent(target, key -> new LinkedHashSet<>());
                if (set.size() < 2) set.add(actor);
              }
            }
            if ("input".equals(action.kind()) && "declaration".equals(action.phase())) inputs++;
            if ("input".equals(action.kind())
                && "result_report".equals(action.phase())
                && "explicit_error".equals(action.reason())) {
              if (firstError == null) firstError = exchanges;
              errors++;
            }
            exchanges++;
          }
        }
      }
    }
    // 原调用与协作目标前缀登记完毕后，仅线性读取工具元数据，升级或追加有证过程。
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var tool : reader.next().toolExecutions()) {
          var origin = calls.get(tool.declaredByCallId());
          String key =
              SessionContextLabels.executionContext(tool, origin == null ? null : origin.actor());
          if (key.isEmpty()) continue;
          var previous = actors.get(key);
          actors.put(
              key,
              new Participant(
                  key,
                  previous == null ? labels.register(key) : previous.label(),
                  previous == null
                      ? tool.subagentId().filter(id -> key.startsWith("subagent:")).orElse("")
                      : previous.id(),
                  true));
        }
      }
    }
    if (!selection.isEmpty() && !actors.containsKey(selection))
      throw new BadRequestResponse("collaboration participant not found in this scope");
    var items = new ArrayList<Map<String, Object>>();
    long total = 0;
    if ("participants".equals(view)) {
      for (var participant : actors.values()) {
        if (total >= offset && items.size() < limit) items.add(participantRow(participant));
        total++;
      }
    } else {
      boolean overview = selection.isEmpty() && "delegations".equals(view);
      for (int pass = 0; pass < (overview ? 2 : 1); pass++) {
        try (var reader = content.openCursor()) {
          while (reader.hasNext()) {
            for (var tool : reader.next().toolExecutions()) {
              var origin = calls.get(tool.declaredByCallId());
              String actor =
                  SessionContextLabels.executionContext(
                      tool, origin == null ? null : origin.actor());
              if (actor.isEmpty()) actor = "unknown:" + tool.declaredByCallId();
              for (var action : tool.collaboration()) {
                boolean delegate = declaration(action.kind(), action.phase());
                String target =
                    target(
                        action.targetId(),
                        tool.toolCallId(),
                        "delegate".equals(action.kind()) ? childTools : Map.of());
                if ("delegations".equals(view) && !delegate) continue;
                boolean included = actors.containsKey(target) && actors.get(target).included();
                if (overview && (pass == 0) != included) continue;
                if (!selection.isEmpty()
                    && !("delegations".equals(view)
                        ? selection.equals(actor)
                        : selection.equals(actor) || selection.equals(target))) continue;
                // 默认两层；更深支路通过完整参与者选择进入，不无限缩进。
                if (selection.isEmpty() && "delegations".equals(view) && depth(actor, parents) > 1)
                  continue;
                if (total >= offset && items.size() < limit) {
                  Map<String, Object> row = new LinkedHashMap<>();
                  row.put("actor", actor);
                  row.put("target", target);
                  row.put("actorLabel", actors.get(actor).label());
                  row.put(
                      "targetLabel",
                      target.isEmpty()
                          ? "目标身份未确认"
                          : actors.containsKey(target) ? actors.get(target).label() : "未采集目标");
                  row.put("kind", action.kind());
                  row.put("phase", action.phase());
                  row.put("toolId", tool.toolCallId());
                  row.put("toolName", tool.name());
                  row.put("callId", tool.declaredByCallId());
                  row.put("callIndex", origin == null ? 0 : origin.index());
                  row.put("sourceLocator", action.sourceLocator());
                  row.put(
                      "reason",
                      action.targetId().isEmpty() && !target.isEmpty()
                          ? "explicit_parent_tool"
                          : action.reason());
                  row.put("actorIdentityReason", action.actorIdentityReason());
                  row.put("reportedStatus", action.reportedStatus().orElse(""));
                  row.put("consumer", tool.resultConsumedByCallId().orElse(""));
                  row.put("childIncluded", included);
                  row.put(
                      "parentIssue",
                      parents.getOrDefault(target, Set.of()).size() > 1
                          ? "multiple_parents"
                          : depth(actor, parents) < 0 ? "cycle_or_unknown_parent" : "");
                  row.put("depth", depth(actor, parents));
                  row.put("task", "任务摘要未安全解析；按需查看任务 Input 原文");
                  items.add(row);
                }
                total++;
              }
            }
          }
        }
      }
    }
    if (!"participants".equals(view)) enrich(content, items, calls, childTools);
    if (!evidence.marker().isEmpty()) qualifyPayloads(content, items, calls);
    if (offset > total) throw new BadRequestResponse("cursor exceeds collaboration total");
    long end = offset + items.size();
    return new Page(
        ApiResponses.SCHEMA_VERSION,
        List.copyOf(items),
        total,
        offset,
        end < total ? SessionContentCursor.encode(scope, end) : null,
        actors.values().stream()
            .limit(5)
            .map(SessionCollaborationProjection::participantRow)
            .toList(),
        actors.size(),
        delegates,
        exchanges,
        inputs,
        errors,
        firstError == null
            ? null
            : new InputSubmissionError(
                SessionContentCursor.encode(evidence.scope(), firstError), firstError),
        evidence.marker(),
        Map.copyOf(reasons),
        selection,
        view);
  }

  private static void enrich(
      NormalizedSessionContent content,
      List<Map<String, Object>> items,
      Map<String, Origin> calls,
      Map<String, Set<String>> childTools)
      throws IOException {
    var ids = new java.util.HashSet<String>();
    var targets = new java.util.HashSet<String>();
    var inputIds = new java.util.HashSet<String>();
    for (var item : items) {
      ids.add((String) item.get("toolId"));
      if ("input".equals(item.get("kind"))) inputIds.add((String) item.get("toolId"));
      else targets.add((String) item.get("target"));
    }
    var previews = new CollaborationTaskPreview(ids, inputIds);
    var reports = new java.util.HashMap<String, List<Map<String, Object>>>();
    var counts = new java.util.HashMap<String, Long>();
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        for (var call : unit.calls()) {
          if (call.response().toolCallIds().stream().anyMatch(ids::contains)) {
            for (var source : call.sourceUnits()) previews.observe(source);
          }
        }
        for (var entry : unit.sourceUnitCatalog().values()) {
          if ("response".equals(entry.direction().getValue())) previews.observe(entry.payload());
        }
        for (var tool : unit.toolExecutions()) {
          for (var action : tool.collaboration()) {
            String target =
                target(
                    action.targetId(),
                    tool.toolCallId(),
                    "delegate".equals(action.kind()) ? childTools : Map.of());
            if ("input".equals(action.kind())
                || !targets.contains(target)
                || declaration(action.kind(), action.phase())) continue;
            counts.merge(target, 1L, Long::sum);
            var list = reports.computeIfAbsent(target, key -> new ArrayList<>());
            if (list.size() < 3) {
              var origin = calls.get(tool.declaredByCallId());
              list.add(
                  Map.of(
                      "toolId",
                      tool.toolCallId(),
                      "callId",
                      tool.declaredByCallId(),
                      "callIndex",
                      origin == null ? 0 : origin.index(),
                      "kind",
                      action.kind(),
                      "phase",
                      action.phase(),
                      "reportedStatus",
                      action.reportedStatus().orElse("")));
            }
          }
        }
      }
    }
    for (var item : items) {
      item.put("task", previews.get((String) item.get("toolId")));
      item.put(
          "reports",
          "input".equals(item.get("kind"))
              ? List.of()
              : reports.getOrDefault(item.get("target"), List.of()));
      item.put(
          "reportTotal",
          "input".equals(item.get("kind")) ? 0L : counts.getOrDefault(item.get("target"), 0L));
    }
  }

  /** 固定本页及报告候选后，仅追加一次完整元数据核验，不读取正文。 */
  private static void qualifyPayloads(
      NormalizedSessionContent content,
      List<Map<String, Object>> items,
      Map<String, Origin> origins)
      throws IOException {
    var rows = new ArrayList<Map<String, Object>>();
    for (var item : items) {
      rows.add(item);
      Object reports = item.get("reports");
      if (reports instanceof List<?> list) {
        var copies = new ArrayList<Map<String, Object>>();
        for (Object report : list) {
          if (report instanceof Map<?, ?> map) {
            var copy = new LinkedHashMap<String, Object>();
            map.forEach((key, value) -> copy.put((String) key, value));
            copies.add(copy);
            rows.add(copy);
          }
        }
        item.put("reports", copies);
      }
    }
    var candidates = new LinkedHashMap<String, PayloadClaim>();
    for (var row : rows)
      candidates
          .computeIfAbsent((String) row.get("toolId"), ignored -> new PayloadClaim())
          .calls
          .putIfAbsent((String) row.get("callId"), 0);
    long calls = 0;
    long tools = 0;
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        calls += unit.calls().size();
        tools += unit.toolExecutions().size();
        for (var call : unit.calls()) {
          for (var claim : candidates.values())
            claim.calls.computeIfPresent(call.callId(), (id, count) -> Math.min(2, count + 1));
          for (String id : call.response().toolCallIds()) {
            var claim = candidates.get(id);
            if (claim != null) {
              claim.declarations = Math.min(2, claim.declarations + 1);
              claim.declaringCall = call.callId();
            }
          }
        }
        for (var tool : unit.toolExecutions()) {
          var claim = candidates.get(tool.toolCallId());
          if (claim != null) {
            claim.tools = Math.min(2, claim.tools + 1);
            claim.owner = tool.declaredByCallId();
            var origin = origins.get(claim.owner);
            String toolActor = SessionContextLabels.executionContext(tool, null);
            if (origin != null && !toolActor.isEmpty() && !origin.actor().equals(toolActor))
              claim.conflict = true;
          }
        }
      }
    }
    boolean complete =
        calls == content.header().totals().getOrDefault("calls", -1L)
            && tools == content.header().totals().getOrDefault("toolExecutions", -1L);
    for (var row : rows) {
      var claim = candidates.get(row.get("toolId"));
      boolean conflict =
          claim.conflict
              || claim.tools > 1
              || claim.declarations > 1
              || claim.calls.values().stream().anyMatch(count -> count > 1)
              || (claim.declarations == 1 && !claim.declaringCall.equals(claim.owner))
              || !row.get("callId").equals(claim.owner);
      row.put(
          "toolPayloadState",
          conflict ? "ambiguous" : complete && claim.tools == 1 ? "unique" : "unconfirmed");
    }
  }

  /** 仅保留当前有界工具候选的饱和身份计数。 */
  private static final class PayloadClaim {
    private long tools;
    private long declarations;
    private final Map<String, Integer> calls = new LinkedHashMap<>();
    private boolean conflict;
    private String owner = "";
    private String declaringCall = "";
  }

  /**
   * 当前证据窗口及其绑定的完整查询范围。
   *
   * @param scope 绑定冻结内容及 canonical 查询条件的游标范围
   * @param marker 显式保护窗口标记，普通窗口为空
   */
  record EvidenceWindow(String scope, String marker) {}

  /**
   * 全冻结首个明确提交错误的事实位置，不携带原文。
   *
   * @param cursor 绑定 canonical 证据窗口的事实游标
   * @param exchangeOffset 首个明确提交错误在完整往来事实中的偏移
   */
  record InputSubmissionError(String cursor, long exchangeOffset) {}

  private static void addChild(Map<String, Set<String>> children, String tool, String key) {
    var candidates = children.computeIfAbsent(tool, unused -> new LinkedHashSet<>());
    if (candidates.size() < 2) candidates.add(key);
  }

  private static String target(
      java.util.Optional<String> explicit, String tool, Map<String, Set<String>> childTools) {
    if (explicit.isPresent()) return "subagent:" + explicit.get();
    var candidates = childTools.getOrDefault(tool, Set.of());
    return candidates.size() == 1 ? candidates.iterator().next() : "";
  }

  private static boolean declaration(String kind, String phase) {
    return "delegate".equals(kind) && "declaration".equals(phase);
  }

  private static int depth(String actor, Map<String, Set<String>> parents) {
    int depth = 0;
    var visited = new java.util.HashSet<String>();
    while (!"main".equals(actor)) {
      if (!visited.add(actor) || depth > 128) return -1;
      var parent = parents.getOrDefault(actor, Set.of());
      if (parent.size() != 1) return -1;
      actor = parent.iterator().next();
      depth++;
    }
    return depth;
  }

  private static Map<String, Object> participantRow(Participant participant) {
    return Map.of(
        "key",
        participant.key(),
        "label",
        participant.label(),
        "id",
        participant.id(),
        "included",
        participant.included());
  }

  /**
   * 当前请求的有界事实窗口，完整计数不依赖分页。
   *
   * @param schemaVersion API 版本
   * @param items 当前页委派、往来或参与者
   * @param total 当前选择的完整条数
   * @param offset 当前页起点
   * @param nextCursor 绑定快照与选择的续页游标
   * @param participants 默认至多五个参与者
   * @param participantTotal 全范围参与者总数
   * @param delegationTotal 全范围委派总数，含深层
   * @param exchangeTotal 全范围事实总数
   * @param inputDeclarationTotal 全冻结范围追加输入声明数，不表示送达
   * @param inputSubmissionErrorReportTotal 全冻结明确追加输入提交错误事实数
   * @param firstInputSubmissionError 首个错误的 canonical 事实窗口
   * @param evidenceWindow 当前显式保护窗口标记，普通页为空
   * @param reasons 原始关联原因及采集诊断计数
   * @param selection 当前完整上下文
   * @param view 当前事实类型
   */
  record Page(
      String schemaVersion,
      List<Map<String, Object>> items,
      long total,
      long offset,
      String nextCursor,
      List<Map<String, Object>> participants,
      long participantTotal,
      long delegationTotal,
      long exchangeTotal,
      long inputDeclarationTotal,
      long inputSubmissionErrorReportTotal,
      InputSubmissionError firstInputSubmissionError,
      String evidenceWindow,
      Map<String, Long> reasons,
      String selection,
      String view) {}

  /**
   * 仅用于声明上下文连接，不持有调用正文。
   *
   * @param actor 完整上下文键
   * @param index 本地响应序号
   * @param parentTool 已确认父工具身份
   */
  private record Origin(String actor, int index, String parentTool) {}

  /**
   * 实例存在性与可读编号，不把候选来源当已采集。
   *
   * @param key 完整上下文键
   * @param label 页面编号
   * @param id 原始实例标识
   * @param included 冻结内容中是否有此上下文
   */
  private record Participant(String key, String label, String id, boolean included) {}
}
