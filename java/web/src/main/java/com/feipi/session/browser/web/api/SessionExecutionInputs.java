package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.math.BigInteger;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/** 请求内完整参数记录身份；挂在原有两轮诊断遍历，不持有输入原文。 */
final class SessionExecutionInputs {
  private static final int ITEMS = 16_384;
  private static final int CHARACTERS = 4_194_304;
  private static final Comparator<ApiResponses.ToolExecutionSummary> IDENTITY =
      Comparator.comparing(ApiResponses.ToolExecutionSummary::scope)
          .thenComparing(ApiResponses.ToolExecutionSummary::subagentId)
          .thenComparing(ApiResponses.ToolExecutionSummary::declaredByCallId)
          .thenComparing(ApiResponses.ToolExecutionSummary::toolCallId);
  private final Map<String, Owner> owners = new HashMap<>();
  private final Map<String, Claim> tools = new HashMap<>();
  private final Map<String, List<Candidate>> catalog = new HashMap<>();
  private final Map<String, TreeMap<Long, String>> sequences = new HashMap<>();
  private final Set<String> duplicateCalls = new HashSet<>();
  private final Set<String> duplicateTools = new HashSet<>();
  private final Set<String> duplicateCatalog = new HashSet<>();
  private final Map<List<String>, InputGroup> groups = new HashMap<>();
  private final Map<List<String>, Result> finished = new HashMap<>();
  private final Map<String, Candidate> resolved = new HashMap<>();
  private final Set<String> invalid = new HashSet<>();
  private boolean exceeded;
  private int calls;
  private int toolCount;
  private int entries;
  private int units;
  private int refs;
  private long metadata;
  private long parameters;
  private int nodes;

  SessionExecutionInputs(NormalizedSessionContent content) {
    exceeded = content.header().agent() != NormalizedAgent.CODEX;
  }

  void observe(NormalizedContentUnit unit) {
    if (exceeded) return;
    if (++units > ITEMS) exceeded = true;
    for (var call : unit.calls()) observeCall(call);
    for (var tool : unit.toolExecutions()) {
      if (exceeded) break;
      if (++toolCount > ITEMS) exceeded = true;
      tool.status().ifPresent(this::meta);
      tool.observation()
          .ifPresent(
              observation -> {
                meta(observation.toolCallId());
                meta(observation.kind());
                meta(observation.source());
                if (observation.status() != null) meta(observation.status());
                if (observation.processId() != null) meta(observation.processId());
                if (observation.issue() != null) meta(observation.issue());
                if (!tool.toolCallId().equals(observation.toolCallId()))
                  invalid.add(tool.toolCallId());
              });
      var claim =
          new Claim(
              meta(tool.declaredByCallId()),
              meta(tool.name()),
              tool.scope().getValue(),
              meta(tool.subagentId().orElse("")));
      if (tools.putIfAbsent(meta(tool.toolCallId()), claim) != null)
        duplicateTools.add(tool.toolCallId());
    }
    for (var chunk : unit.sourceUnitSequences()) {
      if (exceeded) break;
      var sequence = sequences.computeIfAbsent(meta(chunk.name()), ignored -> new TreeMap<>());
      for (int i = 0; i < chunk.keys().size() && !exceeded; i++) {
        reference();
        if (sequence.putIfAbsent(chunk.offset() + i, meta(chunk.keys().get(i))) != null)
          sequence.put(chunk.offset() + i, "");
      }
    }
    for (var entry : unit.sourceUnitCatalog().entrySet()) {
      if (exceeded) break;
      if (++entries > ITEMS) exceeded = true;
      String key = meta(entry.getKey());
      var value = entry.getValue();
      meta(value.unitKey());
      meta(value.unitType());
      meta(value.canonicalSourceLocator());
      meta(value.contentHash());
      value.label().ifPresent(this::meta);
      value.timestamp().ifPresent(this::meta);
      if (!key.equals(value.unitKey())) duplicateCatalog.add(key);
      var candidates = source(value.payload());
      if (!"response".equals(value.direction().getValue())) candidates = List.of();
      if (catalog.putIfAbsent(key, candidates) != null) duplicateCatalog.add(key);
    }
    if (exceeded) discard();
  }

