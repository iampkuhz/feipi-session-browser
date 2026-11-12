package com.feipi.session.browser.web.api;

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
    long offset = cursor == null ? 0 : SessionContentCursor.decode(cursor, scope);
    var groups = new LinkedHashMap<String, Group>();
    var tools = new LinkedHashMap<String, List<ApiResponses.ToolExecutionSummary>>();
    var index = ContentRoundIndex.build(content, 0);
    var previews = SessionContentPreviews.read(content);
    var inputPreviews = inputPreviews(content, previews);
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        var unit = reader.next();
        for (var call : unit.calls()) {
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
        null);
  }

  static Diagnostics diagnostics(NormalizedSessionContent content) throws IOException {
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
          if (!seen.add(tool.toolCallId())) continue;
          var summary =
              SessionApiHandler.toolSummary(
                  tool,
                  inputs.getOrDefault(tool.toolCallId(), ""),
                  previews.hasToolResult(tool.toolCallId()));
          total++;
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
            .map(entry -> entry.getValue().finish(entry.getKey()))
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
        total - families.values().stream().mapToLong(value -> value.measured).sum());
  }

  /** 只接受已知执行器事件族；完整 source 是证据定位符，不是口径身份。 */
  private static boolean comparable(ApiResponses.ToolExecutionSummary tool) {
    var observation = tool.observation();
    return observation != null
        && "executor_reported".equals(observation.kind())
        && observation.source().matches("codex:exec_command_end#event\\[[0-9]+\\]");
  }

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

    private Workload finish(List<String> key) {
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
          List.copyOf(slowest));
    }
  }

  private static Map<String, String> inputPreviews(
      NormalizedSessionContent content, SessionContentPreviews previews) throws IOException {
    var inputs = new java.util.HashMap<String, String>();
    try (var reader = content.openCursor()) {
      while (reader.hasNext()) {
        for (var call : reader.next().calls()) inputs.putAll(previews.toolInputs(call));
      }
    }
    return inputs;
  }

  static boolean failed(ApiResponses.ToolExecutionSummary tool) {
    Integer exit =
        tool.observation() != null && tool.observation().exitCode() != null
            ? tool.observation().exitCode()
            : tool.exitCode();
    String explicit = tool.observation() == null ? "" : tool.observation().status();
    return (exit != null && exit != 0)
        || "failed".equals(explicit)
        || "error".equals(explicit)
        || "cancelled".equals(explicit)
        || (!tool.status().isBlank()
            && !List.of("ok", "success", "completed", "running", "pending", "queued")
                .contains(tool.status().toLowerCase(java.util.Locale.ROOT)));
  }

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

  /**
   * 一页动作及同一快照的全量诊断。
   *
   * @param schemaVersion API 版本
   * @param items 当前页动作
   * @param total 筛选后的动作总数
   * @param offset 当前页起点
   * @param nextCursor 同范围续页游标
   * @param diagnostics 未经分页裁剪的诊断
   */
  record Page(
      String schemaVersion,
      List<Item> items,
      long total,
      long offset,
      String nextCursor,
      Diagnostics diagnostics) {}

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
      long unrankedTools) {
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
          totalTools);
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
      List<ApiResponses.ToolExecutionSummary> slowest) {}
}
