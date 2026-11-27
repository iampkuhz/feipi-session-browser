package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/** 当前不可变内容读取器的惰性局部投影；只保存有界身份和位置，不保存正文。 */
final class LocalToolResultProjection {
  private static final int MAX_ITEMS = 16_384;
  private static final int MAX_REFS = 65_536;
  private static final long MAX_METADATA = 4_194_304;
  private final NormalizedSessionContent content;
  private final Map<String, Call> calls = new HashMap<>();
  private final Map<String, String> payloadCalls = new HashMap<>();
  private final Map<String, List<Candidate>> toolOccurrences = new HashMap<>();
  private final Map<String, Candidate> occurrenceIds = new HashMap<>();
  private final Map<String, Tool> tools = new HashMap<>();
  private final Map<String, Candidate> catalog = new LinkedHashMap<>();
  private final Map<String, Map<Long, String>> sequences = new HashMap<>();
  private final Map<String, Candidate> occurrences = new LinkedHashMap<>();
  private final Map<String, List<Reference>> inputs = new LinkedHashMap<>();
  private final Set<String> duplicateCalls = new HashSet<>();
  private final Set<String> duplicateTools = new HashSet<>();
  private String reason = "";
  private final Set<String> sourcePaths = new TreeSet<>();
  private String scope = "";
  private boolean scopeComplete;
  private String scopeIssue = "missing_content_scope";
  private int sourceFileCount;
  private boolean budgetExceeded;
  private boolean qualified;
  private long metadata;
  private int expanded;
  private int callCount;
  private int toolCount;
  private int catalogCount;
  private long sequenceCount;
  private boolean metadataComplete;
  private String metadataIssue = "";

  private LocalToolResultProjection(NormalizedSessionContent content) {
    this.content = content;
  }

  static LocalToolResultProjection build(NormalizedSessionContent content) throws IOException {
    var projection = new LocalToolResultProjection(content);
    projection.collect();
    projection.checkMetadataCounts();
    for (var candidate : projection.catalog.values()) {
      if (candidate.result) projection.occurrences.put("source:" + candidate.key, candidate);
    }
    projection.buildScope();
    if (projection.reason.isEmpty()) {
      projection.references();
      projection.qualified =
          !projection.budgetExceeded && projection.scopeComplete && projection.metadataComplete;
      projection.checkContexts();
    }
    projection.indexOccurrences();
    if (!projection.scopeComplete && projection.reason.isEmpty())
      projection.reason = projection.scopeIssue;
    if (!projection.metadataComplete && !projection.budgetExceeded) {
      projection.reason =
          projection.metadataIssue + (projection.reason.isEmpty() ? "" : ";" + projection.reason);
    }
    return projection;
  }

  private boolean strings(String... values) {
    for (String value : values) {
      metadata += value.length();
      if (value.length() > 1024 || metadata > MAX_METADATA) {
        reason = "metadata_string_budget";
        budgetExceeded = true;
        return false;
      }
    }
    return true;
  }

  private boolean referenceBudget() {
    if (++expanded > MAX_REFS) {
      reason = "reference_budget";
      budgetExceeded = true;
      return false;
    }
    return true;
  }