  private void observeCall(NormalizedCall call) {
    if (exceeded) return;
    if (++calls > ITEMS) exceeded = true;
    var declarations = new HashSet<String>();
    for (String id : call.response().toolCallIds()) {
      if (exceeded) break;
      reference();
      if (!declarations.add(meta(id))) invalid.add(id);
    }
    var ranges = new ArrayList<SourceUnitRefRange>();
    for (var range : call.sourceUnitRefRanges()) {
      if (exceeded) break;
      reference();
      range.sequence().ifPresent(this::meta);
      range.role().ifPresent(this::meta);
      for (String ref : range.refs()) {
        if (exceeded) break;
        reference();
        meta(ref);
      }
      ranges.add(range);
    }
    var inline = new ArrayList<Candidate>();
    for (var source : call.sourceUnits()) {
      if (exceeded) break;
      var candidates = source(source);
      if (!"user".equals(source.get("role"))) inline.addAll(candidates);
    }
    var owner =
        new Owner(
            call.scope().getValue(),
            meta(call.subagentId().orElse("")),
            declarations,
            List.copyOf(ranges),
            List.copyOf(inline),
            meta(call.parentToolName().orElse("")),
            meta(call.parentToolCallId().orElse("")));
    if (owners.putIfAbsent(meta(call.callId()), owner) != null) duplicateCalls.add(call.callId());
  }

  /** 原始声明先检查，不能借既有工具汇总的裸标识早去重获得资格。 */
  void resolve() {
    if (exceeded) return;
    var declared = new HashMap<String, String>();
    var referenced = new HashMap<String, String>();
    for (var entry : owners.entrySet()) {
      String call = entry.getKey();
      var owner = entry.getValue();
      for (String id : owner.declarations()) {
        if (declared.putIfAbsent(id, call) != null || duplicateCalls.contains(call))
          invalid.add(id);
      }
      var candidates = new ArrayList<>(owner.inline());
      var mirrors = new HashSet<>(owner.inline());
      var mirrored = new HashSet<Candidate>();
      var keys = keys(owner.ranges());
      if (exceeded) {
        discard();
        return;
      }
      if (keys == null) invalid.addAll(owner.declarations());
      else
        for (String key : keys) {
          if (!catalog.containsKey(key) || duplicateCatalog.contains(key)) {
            invalid.addAll(owner.declarations());
            continue;
          }
          String previous = referenced.putIfAbsent(key, call);
          if (previous != null && !previous.equals(call)) {
            invalid.addAll(owner.declarations());
            invalid.addAll(owners.get(previous).declarations());
          }
          for (var candidate : catalog.get(key)) {
            // 只有源单元结构及内容完全一致、且引用归属一致，才承认内联镜像。
            if (!mirrors.contains(candidate)) candidates.add(candidate);
            else if (!mirrored.add(candidate)) invalid.add(candidate.id());
          }
        }
      var seen = new HashSet<String>();
      for (var candidate : candidates) {
        String id = candidate.id();
        var claim = tools.get(id);
        if (!seen.add(id)
            || !candidate.valid()
            || !owner.declarations().contains(id)
            || claim == null
            || !call.equals(claim.call())
            || !candidate.name().equals(claim.name())
            || !owner.scope().equals(claim.scope())
            || !owner.actor().equals(claim.actor())) invalid.add(id);
        if (resolved.putIfAbsent(id, candidate) != null) invalid.add(id);
      }
    }
    // 未归属目录声明不能按裸标识给已有内联声明作旁证。
    for (var entry : catalog.entrySet())
      if (!referenced.containsKey(entry.getKey()))
        for (var candidate : entry.getValue()) invalid.add(candidate.id());
    invalid.addAll(duplicateTools);
    for (var entry : tools.entrySet()) {
      String id = entry.getKey();
      var claim = entry.getValue();
      var owner = owners.get(claim.call());
      if (owner != null && "subagent".equals(owner.scope())) {
        var parent = tools.get(owner.parentTool());
        if (!"spawn_agent".equals(owner.parentName())
            || parent == null
            || !"spawn_agent".equals(parent.name())
            || duplicateTools.contains(owner.parentTool())
            || duplicateCalls.contains(parent.call())
            || !parent.call().equals(declared.get(owner.parentTool()))) invalid.add(id);
      }
      if (!claim.call().equals(declared.get(id))
          || owner == null
          || duplicateCalls.contains(claim.call())) invalid.add(id);
    }
  }

