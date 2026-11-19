package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import io.javalin.http.BadRequestResponse;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 执行阅读投影：只持有安全短摘要，分页单位为动作而非可能无限长的轮次。 */
final class SessionExecutionProjection {
  private SessionExecutionProjection() {}

  static Page read(
      NormalizedSessionContent content,
      String scope,
      String cursor,
      int limit,
      String target,
      String filter)
      throws IOException {
    return read(content, scope, cursor, limit, target, filter, "");
  }

  static Page read(
      NormalizedSessionContent content,
      String scope,
      String cursor,
      int limit,
      String target,
      String filter,
      String agent)
      throws IOException {
    return read(
        content,
        new ReadRequest(scope, cursor, limit, target, filter, agent),
        new SessionContextLabels());
  }

  /**
   * 既有过程分页查询值，不包含内容、响应或显示目录。
   *
   * @param scope 游标范围
   * @param cursor 当前游标
   * @param limit 页大小
   * @param target 目标调用或工具
   * @param filter 动作状态筛选
   * @param agent 所选完整上下文
   */
  record ReadRequest(
      String scope, String cursor, int limit, String target, String filter, String agent) {}

  static Page read(
      NormalizedSessionContent content, ReadRequest request, SessionContextLabels labels)
      throws IOException {
    String scope = request.scope();
    String cursor = request.cursor();
    int limit = request.limit();
    String target = request.target();
    String filter = request.filter();
    String agent = request.agent();
    long offset = cursor == null ? 0 : SessionContentCursor.decode(cursor, scope);
    var groups = new LinkedHashMap<String, Group>();
    var owners = new java.util.HashMap<String, String>();
    var tools = new LinkedHashMap<String, List<ApiResponses.ToolExecutionSummary>>();
    var index = ContentRoundIndex.build(content, 0);
    var previews = SessionContentPreviews.read(content);
    var inputPreviews = inputPreviews(content, previews);
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        for (var call : unit.calls()) {
          labels.register(call);
          owners.put(call.callId(), SessionContextLabels.context(call));
          if (!SessionCollaborationProjection.matches(call, agent)) continue;
          String text = previews.text(call, false);
          boolean outputAvailable = !text.isBlank() || !call.response().toolCallIds().isEmpty();
          String evidence = ContentRoundIndex.modelCallEvidence(content.header().agent(), call);
          boolean response = outputAvailable || "response_usage".equals(evidence);
          groups.put(
              call.callId(),
              new Group(
                  call.callId(),
                  call.callIndex(),
                  index.roundIndexForCall(call.callId()).orElse(1),
                  response ? ("response_usage".equals(evidence) ? "模型响应记录" : "本地响应记录") : "输入记录",
                  call.scope().name().toLowerCase(java.util.Locale.ROOT),
                  call.subagentId().orElse(""),
                  call.parentCallId().orElse(""),
                  call.parentToolCallId().orElse(""),
                  shortText(response ? text : previews.text(call, true)),
                  call.response().toolCallIds().size(),
                  response,
                  shortText(previews.timestamp(call)),
                  !previews.text(call, true).isBlank() || !call.request().toolResultIds().isEmpty(),
                  outputAvailable));
        }
      }
    }
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var tool : reader.next().toolExecutions()) {
          if (!agent.isEmpty()
              && !agent.equals(
                  SessionContextLabels.executionContext(tool, owners.get(tool.declaredByCallId()))))
            continue;
          tools
              .computeIfAbsent(tool.declaredByCallId(), key -> new ArrayList<>())
              .add(
                  SessionApiHandler.toolSummary(
                      tool,
                      inputPreviews.getOrDefault(tool.toolCallId(), ""),
                      previews.hasToolResult(tool.toolCallId())));
        }
      }
    }
    var items = new ArrayList<Item>();
    groups.values().stream()
        .sorted(Comparator.comparingInt(Group::index))
        .forEach(
            group -> {
              var owned = tools.remove(group.id());
              if (owned == null || owned.isEmpty()) {
                if (!"failed".equals(filter)) items.add(new Item(group, null, 0));
              } else {
                for (int ordinal = 0; ordinal < owned.size(); ordinal++) {
                  var tool = owned.get(ordinal);
                  if (!"failed".equals(filter) || failed(tool))
                    items.add(new Item(group, tool, ordinal + 1));
                }
              }
            });
    for (var remaining : tools.values()) {
      for (var tool : remaining) {
        var group =
            new Group(
                tool.declaredByCallId(),
                0,
                0,
                "来源未确认",
                tool.scope(),
                tool.subagentId(),
                "",
                "",
                "",
                0,
                false,
                "",
                false,
                false);
        if (!"failed".equals(filter) || failed(tool)) items.add(new Item(group, tool, 0));
      }
    }
    if (target != null) {
      boolean found = false;
      for (int i = 0; i < items.size(); i++) {
        var item = items.get(i);
        if ((item.tool() != null && target.equals(item.tool().toolCallId()))
            || target.equals(item.group().id())) {
          offset = i;
          found = true;
          break;
        }
      }
      if (!found) throw new BadRequestResponse("execution target not found in this scope");
    }
    if (offset > items.size()) throw new BadRequestResponse("cursor exceeds section total");
    long end = Math.min(items.size(), offset + limit);
    return new Page(
        ApiResponses.SCHEMA_VERSION,
        items.subList((int) offset, (int) end),
        items.size(),
        offset,
        end < items.size() ? SessionContentCursor.encode(scope, end) : null,
        null,
        contextLabels(items.subList((int) offset, (int) end), null, labels));
  }

  static Diagnostics diagnostics(NormalizedSessionContent content) throws IOException {
    return diagnostics(content, "");
  }

  static Diagnostics diagnostics(NormalizedSessionContent content, String agent)
      throws IOException {
    return diagnostics(content, agent, new SessionContextLabels());
  }

  static Diagnostics diagnostics(
      NormalizedSessionContent content, String agent, SessionContextLabels labels)
      throws IOException {
    var sameInputs = new SessionExecutionInputs(content);
    var owners = new java.util.HashMap<String, String>();
    var identities = new java.util.HashMap<String, CallIdentity>();
    var spawns = new HashSet<String>();
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        sameInputs.observe(unit);
        for (var call : unit.calls()) {
          labels.register(call);
          owners.put(call.callId(), SessionCollaborationProjection.context(call));
          identities.put(
              call.callId(),
              new CallIdentity(
                  call.scope().name(),
                  call.subagentId().orElse(""),
                  call.parentToolName().orElse(""),
                  call.parentToolCallId().orElse("")));
        }
        for (var tool : unit.toolExecutions())
          if ("spawn_agent".equals(tool.name())) spawns.add(tool.toolCallId());
      }
    }
    sameInputs.resolve();
    var signals = new LongOperationsBuilder();
    var cumulativeSignals = new WorkloadSignalsBuilder();
    long total = 0;
    long measured = 0;
    var workNanos = BigInteger.ZERO;
    long failed = 0;
    String firstFailure = "";
    ApiResponses.ToolExecutionSummary firstFailureTool = null;
    var longest = new LinkedHashMap<List<String>, ApiResponses.ToolExecutionSummary>();
    var families = new LinkedHashMap<List<String>, WorkloadBuilder>();
    var seen = new HashSet<String>();
    var previews = SessionContentPreviews.read(content);
    var inputs = inputPreviews(content, previews);
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var tool : reader.next().toolExecutions()) {
          if (!agent.isEmpty()
              && !agent.equals(
                  SessionContextLabels.executionContext(tool, owners.get(tool.declaredByCallId()))))
            continue;
          if (!seen.add(tool.toolCallId())) continue;
          var summary =
              SessionApiHandler.toolSummary(
                  tool,
                  inputs.getOrDefault(tool.toolCallId(), ""),
                  previews.hasToolResult(tool.toolCallId()));
          sameInputs.add(
              summary,
              LongOperationsBuilder.confirmed(
                  summary, identities.get(tool.declaredByCallId()), spawns));
          total++;
          signals.add(summary, identities.get(tool.declaredByCallId()), spawns);
          cumulativeSignals.add(summary, identities.get(tool.declaredByCallId()), spawns);
          if (("main".equals(summary.scope()) && summary.subagentId().isBlank())
              || ("subagent".equals(summary.scope()) && !summary.subagentId().isBlank())) {
            var family = List.of(summary.scope(), summary.subagentId(), summary.name());
            families.computeIfAbsent(family, key -> new WorkloadBuilder()).add(summary);
          }
          if (failed(summary)) {
            failed++;
            if (firstFailure.isEmpty()) {
              firstFailure = tool.toolCallId();
              firstFailureTool = summary;
            }
          }
          if (summary.durationMs() != null) {
            measured++;
            workNanos = workNanos.add(preciseNanos(summary));
            String kind = summary.observation() == null ? "" : summary.observation().kind();
            var comparison = List.of(tool.name(), kind);
            var previous = longest.get(comparison);
            if (previous == null || preciseNanos(summary).compareTo(preciseNanos(previous)) > 0)
              longest.put(comparison, summary);
          }
        }
      }
    }
    var workloads =
        families.entrySet().stream()
            .filter(entry -> entry.getValue().measured > 0)
            .map(entry -> entry.getValue().finish(entry.getKey(), sameInputs))
            .sorted(
                Comparator.comparing(Workload::scope)
                    .thenComparing(Workload::subagentId)
                    .thenComparing(Workload::kind)
                    .thenComparing(
                        value -> new BigInteger(value.measuredWorkNanos()),
                        Comparator.reverseOrder())
                    .thenComparing(Workload::name))
            .toList();
    return new Diagnostics(
        total,
        measured,
        new BigDecimal(workNanos, 6).doubleValue(),
        failed,
        firstFailure,
        longest.values().stream()
            .sorted(Comparator.comparing(SessionExecutionProjection::preciseNanos).reversed())
            .limit(8)
            .toList(),
        longest.size(),
        firstFailureTool,
        workloads.stream().limit(8).toList(),
        workloads.size(),
        total - families.values().stream().mapToLong(value -> value.measured).sum(),
        signals.finish(),
        cumulativeSignals.finish(sameInputs));
  }

  /** 只接受已知执行器事件族；完整 source 是证据定位符，不是口径身份。 */
  private static boolean comparable(ApiResponses.ToolExecutionSummary tool) {
    var observation = tool.observation();
    return observation != null
        && "executor_reported".equals(observation.kind())
        && observation.source().matches("codex:exec_command_end#event\\[[0-9]+\\]");
  }

  /**
   * 仅保留身份判定必要值，不在全范围映射中持有调用正文及边集合。
   *
   * @param scope 声明记录的执行作用域
   * @param subagentId 完整子代理身份，主会话或未记录时为空
   * @param parentToolName 已解析父工具名，未确认时为空
   * @param parentToolCallId 已解析父工具标识，未确认时为空
   */
  private record CallIdentity(
      String scope, String subagentId, String parentToolName, String parentToolCallId) {}

  /** 窄家族完整覆盖；先确认声明身份及 typed 观测，再裁剪候选。 */
  private static final class LongOperationsBuilder {
    private long total;
    private long measured;
    private long unknown;
    private long other;
    private long unconfirmed;
    private final List<LongOperation> candidates = new ArrayList<>(4);

    private void add(
        ApiResponses.ToolExecutionSummary tool, CallIdentity owner, Set<String> spawns) {
      if (!"exec_command".equals(tool.name())) return;
      total++;
      // 各排除类别互斥：身份不足优先，其次缺测，最后其他口径。
      if (!confirmed(tool, owner, spawns)) unconfirmed++;
      else if (tool.observation() == null || tool.observation().durationNanos() == null) unknown++;
      else if (!comparable(tool)) other++;
      else {
        measured++;
        candidates.add(new LongOperation(preciseNanos(tool).toString(), tool));
        candidates.sort(
            Comparator.comparing(
                    (LongOperation value) -> new BigInteger(value.durationNanos()),
                    Comparator.reverseOrder())
                .thenComparing(value -> value.tool().scope())
                .thenComparing(value -> value.tool().subagentId())
                .thenComparing(value -> value.tool().declaredByCallId())
                .thenComparing(value -> value.tool().toolCallId()));
        if (candidates.size() > 3) candidates.removeLast();
      }
    }

    private static boolean confirmed(
        ApiResponses.ToolExecutionSummary tool, CallIdentity owner, Set<String> spawns) {
      if (owner == null
          || !owner.scope().equalsIgnoreCase(tool.scope())
          || !owner.subagentId().equals(tool.subagentId())) return false;
      if ("main".equals(tool.scope())) return tool.subagentId().isEmpty();
      // Codex 唯一 spawn relation 才携带此已解析父边；缺失/冲突不猜实例。
      return "subagent".equals(tool.scope())
          && !tool.subagentId().isBlank()
          && "spawn_agent".equals(owner.parentToolName())
          && spawns.contains(owner.parentToolCallId());
    }

    private LongOperations finish() {
      return new LongOperations(
          total, measured, unknown, other, unconfirmed, List.copyOf(candidates));
    }
  }

  /**
   * 精确单次纳秒与已有完整身份、安全预览、观测来源及定位工具键。
   *
   * @param durationNanos 精确单次纳秒的十进制字符串
   * @param tool 含完整身份与稳定定位标识的工具摘要
   */
  record LongOperation(String durationNanos, ApiResponses.ToolExecutionSummary tool) {}

  /**
   * exec_command 的互斥覆盖，身份不足不意味着真实子实例不存在。
   *
   * @param totalTools 当前范围内同名工具总数
   * @param measuredTools 身份确认且有受支持执行器原始时长的数量
   * @param unknownTools 身份确认但缺少执行器原始时长的数量
   * @param otherKindTools 身份确认且有原始时长但计时口径不受支持的数量
   * @param unconfirmedIdentityTools 缺少确定执行身份或唯一委派依据的数量
   * @param candidates 按精确单次时长与稳定完整身份选取的至多三项
   */
  record LongOperations(
      long totalTools,
      long measuredTools,
      long unknownTools,
      long otherKindTools,
      long unconfirmedIdentityTools,
      List<LongOperation> candidates) {}

  /** 累计线索先确认完整组身份，再统计覆盖与裁剪；不保留工具列表。 */
  private static final class WorkloadSignalsBuilder {
    private final Map<List<String>, SignalGroup> groups = new LinkedHashMap<>();
    private final Set<List<String>> excluded = new HashSet<>();
    private long ungrouped;

    private void add(
        ApiResponses.ToolExecutionSummary tool, CallIdentity owner, Set<String> spawns) {
      if (!"exec_command".equals(tool.name())) return;
      var declared =
          owner == null
              ? List.<String>of()
              : contextKey(owner.scope().toLowerCase(java.util.Locale.ROOT), owner.subagentId());
      var reported = contextKey(tool.scope(), tool.subagentId());
      boolean confirmed = LongOperationsBuilder.confirmed(tool, owner, spawns);
      if (!confirmed) {
        if (!declared.isEmpty()) excluded.add(declared);
        if (!reported.isEmpty()) excluded.add(reported);
      }
      // 不一致时只将调用计入一个已知组；相关两侧均失去整组资格。
      var key = declared.isEmpty() ? reported : declared;
      if (key.isEmpty()) ungrouped++;
      else groups.computeIfAbsent(key, ignored -> new SignalGroup()).add(tool);
    }

    private static List<String> contextKey(String scope, String id) {
      if (("main".equals(scope) && id.isEmpty()) || ("subagent".equals(scope) && !id.isBlank()))
        return List.of(scope, id);
      return List.of();
    }

    private WorkloadSignals finish(SessionExecutionInputs sameInputs) {
      long total = ungrouped;
      long measured = 0;
      long unknown = 0;
      long other = 0;
      long identity = ungrouped;
      var candidates = new ArrayList<WorkloadSignal>();
      for (var entry : groups.entrySet()) {
        var group = entry.getValue();
        total += group.total;
        if (excluded.contains(entry.getKey())) identity += group.total;
        else {
          measured += group.measured;
          unknown += group.unknown;
          other += group.other;
          if (group.measured > 0) candidates.add(group.finish(entry.getKey(), sameInputs));
        }
      }
      candidates.sort(
          Comparator.comparing(
                  (WorkloadSignal value) -> new BigInteger(value.measuredWorkNanos()),
                  Comparator.reverseOrder())
              .thenComparing(WorkloadSignal::scope)
              .thenComparing(WorkloadSignal::subagentId)
              .thenComparing(WorkloadSignal::name)
              .thenComparing(WorkloadSignal::kind));
      return new WorkloadSignals(
          total,
          measured,
          unknown,
          other,
          identity,
          candidates.size(),
          List.copyOf(candidates.subList(0, Math.min(3, candidates.size()))));
    }
  }

  /** 单组只持有精确和、覆盖计数及一个单次代表。 */
  private static final class SignalGroup {
    private long total;
    private long measured;
    private long unknown;
    private long other;
    private BigInteger nanos = BigInteger.ZERO;
    private LongOperation longest;

    private void add(ApiResponses.ToolExecutionSummary tool) {
      total++;
      if (tool.observation() == null || tool.observation().durationNanos() == null) unknown++;
      else if (!comparable(tool)) other++;
      else {
        measured++;
        var duration = preciseNanos(tool);
        nanos = nanos.add(duration);
        if (longest == null
            || duration.compareTo(new BigInteger(longest.durationNanos())) > 0
            || (duration.toString().equals(longest.durationNanos())
                && Comparator.comparing(ApiResponses.ToolExecutionSummary::declaredByCallId)
                        .thenComparing(ApiResponses.ToolExecutionSummary::toolCallId)
                        .compare(tool, longest.tool())
                    < 0)) {
          longest = new LongOperation(duration.toString(), tool);
        }
      }
    }

    private WorkloadSignal finish(List<String> key, SessionExecutionInputs sameInputs) {
      return new WorkloadSignal(
          key.get(0),
          key.get(1),
          "exec_command",
          "executor_reported",
          nanos.toString(),
          total,
          measured,
          unknown,
          other,
          longest,
          sameInputs.maximum(
              List.of(key.get(0), key.get(1), "exec_command"),
              total,
              measured,
              unknown,
              other,
              nanos.toString()));
    }
  }

  /**
   * 同家族已测子集累计，不表示实际总量或任务成本。
   *
   * @param scope 确认的执行作用域
   * @param subagentId 完整子代理身份，主会话为空
   * @param name 原始工具名，当前仅支持 exec_command
   * @param kind 测量口径，当前仅支持 executor_reported 的 codex:exec_command_end 事件族
   * @param measuredWorkNanos 已测子集精确累计纳秒十进制字符串
   * @param totalTools 此组全部同名工具数
   * @param measuredTools 此组可信原始计时数量，包含实测零
   * @param unknownTools 此组缺少原始计时的数量
   * @param otherKindTools 此组有原始计时但口径不受支持的数量
   * @param sameInputMaximum 可选同完整参数记录最大累计，不改变最长代表
   * @param longest 已纳入子集的最长单次代表，不承载整组累计
   */
  record WorkloadSignal(
      String scope,
      String subagentId,
      String name,
      String kind,
      String measuredWorkNanos,
      long totalTools,
      long measuredTools,
      long unknownTools,
      long otherKindTools,
      LongOperation longest,
      SessionExecutionInputs.SameInputMaximum sameInputMaximum) {}

  /**
   * 完整范围的累计线索覆盖；身份失败组整组排除，余下计时允许部分覆盖。
   *
   * @param totalTools 当前范围全部 exec_command 数量
   * @param measuredTools 合格身份组内可信原始计时数量
   * @param unknownTools 合格身份组内缺少原始计时的数量
   * @param otherKindTools 合格身份组内不受支持原始计时口径的数量
   * @param excludedIdentityTools 因组身份边界不足或无法归组而排除的调用数
   * @param eligibleGroups 身份合格且至少有一条可信计时的组数，不表示代理数
   * @param candidates 按精确累计及稳定完整身份排序的至多三组
   */
  record WorkloadSignals(
      long totalTools,
      long measuredTools,
      long unknownTools,
      long otherKindTools,
      long excludedIdentityTools,
      long eligibleGroups,
      List<WorkloadSignal> candidates) {}

  /** 同一可信上下文、原工具名的覆盖；当前唯一受支持口径独立累计。 */
  private static final class WorkloadBuilder {
    private long total;
    private long measured;
    private long unknown;
    private long other;
    private BigInteger nanos = BigInteger.ZERO;
    private final List<ApiResponses.ToolExecutionSummary> slowest = new ArrayList<>(3);

    private void add(ApiResponses.ToolExecutionSummary tool) {
      total++;
      if (tool.durationMs() == null) unknown++;
      else if (!comparable(tool)) other++;
      else {
        measured++;
        nanos = nanos.add(preciseNanos(tool));
        slowest.add(tool);
        slowest.sort(
            Comparator.comparing(
                    SessionExecutionProjection::preciseNanos, Comparator.reverseOrder())
                .thenComparing(ApiResponses.ToolExecutionSummary::toolCallId));
        if (slowest.size() > 3) slowest.removeLast();
      }
    }

    private Workload finish(List<String> key, SessionExecutionInputs sameInputs) {
      return new Workload(
          key.get(0),
          key.get(1),
          "executor_reported",
          key.get(2),
          total,
          measured,
          unknown,
          other,
          nanos.toString(),
          slowest.getFirst(),
          List.copyOf(slowest),
          other == 0
              ? sameInputs.maximum(key, total, measured, unknown, other, nanos.toString())
              : null);
    }
  }

  private static Map<String, String> inputPreviews(
      NormalizedSessionContent content, SessionContentPreviews previews) throws IOException {
    var inputs = new java.util.HashMap<String, String>(previews.independentToolInputs());
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var call : reader.next().calls()) inputs.putAll(previews.toolInputs(call));
      }
    }
    return inputs;
  }

  static boolean failed(ApiResponses.ToolExecutionSummary tool) {
    return failureEvidence(tool) != null;
  }

  static FailureEvidence failureEvidence(ApiResponses.ToolExecutionSummary tool) {
    if (tool == null) return null;
    Integer exit =
        tool.observation() != null && tool.observation().exitCode() != null
            ? tool.observation().exitCode()
            : tool.exitCode();
    if (exit != null && exit != 0) return new FailureEvidence("nonzero_exit", exit, null);
    String explicit = tool.observation() == null ? "" : tool.observation().status();
    if ("failed".equals(explicit) || "error".equals(explicit) || "cancelled".equals(explicit))
      return new FailureEvidence("executor_status", null, explicit);
    if (!tool.status().isBlank()
        && !List.of("ok", "success", "completed", "running", "pending", "queued")
            .contains(tool.status().toLowerCase(java.util.Locale.ROOT)))
      return new FailureEvidence("result_signal", null, null);
    return null;
  }

  /**
   * 首个满足旧失败判定的有界依据，不承载任意结果原文。
   *
   * @param kind 固定依据类别
   * @param exitCode 有效非零退出码，仅退出依据存在
   * @param executorStatus 精确负面执行器状态，仅状态依据存在
   */
  record FailureEvidence(String kind, Integer exitCode, String executorStatus) {}

  private static java.math.BigInteger preciseNanos(ApiResponses.ToolExecutionSummary tool) {
    if (tool.observation() != null && tool.observation().durationNanos() != null)
      return java.math.BigInteger.valueOf(tool.observation().durationNanos());
    return java.math.BigInteger.valueOf(tool.durationMs())
        .multiply(java.math.BigInteger.valueOf(1_000_000));
  }

  private static String shortText(String text) {
    String safe =
        com.feipi.session.browser.query.api.SensitiveFieldPolicy.DEFAULT.applyMasking(text);
    return safe.length() <= 180 ? safe : safe.substring(0, 179) + "…";
  }

  private static Map<String, String> contextLabels(
      List<Item> items, Diagnostics diagnostics, SessionContextLabels labels) {
    var keys = new java.util.LinkedHashSet<String>();
    for (var item : items) {
      var group = item.group();
      keys.add(SessionContextLabels.reference(group.scope(), group.subagentId(), group.id()));
      addContext(keys, item.tool());
    }
    if (diagnostics != null) {
      addContext(keys, diagnostics.firstFailureTool());
      diagnostics.longestByName().forEach(tool -> addContext(keys, tool));
      for (var workload : diagnostics.workloads()) {
        keys.add(SessionContextLabels.reference(workload.scope(), workload.subagentId(), ""));
        addContext(keys, workload.longest());
        workload.slowest().forEach(tool -> addContext(keys, tool));
        if (workload.sameInputMaximum() != null)
          addContext(keys, workload.sameInputMaximum().tool());
      }
      diagnostics.longOperations().candidates().forEach(value -> addContext(keys, value.tool()));
      for (var signal : diagnostics.workloadSignals().candidates()) {
        keys.add(SessionContextLabels.reference(signal.scope(), signal.subagentId(), ""));
        if (signal.longest() != null) addContext(keys, signal.longest().tool());
        if (signal.sameInputMaximum() != null) addContext(keys, signal.sameInputMaximum().tool());
      }
    }
    return labels.subset(keys);
  }

  private static void addContext(Set<String> keys, ApiResponses.ToolExecutionSummary tool) {
    if (tool != null)
      keys.add(
          SessionContextLabels.reference(tool.scope(), tool.subagentId(), tool.declaredByCallId()));
  }

  /**
   * 一页动作及同一快照的全量诊断。
   *
   * @param schemaVersion API 版本
   * @param items 当前页动作
   * @param total 筛选后的动作总数
   * @param offset 当前页起点
   * @param nextCursor 同范围续页游标
   * @param diagnostics 未经分页裁剪的诊断
   * @param contextLabels 当前页及诊断引用与全调用权威上下文的交集
   */
  record Page(
      String schemaVersion,
      List<Item> items,
      long total,
      long offset,
      String nextCursor,
      Diagnostics diagnostics,
      Map<String, String> contextLabels) {
    Page(
        String schemaVersion,
        List<Item> items,
        long total,
        long offset,
        String nextCursor,
        Diagnostics diagnostics) {
      this(schemaVersion, items, total, offset, nextCursor, diagnostics, Map.of());
    }

    Page withDiagnostics(Diagnostics value, SessionContextLabels labels) {
      return new Page(
          schemaVersion,
          items,
          total,
          offset,
          nextCursor,
          value,
          SessionExecutionProjection.contextLabels(items, value, labels));
    }
  }

  /**
   * 动作和确切声明来源；单响应的工具可跨页而不丢失来源。
   *
   * @param group 本地记录边界
   * @param tool 工具动作，纯文本记录为空
   * @param toolOrdinal 同一声明组内的工具序号，非工具或未知来源为零
   */
  record Item(Group group, ApiResponses.ToolExecutionSummary tool, int toolOrdinal) {}

  /**
   * 本地调用的紧凑来源，不宣称完整原始 HTTP 请求。
   *
   * @param id 稳定调用标识
   * @param index 本地记录序号
   * @param round 证据轮次
   * @param label 边界类型
   * @param scope 独立上下文
   * @param subagentId 子代理标识
   * @param parentCallId 父调用边
   * @param parentToolCallId 已确认父工具身份，不以父调用猜委派
   * @param preview 遮蔽后的短文本
   * @param toolCount 此响应声明的工具总数
   * @param response 是否有响应证据
   * @param timestamp 来源记录时间，不表示执行起止区间
   * @param inputAvailable 是否有本地输入正文或工具结果引用
   * @param outputAvailable 是否有本地输出正文或工具声明
   */
  record Group(
      String id,
      int index,
      int round,
      String label,
      String scope,
      String subagentId,
      String parentCallId,
      String parentToolCallId,
      String preview,
      int toolCount,
      boolean response,
      String timestamp,
      boolean inputAvailable,
      boolean outputAvailable) {}

  /**
   * 全量工具证据覆盖；工作量之和不冒充墙钟或关键路径。
   *
   * @param totalTools 所有工具数
   * @param measuredTools 有时长证据的工具数
   * @param measuredWorkMs 已测工具工作量之和
   * @param failures 观察到失败信号的数量
   * @param firstFailure 首个失败定位标识
   * @param longestByName 各同名且同口径工具已测最长项
   * @param measuredKinds 有时长证据的工具类别总数
   * @param firstFailureTool 首个失败动作的安全短摘要，未观察到失败时为空
   * @param workloads 按可信上下文分块、块内按已测累计排序的有界汇总
   * @param workloadGroups 完整范围中可比较的汇总数，用于披露截断
   * @param unrankedTools 未参与可信累计比较的调用数，含缺测、口径和上下文未知
   * @param workloadSignals 同家族确定身份组的独立已测累计线索与互斥覆盖
   * @param longOperations 完整当前筛选范围的可信单次操作线索与互斥覆盖
   */
  record Diagnostics(
      long totalTools,
      long measuredTools,
      double measuredWorkMs,
      long failures,
      String firstFailure,
      List<ApiResponses.ToolExecutionSummary> longestByName,
      long measuredKinds,
      ApiResponses.ToolExecutionSummary firstFailureTool,
      List<Workload> workloads,
      long workloadGroups,
      long unrankedTools,
      LongOperations longOperations,
      WorkloadSignals workloadSignals) {
    /** 只从既有首工具派生，不读取其它内容或改变构造入口。 */
    @JsonProperty("firstFailureEvidence")
    public FailureEvidence firstFailureEvidence() {
      return failureEvidence(firstFailureTool);
    }

    /** 空内容投影仍使用同一包内构造入口，不虚构可信累计项。 */
    Diagnostics(
        long totalTools,
        long measuredTools,
        double measuredWorkMs,
        long failures,
        String firstFailure,
        List<ApiResponses.ToolExecutionSummary> longestByName,
        long measuredKinds,
        ApiResponses.ToolExecutionSummary firstFailureTool) {
      this(
          totalTools,
          measuredTools,
          measuredWorkMs,
          failures,
          firstFailure,
          longestByName,
          measuredKinds,
          firstFailureTool,
          List.of(),
          0,
          totalTools,
          new LongOperations(0, 0, 0, 0, 0, List.of()),
          new WorkloadSignals(0, 0, 0, 0, 0, 0, List.of()));
    }
  }

  /**
   * 单一可信上下文与测量口径下的同名工作量，不合并真实调用身份。
   *
   * @param scope 执行作用域
   * @param subagentId 确切子代理身份，主会话为空
   * @param kind 受支持测量口径，不使用逐事件定位符
   * @param name 原始工具名，不表示同一语义动作
   * @param totalTools 此上下文同名调用总数，含其他口径和未测
   * @param measuredTools 当前口径已测数，包含实测零
   * @param unknownTools 未测调用数，不补零
   * @param otherKindTools 有时长但为其他或未确认口径的调用数
   * @param measuredWorkNanos 精确累计纳秒的十进制字符串，避免溢出和客户端精度丢失
   * @param longest 最长单次代表项，时长相同时按稳定工具身份选取
   * @param sameInputMaximum 与可信累计计时集合一致时共用的可选事实
   * @param slowest 本口径单次耗时前至多三项，含代表，不合并同名或同预览调用
   */
  record Workload(
      String scope,
      String subagentId,
      String kind,
      String name,
      long totalTools,
      long measuredTools,
      long unknownTools,
      long otherKindTools,
      String measuredWorkNanos,
      ApiResponses.ToolExecutionSummary longest,
      List<ApiResponses.ToolExecutionSummary> slowest,
      SessionExecutionInputs.SameInputMaximum sameInputMaximum) {}
}