  private void collect() throws IOException {
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext() && reason.isEmpty()) {
        var unit = cursor.next();
        for (var source : unit.sourceFiles()) {
          if (++sourceFileCount > MAX_ITEMS) {
            reason = "source_scope_budget";
            budgetExceeded = true;
            return;
          }
          String path = source.path().toString();
          if (!strings(path)) return;
          sourcePaths.add(path);
        }
        for (var call : unit.calls()) {
          if (++callCount > MAX_ITEMS) {
            reason = "call_budget";
            budgetExceeded = true;
            return;
          }
          var value = Call.of(call);
          if (!strings(
              value.id(),
              value.context(),
              value.payload(),
              Integer.toString(value.recordIndex()),
              value.scope())) return;
          if (calls.putIfAbsent(call.callId(), value) != null) duplicateCalls.add(call.callId());
          payloadCalls.put(value.payload(), value.id());
        }
        for (var tool : unit.toolExecutions()) {
          if (++toolCount > MAX_ITEMS) {
            reason = "tool_budget";
            budgetExceeded = true;
            return;
          }
          var value = Tool.of(tool);
          if (!strings(tool.toolCallId(), value.name(), value.owner(), value.context())) return;
          if (tools.putIfAbsent(tool.toolCallId(), value) != null)
            duplicateTools.add(tool.toolCallId());
        }
        for (var chunk : unit.sourceUnitSequences()) {
          if (!strings(chunk.name())) return;
          var positions = sequences.computeIfAbsent(chunk.name(), ignored -> new HashMap<>());
          for (int i = 0; i < chunk.keys().size(); i++) {
            String key = chunk.keys().get(i);
            sequenceCount++;
            if (!referenceBudget() || !strings(key)) return;
            long position = chunk.offset() + i;
            if (positions.putIfAbsent(position, key) != null) {
              reason = "conflicting_sequence";
              return;
            }
          }
        }
        for (var entry : unit.sourceUnitCatalog().values()) {
          if (++catalogCount > MAX_ITEMS) {
            reason = "catalog_budget";
            budgetExceeded = true;
            return;
          }
          if (!strings(
              entry.unitKey(),
              entry.unitType(),
              entry.originPath(),
              entry.canonicalSourceLocator(),
              entry.label().orElse(""))) return;
          var source = entry.payload() instanceof Map<?, ?> map ? map : Map.of();
          String tool = PayloadCallContentExtractor.toolResultId(source);
          if (!strings(tool)) return;
          boolean result = PayloadCallContentExtractor.isToolResult(entry.unitType());
          boolean request = "request".equals(entry.direction().getValue());
          String text = result ? PayloadCallContentExtractor.catalogEntryText(entry) : "";
          var candidate =
              new Candidate(
                  entry.unitKey(),
                  tool,
                  sourceOrder(entry),
                  entry.unitKey(),
                  -1,
                  -1,
                  result && request,
                  entry.text().isPresent() || hasText(entry.payload()),
                  digest(text));
          if (result
              && (!request
                  || !PayloadCallContentExtractor.isToolResult(source.get("type"))
                  || entry.label().filter(label -> !label.equals(tool)).isPresent())) {
            candidate.ambiguous = true;
          }
          if (entry.unitKey().startsWith("tool-result:")
              && (sourceOrder(entry) == Long.MAX_VALUE
                  || !entry.unitKey().endsWith(":" + entry.canonicalSourceLocator())
                  || !"tool_result".equals(entry.unitType()))) candidate.ambiguous = true;
          if (!strings(candidate.id, candidate.digest)) return;
          var previous = catalog.putIfAbsent(entry.unitKey(), candidate);
          if (previous != null) previous.ambiguous = true;
        }
      }
    }
  }

  private void references() throws IOException {
    int ordinal = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext() && !budgetExceeded) {
        for (var call : cursor.next().calls()) {
          int callOrdinal = ordinal++;
          var list = inputs.computeIfAbsent(call.callId(), ignored -> new ArrayList<>());
          long position = 0;
          var explicit = new HashMap<String, List<Reference>>();
          for (var range : call.sourceUnitRefRanges()) {
            if (!referenceBudget()) return;
            if (!range.refs().isEmpty() || range.sequence().isEmpty()) {
              for (String key : range.refs()) {
                if (!referenceBudget() || !strings(key)) return;
                addReference(call, key, position++, list, explicit);
              }
            } else {
              if (!strings(range.sequence().orElseThrow())) return;
              var sequence = sequences.get(range.sequence().orElseThrow());
              for (long i = range.start(); i < range.end(); i++) {
                if (!referenceBudget()) return;
                String key = sequence == null ? null : sequence.get(i);
                if (key == null) {
                  addReference(
                      call,
                      "missing-sequence:" + range.sequence().orElseThrow() + ":" + i,
                      position++,
                      list,
                      explicit);
                  reason = "missing_sequence_position";
                } else addReference(call, key, position++, list, explicit);
              }
            }
          }
          for (int index = 0; index < call.sourceUnits().size(); index++) {
            var source = call.sourceUnits().get(index);
            if (!referenceBudget()) return;
            if (!PayloadCallContentExtractor.isToolResult(source.get("type"))) continue;
            String tool = PayloadCallContentExtractor.toolResultId(source);
            String key = source.get("result_source_unit_key") instanceof String value ? value : "";
            if (!strings(tool, key)) return;
            String text =
                PayloadCallContentExtractor.resolveInline(List.of(source), null, null, null);
            boolean request =
                !"assistant".equals(source.get("role"))
                    && !"response".equals(source.get("direction"));
            if (!request) continue;
            String identityKey = key.isEmpty() ? "inline:" + callOrdinal + ":" + index : key;
            var candidate = key.isEmpty() ? null : occurrences.get("source:" + identityKey);
            if (candidate == null) {
              if (key.isEmpty() && !strings(identityKey)) return;
              candidate =
                  new Candidate(
                      identityKey,
                      tool,
                      sourceOrderKey(key, catalogCount + expanded),
                      "",
                      callOrdinal,
                      index,
                      true,
                      hasText(source),
                      digest(text));
              candidate.anchored = !key.isEmpty();
              if (!strings(candidate.id, candidate.digest)) return;
              occurrences.put(key.isEmpty() ? identityKey : "source:" + identityKey, candidate);
            } else if (!candidate.tool.equals(tool)
                || !candidate.digest.equals(digest(text))
                || candidate.present != hasText(source)) {
              candidate.ambiguous = true;
            }
            // 同一 call 中 catalog/inline 镜像只抵消相同次数，额外重复仍保留。
            var mirrors = explicit.get(identityKey);
            if (mirrors != null && !mirrors.isEmpty()) mirrors.removeFirst();
            else {
              var reference = new Reference(call.callId(), position++, candidate);
              if (!strings(reference.id)) return;
              list.add(reference);
            }
          }
        }
      }
    }
  }

  private void checkContexts() {
    for (var list : inputs.values()) {
      for (var reference : list) {
        var tool = tools.get(reference.candidate.tool);
        var call = calls.get(reference.call);
        if (duplicateCalls.contains(reference.call)
            || (tool != null
                && !expectedContext(tool).isEmpty()
                && !expectedContext(tool).equals(call.context()))) {
          reference.candidate.ambiguous = true;
        }
      }
    }
  }

  private static long sourceOrder(SourceUnitCatalogEntry entry) {
    return sourceOrderKey(entry.unitKey(), ((long) entry.eventOrder() << 32) + entry.partIndex());
  }

  private static long sourceOrderKey(String key, long fallback) {
    String prefix = "tool-result:";
    if (key.startsWith(prefix)) {
      int separator = key.indexOf(':', prefix.length());
      if (separator > 0) {
        try {
          long ordinal = Long.parseLong(key.substring(prefix.length(), separator));
          if (ordinal >= 0) return ordinal;
        } catch (NumberFormatException invalid) {
          return Long.MAX_VALUE;
        }
      }
    }
    return fallback;
  }

  private void addReference(
      NormalizedCall call,
      String key,
      long position,
      List<Reference> list,
      Map<String, List<Reference>> explicit) {
    if (!strings(key)) return;
    var candidate = catalog.get(key);
    if (candidate == null) {
      reason = "missing_catalog_reference";
      candidate = new Candidate(key, "", expanded, "", -1, -1, true, false, digest(""));
      candidate.anchored = false;
      if (!strings(candidate.id, candidate.digest)) return;
      catalog.put(key, candidate);
      occurrences.put("source:" + key, candidate);
    }
    if (!candidate.result) return;
    var reference = new Reference(call.callId(), position, candidate);
    if (!strings(reference.id)) return;
    list.add(reference);
    explicit.computeIfAbsent(key, ignored -> new ArrayList<>()).add(reference);
  }

  boolean belongsToPayload(String payload, String occurrenceId) {
    var candidate = occurrenceIds.get(occurrenceId);
    if (candidate == null) return false;
    if (!candidate.tool.isBlank() && payload.equals("tool:result:" + candidate.tool)) return true;
    return inputs.getOrDefault(callForPayload(payload), List.of()).stream()
        .anyMatch(reference -> reference.candidate.id.equals(occurrenceId) && confirmed(reference));
  }

  PayloadLookup.LocalResults read(
      String payload, long cursor, int limit, String target, PayloadVisibility visibility)
      throws IOException {
    return read(payload, cursor, limit, target, visibility, null);
  }

  PayloadLookup.LocalResults read(
      String payload,
      long cursor,
      int limit,
      String target,
      PayloadVisibility visibility,
      ExportPayloadLookup bulk)
      throws IOException {
    validate(cursor, limit);
    var selected = new ArrayList<Candidate>();
    boolean tool = payload.startsWith("tool:result:");
    // 保留原始请求和工具级结果；不把未关联到已记录工具的正文混入请求阅读区。
    var references =
        tool
            ? List.<Reference>of()
            : inputs.getOrDefault(callForPayload(payload), List.of()).stream()
                .filter(
                    ref ->
                        tools.containsKey(ref.candidate.tool)
                            || ref.candidate.tool.isEmpty() && !ref.candidate.present)
                .toList();
    if (!tool && !payloadCalls.containsKey(payload))
      throw new IllegalArgumentException("Exact request or tool result payload required");
    if (tool) {
      String id = payload.substring("tool:result:".length());
      if (!tools.containsKey(id) && !toolOccurrences.containsKey(id))
        throw new IllegalArgumentException("Unknown tool result payload");
      selected.addAll(toolOccurrences.getOrDefault(id, List.of()));
    } else references.forEach(reference -> selected.add(reference.candidate));
    long start = cursor;
    if (target != null && !target.isEmpty()) {
      int found = -1;
      for (int i = 0; i < selected.size(); i++) {
        String id = tool ? selected.get(i).id : references.get(i).id;
        if (id.equals(target)) {
          found = i;
          break;
        }
      }
      if (found < 0) throw new IllegalArgumentException("Unknown local result target");
      start = (long) (found / limit) * limit;
    }
    int from = (int) Math.min(start, selected.size());
    int end = Math.min(selected.size(), from + limit);
    var page = selected.subList(from, end);
    var texts = readContents(page, visibility, bulk);
    var items = new ArrayList<PayloadLookup.LocalResultOccurrence>();
    var refs = new ArrayList<PayloadLookup.InputResultReference>();
    for (int i = from; i < end; i++) {
      var item = selected.get(i);
      String identity = identity(item);
      var body = texts.getOrDefault(item.id, missing());
      if (tool) {
        var execution = tools.get(item.tool);
        String name = execution == null ? "" : execution.name();
        items.add(
            new PayloadLookup.LocalResultOccurrence(
                item.id,
                SensitiveFieldPolicy.fromVisibility(visibility).applyMasking(item.tool),
                SensitiveFieldPolicy.fromVisibility(visibility).applyMasking(name),
                item.order,
                identity,
                body));
      } else {
        var reference = references.get(i);
        var call = calls.get(reference.call);
        boolean confirmed = confirmed(reference);
        refs.add(
            new PayloadLookup.InputResultReference(
                reference.id,
                confirmed ? item.id : "",
                SensitiveFieldPolicy.fromVisibility(visibility).applyMasking(item.tool),
                SensitiveFieldPolicy.fromVisibility(visibility)
                    .applyMasking(tools.containsKey(item.tool) ? tools.get(item.tool).name() : ""),
                reference.call,
                call.context(),
                reference.position,
                confirmed ? "confirmed" : identity.equals("confirmed") ? "unconfirmed" : identity,
                body));
      }
    }
    return new PayloadLookup.LocalResults(
        items, refs, start, end < selected.size() ? (long) end : null, coverage(), reason);
  }

  PayloadLookup.LocalResultRelations relations(
      String occurrenceId, long cursor, int limit, String target) {
    validate(cursor, limit);
    Candidate candidate = occurrenceIds.get(occurrenceId);
    if (candidate == null) throw new IllegalArgumentException("Unknown local result occurrence");
    var targets = new ArrayList<PayloadLookup.ResultTarget>();
    for (var ref : candidate.references) {
      if (!confirmed(ref)) continue;
      var call = calls.get(ref.call);
      targets.add(
          new PayloadLookup.ResultTarget(
              call.id(),
              call.context(),
              call.payload(),
              ref.id,
              ref.id,
              call.recordIndex(),
              call.scope()));
    }

    long start = cursor;
    if (target != null && !target.isEmpty()) {
      int found = -1;
      for (int i = 0; i < targets.size(); i++)
        if (targets.get(i).target().equals(target)) found = i;
      if (found < 0) throw new IllegalArgumentException("Unknown local result target");
      start = (long) (found / limit) * limit;
    }
    int from = (int) Math.min(start, targets.size());
    int end = Math.min(targets.size(), from + limit);
    String identity = identity(candidate);
    String why =
        !reason.isEmpty() ? reason : identity.equals("confirmed") ? "" : "unconfirmed_identity";
    return new PayloadLookup.LocalResultRelations(
        targets.subList(from, end),
        start,
        end < targets.size() ? (long) end : null,
        why.isEmpty() ? "complete" : targets.isEmpty() ? "unknown" : "partial",
        why,
        identity);
  }

  private void checkMetadataCounts() {
    var actual = new LinkedHashMap<String, Long>();
    actual.put("calls", (long) callCount);
    actual.put("toolExecutions", (long) toolCount);
    actual.put("sourceUnitCatalog", (long) catalogCount);
    actual.put("sourceUnitSequenceEntries", sequenceCount);
    var mismatches = new ArrayList<String>();
    for (var entry : actual.entrySet()) {
      if (!entry.getValue().equals(content.header().totals().getOrDefault(entry.getKey(), -1L)))
        mismatches.add(entry.getKey());
    }
    metadataComplete = mismatches.isEmpty();
    if (!metadataComplete) metadataIssue = "incomplete_metadata:" + String.join(",", mismatches);
  }

  private void buildScope() {
    Object raw = content.header().session().get("session_key");
    String key = raw == null ? "" : raw.toString();
    String agent = content.header().agent().getValue();
    if (!strings(agent, key)) return;
    var fields = new ArrayList<String>();
    fields.add("scope:v1");
    fields.add(agent);
    fields.add(key);
    fields.addAll(sourcePaths);
    scope = identityId(fields);
    strings(scope);
    boolean sourcesComplete = sourceFileCount == content.header().totals().get("sourceFiles");
    if (!sourcesComplete) scopeIssue = "incomplete_source_scope";
    scopeComplete =
        !budgetExceeded
            && reason.isEmpty()
            && sourcesComplete
            && (!key.isBlank() || !sourcePaths.isEmpty());
  }

  private void indexOccurrences() {
    var identities = new HashMap<String, List<String>>();
    for (var candidate : occurrences.values()) {
      var tool = tools.get(candidate.tool);
      var fields =
          List.of(
              "occurrence:v1",
              scope,
              candidate.anchored ? "source" : "unconfirmed-position",
              candidate.tool,
              tool == null ? "" : tool.name(),
              tool == null ? "" : tool.owner(),
              tool == null ? "" : expectedContext(tool),
              candidate.key);
      candidate.id = checkedIdentity(fields, identities);
      if (occurrenceIds.putIfAbsent(candidate.id, candidate) != null)
        throw new IllegalStateException("Duplicate complete occurrence identity");
      toolOccurrences.computeIfAbsent(candidate.tool, ignored -> new ArrayList<>()).add(candidate);
    }
    for (var list : inputs.values()) {
      for (var reference : list) {
        var call = calls.get(reference.call);
        String position = Long.toString(reference.position);
        strings(position);
        reference.id =
            checkedIdentity(
                List.of(
                    "reference:v1",
                    scope,
                    reference.candidate.id,
                    reference.call,
                    call == null ? "" : call.context(),
                    call == null ? "" : call.payload(),
                    position),
                identities);
      }
    }
    for (var list : toolOccurrences.values()) {
      list.sort(
          java.util.Comparator.comparingLong((Candidate item) -> item.order)
              .thenComparing(item -> item.key));
    }
    if (budgetExceeded) qualified = false;
  }

  private String checkedIdentity(List<String> fields, Map<String, List<String>> identities) {
    String id = identityId(fields);
    var previous = identities.putIfAbsent(id, fields);
    if (previous != null && !previous.equals(fields))
      throw new IllegalStateException("Opaque complete identity collision");
    strings(id);
    return id;
  }

  private static String identityId(List<String> fields) {
    var digest = sha256();
    for (String field : fields) digest.update(component(field).getBytes(StandardCharsets.UTF_8));
    return "lr_" + Base64.getUrlEncoder().withoutPadding().encodeToString(digest.digest());
  }

  private String callForPayload(String payload) {
    return payloadCalls.getOrDefault(payload, "");
  }

  private String identity(Candidate candidate) {
    if (candidate.ambiguous || duplicateTools.contains(candidate.tool)) return "ambiguous";
    var tool = tools.get(candidate.tool);
    if (!qualified || !candidate.anchored || tool == null) return "unconfirmed";
    if (!"unknown".equals(tool.owner())) {
      var owner = calls.get(tool.owner());
      if (owner == null
          || duplicateCalls.contains(tool.owner())
          || !owner.context().startsWith(tool.context())) return "ambiguous";
    }
    return expectedContext(tool).isEmpty() ? "unconfirmed" : "confirmed";
  }

  private boolean confirmed(Reference reference) {
    var call = calls.get(reference.call);
    var tool = tools.get(reference.candidate.tool);
    return identity(reference.candidate).equals("confirmed")
        && call != null
        && !duplicateCalls.contains(reference.call)
        && expectedContext(tool).equals(call.context());
  }

  private String expectedContext(Tool tool) {
    var owner = "unknown".equals(tool.owner()) ? null : calls.get(tool.owner());
    if (owner != null) return owner.context();
    return tool.context().equals("main|") ? "main|0:0:0:" : "";
  }

  private String coverage() {
    return reason.isEmpty() ? "complete" : "unknown";
  }

  private Map<String, PayloadLookup.ResultContent> readContents(
      List<Candidate> page, PayloadVisibility visibility, ExportPayloadLookup bulk)
      throws IOException {
    var selected = new HashMap<String, List<Candidate>>();
    var inline = new HashMap<Integer, List<Candidate>>();
    var unique = new LinkedHashMap<String, Candidate>();
    page.forEach(candidate -> unique.put(candidate.id, candidate));
    for (var candidate : unique.values()) {
      if (!candidate.catalogKey.isEmpty())
        selected.computeIfAbsent(candidate.catalogKey, ignored -> new ArrayList<>()).add(candidate);
      else
        inline.computeIfAbsent(candidate.callOrdinal, ignored -> new ArrayList<>()).add(candidate);
    }
    var result = new HashMap<String, PayloadLookup.ResultContent>();
    if (page.isEmpty()) return result;
    var policy = SensitiveFieldPolicy.fromVisibility(visibility);
    if (bulk != null) {
      for (var candidate : unique.values()) {
        putContent(
            result,
            candidate,
            bulk.localResultText(
                candidate.catalogKey, candidate.callOrdinal, candidate.sourceIndex),
            policy);
      }
      return result;
    }
    int ordinal = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        for (var entry : unit.sourceUnitCatalog().values()) {
          for (var candidate : selected.getOrDefault(entry.unitKey(), List.of())) {
            String text = PayloadCallContentExtractor.catalogEntryText(entry);
            putContent(result, candidate, text, policy);
          }
        }
        for (var call : unit.calls()) {
          for (var candidate : inline.getOrDefault(ordinal, List.of())) {
            String text =
                PayloadCallContentExtractor.resolveInline(
                    List.of(call.sourceUnits().get(candidate.sourceIndex)), null, null, null);
            putContent(result, candidate, text, policy);
          }
          ordinal++;
        }
      }
    }
    return result;
  }

  private static void putContent(
      Map<String, PayloadLookup.ResultContent> result,
      Candidate candidate,
      String text,
      SensitiveFieldPolicy policy) {
    // 冻结来源核验失败不能任选首条/末条正文。
    if (candidate.ambiguous || !candidate.present || !candidate.digest.equals(digest(text))) {
      result.put(candidate.id, missing());
    } else {
      result.put(
          candidate.id,
          new PayloadLookup.ResultContent("available", policy.applyMasking(text), false));
    }
  }

  private static PayloadLookup.ResultContent missing() {
    return new PayloadLookup.ResultContent("missing", "", false);
  }

  private static boolean hasText(Object value) {
    if (value instanceof String) return true;
    if (!(value instanceof Map<?, ?> map)) return false;
    return List.of("text", "content", "output").stream()
        .map(map::get)
        .anyMatch(item -> item instanceof String || item instanceof List<?>);
  }

  private static String digest(String value) {
    return java.util.HexFormat.of()
        .formatHex(sha256().digest(value.getBytes(StandardCharsets.UTF_8)));
  }

  private static MessageDigest sha256() {
    try {
      return MessageDigest.getInstance("SHA-256");
    } catch (NoSuchAlgorithmException exception) {
      throw new IllegalStateException("Required SHA-256 unavailable", exception);
    }
  }

  private static void validate(long cursor, int limit) {
    if (cursor < 0 || limit < 1 || limit > 100)
      throw new IllegalArgumentException("cursor must be nonnegative; limit within 1..100");
  }

  private static String context(NormalizedCall call) {
    return call.scope().getValue()
        + "|"
        + component(call.subagentId().orElse(""))
        + component(call.parentCallId().orElse(""))
        + component(call.parentToolCallId().orElse(""));
  }

  private static String component(String value) {
    return value.length() + ":" + value;
  }

  /** 来源描述仅驻留当前投影；正文摘要仅校验同源镜像，不进入可重建句柄。 */
  private static final class Candidate {
    private String id = "";
    private final String key;
    private final String tool;
    private final long order;
    private final String catalogKey;
    private final int callOrdinal;
    private final int sourceIndex;
    private final boolean result;
    private final boolean present;
    private final String digest;
    private final List<Reference> references = new ArrayList<>();
    private boolean anchored = true;
    private boolean ambiguous;

    private Candidate(
        String key,
        String tool,
        long order,
        String catalogKey,
        int callOrdinal,
        int sourceIndex,
        boolean result,
        boolean present,
        String digest) {
      this.key = key;
      this.tool = tool;
      this.order = order;
      this.catalogKey = catalogKey;
      this.callOrdinal = callOrdinal;
      this.sourceIndex = sourceIndex;
      this.result = result;
      this.present = present;
      this.digest = digest;
    }
  }

  /**
   * 不捕获原调用正文。
   *
   * @param id 调用标识
   * @param context 无歧义编码的执行上下文
   * @param payload 精确请求载荷标识
   * @param recordIndex 来自当前调用的本地模型记录编号
   * @param scope 来自当前调用枚举的安全作用域
   */
  private record Call(String id, String context, String payload, int recordIndex, String scope) {
    private static Call of(NormalizedCall call) {
      String prefix =
          call.scope() == com.feipi.session.browser.domain.enums.CallScope.MAIN ? "main" : "sa";
      return new Call(
          call.callId(),
          LocalToolResultProjection.context(call),
          prefix + ":req:" + call.callId(),
          call.callIndex(),
          call.scope().getValue());
    }
  }

  /**
   * 工具声明身份，不从 scalar consumer 补边。
   *
   * @param name 工具名称
   * @param owner 已记录的声明调用或 unknown
   * @param context 工具执行作用域，子 agent 身份取实际 owner 而非协作 child
   */
  private record Tool(String name, String owner, String context) {
    private static Tool of(NormalizedToolExecution tool) {
      return new Tool(tool.name(), tool.declaredByCallId(), tool.scope().getValue() + "|");
    }
  }

  /** 一个请求侧引用位置。 */
  private static final class Reference {
    private String id = "";
    private final String call;
    private final long position;
    private final Candidate candidate;

    private Reference(String call, long position, Candidate candidate) {
      this.call = call;
      this.position = position;
      this.candidate = candidate;
      candidate.references.add(this);
    }
  }
}