  private Set<String> keys(List<SourceUnitRefRange> ranges) {
    var result = new HashSet<String>();
    for (var range : ranges) {
      if (range.role().filter(role -> "user".equalsIgnoreCase(role)).isPresent()) continue;
      if (!range.refs().isEmpty()) {
        for (String key : range.refs()) if (!result.add(key)) return null;
      } else if (range.sequence().isPresent()) {
        var sequence = sequences.get(range.sequence().get());
        long length = (long) range.end() - range.start();
        if (length > 65_536 || sequence == null) return null;
        for (long i = range.start(); i < range.end(); i++) {
          reference();
          if (exceeded) return null;
          String key = sequence.get(i);
          if (key == null) return null;
          if (!result.add(key)) return null;
        }
      } else if (range.end() != range.start()) return null;
    }
    return result;
  }

  void add(ApiResponses.ToolExecutionSummary tool, boolean confirmed) {
    if (exceeded || !"exec_command".equals(tool.name())) return;
    var group =
        groups.computeIfAbsent(
            List.of(tool.scope(), tool.subagentId(), tool.name()), ignored -> new InputGroup());
    group.total++;
    var candidate = resolved.get(tool.toolCallId());
    if (!confirmed
        || invalid.contains(tool.toolCallId())
        || candidate == null
        || !candidate.valid()) {
      group.invalid = true;
      return;
    }
    group
        .inputs
        .computeIfAbsent(candidate.fingerprint(), ignored -> new Accumulator())
        .add(tool, candidate.preview());
  }

  SameInputMaximum maximum(
      List<String> key, long total, long measured, long unknown, long other, String nanos) {
    if (exceeded) return null;
    var group = groups.get(key);
    if (group == null || group.invalid || group.total != total || group.inputs.size() < 2)
      return null;
    var result = finished.computeIfAbsent(key, ignored -> finish(group));
    return result.total() == total
            && result.measured() == measured
            && result.unknown() == unknown
            && result.other() == other
            && result.nanos().equals(nanos)
        ? result.maximum()
        : null;
  }

  private static Result finish(InputGroup group) {
    long count = 0, measuredCount = 0, unknownCount = 0, otherCount = 0;
    var sum = BigInteger.ZERO;
    Accumulator best = null;
    for (var input : group.inputs.values()) {
      count += input.total;
      measuredCount += input.measured;
      unknownCount += input.unknown;
      otherCount += input.other;
      sum = sum.add(input.nanos);
      if (input.representative != null
          && (best == null
              || input.nanos.compareTo(best.nanos) > 0
              || (input.nanos.equals(best.nanos)
                  && IDENTITY.compare(input.representative, best.representative) < 0)))
        best = input;
    }
    if (count != group.total
        || best == null
        || best.measured < 2
        || best.representative.inputPreview().isBlank())
      return new Result(count, measuredCount, unknownCount, otherCount, sum.toString(), null);
    return new Result(
        count,
        measuredCount,
        unknownCount,
        otherCount,
        sum.toString(),
        new SameInputMaximum(
            best.nanos.toString(),
            best.total,
            best.measured,
            best.unknown,
            best.other,
            group.inputs.size(),
            count,
            group.total,
            best.representative));
  }

  private List<Candidate> source(Object value) {
    if (exceeded) return List.of();
    var candidates = new ArrayList<Candidate>();
    var digest = digest();
    int[] budget = {0, 0};
    walk(value, 0, budget, digest, candidates);
    String source = HexFormat.of().formatHex(digest.digest());
    return candidates.stream()
        .map(
            c ->
                new Candidate(
                    c.id(),
                    c.name(),
                    c.fingerprint(),
                    c.preview(),
                    source,
                    c.valid() && budget[1] == 0))
        .toList();
  }

  private void walk(
      Object value, int depth, int[] local, MessageDigest digest, List<Candidate> candidates) {
    if (exceeded) return;
    if (depth > 8 || ++local[0] > 1024 || ++nodes > 262_144) {
      exceeded = true;
      return;
    }
    if (value instanceof Map<?, ?> map) {
      digest.update((byte) 1);
      if (Boolean.TRUE.equals(map.get("truncated")) || Boolean.FALSE.equals(map.get("complete")))
        local[1] = 1;
      if (map.size() > 1024) {
        exceeded = true;
        return;
      }
      var keys = new ArrayList<String>();
      for (Object key : map.keySet()) {
        if (!(key instanceof String text)) {
          exceeded = true;
          return;
        }
        keys.add(text);
      }
      keys.sort(String::compareTo);
      for (String key : keys) {
        if (exceeded) break;
        encode(digest, meta(key));
        Object child = map.get(key);
        if (("input".equals(key) || "arguments".equals(key)) && child instanceof String text) {
          if (++local[0] > 1024 || ++nodes > 262_144 || depth + 1 > 8) exceeded = true;
          parameters += text.length();
          if (parameters > CHARACTERS) exceeded = true;
          if (!exceeded && text.length() <= 65_536) encode(digest, text);
        } else if ("input".equals(key) || "arguments".equals(key)) {
          if (++local[0] > 1024 || ++nodes > 262_144 || depth + 1 > 8) exceeded = true;
          digest.update((byte) 7);
        } else walk(child, depth + 1, local, digest, candidates);
      }
      if (!exceeded
          && map.get("type") instanceof String type
          && List.of("tool_use", "function_call", "custom_tool_call").contains(type))
        candidates.add(candidate(map));
      digest.update((byte) 5);
    } else if (value instanceof List<?> list) {
      digest.update((byte) 2);
      for (Object child : list) {
        if (exceeded) break;
        walk(child, depth + 1, local, digest, candidates);
      }
      digest.update((byte) 6);
    } else if (value instanceof String text) {
      digest.update((byte) 3);
      encode(digest, meta(text));
    } else if (value == null || value instanceof Number || value instanceof Boolean) {
      digest.update((byte) 4);
      encode(digest, String.valueOf(value));
    } else exceeded = true;
  }

  private Candidate candidate(Map<?, ?> map) {
    String id = "";
    for (String field : List.of("id", "call_id", "tool_call_id"))
      if (map.get(field) instanceof String text && !text.isBlank()) {
        if (!id.isEmpty() && !id.equals(text)) return new Candidate(id, "", "", "", "", false);
        id = text;
      }
    String name = map.get("name") instanceof String text ? text : "";
    Object raw = map.containsKey("input") ? map.get("input") : map.get("arguments");
    boolean valid =
        !id.isBlank()
            && !name.isBlank()
            && map.containsKey("input") != map.containsKey("arguments")
            && raw instanceof String text
            && !text.isBlank()
            && text.length() <= 65_536
            && !Boolean.TRUE.equals(map.get("truncated"))
            && !Boolean.FALSE.equals(map.get("complete"));
    if (!valid) return new Candidate(id, name, "", "", "", false);
    String text = (String) raw;
    var hash = digest();
    encode(hash, text);
    return new Candidate(
        id,
        name,
        HexFormat.of().formatHex(hash.digest()),
        ToolInputPreview.from(new ToolInputContents.Input(id, name, text)),
        "",
        true);
  }

  private String meta(String text) {
    if (exceeded) return "";
    if (text.length() > 1024) {
      exceeded = true;
      return "";
    }
    metadata += text.length();
    if (metadata > CHARACTERS) {
      exceeded = true;
      return "";
    }
    return text;
  }

  /** 全局不足立即撤销全部新事实；既有诊断不读取这些索引。 */
  private void discard() {
    owners.clear();
    tools.clear();
    catalog.clear();
    sequences.clear();
    duplicateCalls.clear();
    duplicateTools.clear();
    duplicateCatalog.clear();
    groups.clear();
    finished.clear();
    resolved.clear();
    invalid.clear();
  }

  private void reference() {
    if (++refs > 65_536) exceeded = true;
  }

  private static MessageDigest digest() {
    try {
      return MessageDigest.getInstance("SHA-256");
    } catch (NoSuchAlgorithmException exception) {
      throw new IllegalStateException("缺少标准输入指纹算法", exception);
    }
  }

  /** 逐 UTF-16 单元及长度编码，非法代理项也不会经替换字符产生相同身份。 */
  private static void encode(MessageDigest digest, String text) {
    int length = text.length();
    for (int shift = 24; shift >= 0; shift -= 8) digest.update((byte) (length >>> shift));
    for (int i = 0; i < length; i++) {
      char c = text.charAt(i);
      digest.update((byte) (c >>> 8));
      digest.update((byte) c);
    }
  }

  /**
   * 完整工具归属，不保存结果正文。
   *
   * @param call 声明调用
   * @param name 工具原名
   * @param scope 作用域
   * @param actor 完整代理身份
   */
  private record Claim(String call, String name, String scope, String actor) {}

  /**
   * 有界调用声明与来源关联。
   *
   * @param scope 作用域
   * @param actor 完整代理身份
   * @param declarations 声明标识
   * @param ranges 有界来源引用
   * @param inline 安全内联声明
   * @param parentName 已确认父工具名
   * @param parentTool 已确认父工具标识
   */
  private record Owner(
      String scope,
      String actor,
      Set<String> declarations,
      List<SourceUnitRefRange> ranges,
      List<Candidate> inline,
      String parentName,
      String parentTool) {}

  /**
   * 输入只保存请求内指纹和安全摘要。
   *
   * @param id 工具标识
   * @param name 工具原名
   * @param fingerprint 请求内完整记录身份
   * @param preview 安全摘要
   * @param source 请求内源单元身份
   * @param valid 完整参数资格
   */
  private record Candidate(
      String id, String name, String fingerprint, String preview, String source, boolean valid) {}

  /**
   * 同一次聚合的覆盖与共享可选事实，旧载体仅作一致性匹配。
   *
   * @param total 输入识别数
   * @param measured 可信计时数
   * @param unknown 缺测数
   * @param other 其他口径数
   * @param nanos 精确累计
   * @param maximum 可选最大项
   */
  private record Result(
      long total,
      long measured,
      long unknown,
      long other,
      String nanos,
      SameInputMaximum maximum) {}

  /** 已确认 Agent 与原工具累计组的输入覆盖，不绑定一次委派。 */
  private static final class InputGroup {
    private boolean invalid;
    private long total;
    private final Map<String, Accumulator> inputs = new HashMap<>();
  }

  /** 单份完整参数记录的精确和及一个稳定安全代表。 */
  private static final class Accumulator {
    private long total;
    private long measured;
    private long unknown;
    private long other;
    private BigInteger nanos = BigInteger.ZERO;
    private ApiResponses.ToolExecutionSummary representative;

    private void add(ApiResponses.ToolExecutionSummary tool, String preview) {
      total++;
      var observation = tool.observation();
      if (observation == null || observation.durationNanos() == null) unknown++;
      else if (!"executor_reported".equals(observation.kind())
          || !observation.source().matches("codex:exec_command_end#event\\[[0-9]+\\]")) other++;
      else {
        measured++;
        nanos = nanos.add(BigInteger.valueOf(observation.durationNanos()));
        if (representative == null || IDENTITY.compare(tool, representative) < 0)
          representative = safe(tool, preview);
      }
    }
  }

  /** 独立使用本 occurrence 的已遮蔽摘要，不借裸标识预览。 */
  private static ApiResponses.ToolExecutionSummary safe(
      ApiResponses.ToolExecutionSummary tool, String preview) {
    return new ApiResponses.ToolExecutionSummary(
        tool.toolCallId(),
        tool.name(),
        tool.scope(),
        tool.declaredByCallId(),
        tool.status(),
        tool.exitCode(),
        tool.durationMs(),
        tool.subagentId(),
        preview,
        ToolInputPreview.executionKind(tool.name(), preview),
        tool.resultObserved(),
        tool.observation());
  }

  /**
   * 同完整参数记录调用的已测最大累计，属于父 Agent 组而非一次委派或任务。
   *
   * @param measuredWorkNanos 精确已测累计纳秒
   * @param totalTools 该参数记录调用总数
   * @param measuredTools 可信计时数
   * @param unknownTools 缺测数
   * @param otherKindTools 其他口径数
   * @param distinctInputs 父组不同完整参数记录数
   * @param identifiedInputs 父组已识别输入数
   * @param totalInputs 父组全部同名调用数
   * @param tool 完整身份与安全摘要代表，不承载任务成本
   */
  record SameInputMaximum(
      String measuredWorkNanos,
      long totalTools,
      long measuredTools,
      long unknownTools,
      long otherKindTools,
      long distinctInputs,
      long identifiedInputs,
      long totalInputs,
      ApiResponses.ToolExecutionSummary tool) {}
}
