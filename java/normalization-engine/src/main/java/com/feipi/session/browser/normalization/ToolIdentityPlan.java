package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** List 与惰性序列共用的无正文工具 occurrence 身份计划。 */
final class ToolIdentityPlan {
  private final List<Declaration> declarations = new ArrayList<>();
  private final Map<Slot, String> ids = new HashMap<>();
  private final Map<Long, Reference> observations = new LinkedHashMap<>();
  private final Set<Long> boundObservations = new HashSet<>();
  private final Map<Long, Reference> results = new LinkedHashMap<>();
  private final Map<Long, SourceRecordRelation> relations = new LinkedHashMap<>();
  private final Set<String> reserved = new HashSet<>();
  private final List<NormalizedSourceFile> files;
  private final Set<String> roots = new HashSet<>();
  private final Map<String, Set<String>> childOrigins = new HashMap<>();
  private final Map<Long, String> relationOrigins = new HashMap<>();
  private final Set<Long> rootSpawnSelfAnchors = new HashSet<>();
  private final Map<Long, String> rootSpawnResultAnchors = new HashMap<>();
  private final Map<ParentLookup, CandidateGroup> parentIndex = new HashMap<>();
  private final Map<ResolutionKey, SourceRecordRelation> resolvedParents = new HashMap<>();
  private final Map<SourceRecordRelation, Integer> diagnosticIndices = new HashMap<>();
  final List<Map<String, Object>> diagnostics = new ArrayList<>();

  ToolIdentityPlan(List<NormalizedSourceFile> files) {
    this.files = List.copyOf(files);
    for (var file : files) {
      String origin = origin(file.path().toString());
      if (file.role() == SourceFileRole.TRANSCRIPT) roots.add(origin);
      file.subagentId()
          .ifPresent(
              child -> childOrigins.computeIfAbsent(child, ignored -> new HashSet<>()).add(origin));
    }
  }

  static String origin(String locator) {
    String normalized = locator.replace('\\', '/');
    int suffix = normalized.lastIndexOf("#event[");
    return suffix < 0 ? normalized : normalized.substring(0, suffix);
  }

  static String associationScope(SourceRecord record) {
    String scope =
        CallBuilder.callScope(record) == com.feipi.session.browser.domain.enums.CallScope.MAIN
            ? ""
            : CallBuilder.displaySubagentId(record).orElse("");
    String origin = origin(record.locator());
    return origin.length() + ":" + origin + scope;
  }

  void accept(long ordinal, SourceRecord record) {
    String origin = origin(record.locator());
    String scope = associationScope(record);
    if ("assistant".equals(record.eventType())) {
      for (int i = 0; i < record.toolCalls().size(); i++) {
        var tool = record.toolCalls().get(i);
        declare(ordinal, i, origin, scope, tool.toolCallId(), tool.name(), record.relation());
      }
    } else if ("tool_use".equals(record.eventType())
        && record.callId().isPresent()
        && record.toolName().isPresent()) {
      declare(
          ordinal,
          -1,
          origin,
          scope,
          record.callId().get(),
          record.toolName().get(),
          record.relation());
      if (roots.contains(origin)
          && CallBuilder.callScope(record) == CallScope.MAIN
          && "spawn_agent".equals(record.toolName().get())
          && record.relation().parentToolCallId().equals(record.callId())) {
        rootSpawnSelfAnchors.add(ordinal);
      }
    }
    record
        .toolObservation()
        .ifPresent(value -> observations.put(ordinal, new Reference(scope, value.toolCallId())));
    record.toolCalls().forEach(tool -> reserved.add(tool.toolCallId()));
    record
        .toolUseId()
        .ifPresent(
            id -> {
              reserved.add(id);
              if ("tool_result".equals(record.eventType()))
                results.put(ordinal, new Reference(scope, id));
            });
    if (record.relation().parentToolCallId().isPresent()) {
      relations.put(ordinal, record.relation());
      relationOrigins.put(ordinal, origin);
      reserved.add(record.relation().parentToolCallId().get());
    }
  }

  private void declare(
      long ordinal,
      int index,
      String origin,
      String scope,
      String raw,
      String name,
      SourceRecordRelation relation) {
    reserved.add(raw);
    declarations.add(
        new Declaration(new Slot(ordinal, index), origin, scope, raw, name, relation.subagentId()));
  }

  void finish() {
    Map<String, Integer> counts = new HashMap<>();
    declarations.forEach(declaration -> counts.merge(declaration.raw(), 1, Integer::sum));
    Set<String> allocated = new HashSet<>(reserved);
    for (Declaration declaration : declarations) {
      String id = declaration.raw();
      if (counts.get(id) > 1) {
        String base =
            "normalized-tool:" + declaration.slot().ordinal() + ":" + declaration.slot().index();
        id = base;
        int suffix = 0;
        while (!allocated.add(id)) id = base + ":" + ++suffix;
      }
      if (!id.equals(declaration.raw())) ids.put(declaration.slot(), id);
    }
    Map<Reference, List<Declaration>> local = new HashMap<>();
    for (Declaration declaration : declarations)
      local
          .computeIfAbsent(
              new Reference(declaration.scope(), declaration.raw()), ignored -> new ArrayList<>())
          .add(declaration);
    // 观测不依赖物理顺序；仅唯一的同来源同 scope 声明可关联，重复裸 ID 不猜 occurrence。
    observations.forEach(
        (ordinal, reference) -> {
          var candidates = local.getOrDefault(reference, List.of());
          if (candidates.size() == 1) {
            var declaration = candidates.getFirst();
            ids.put(
                new Slot(ordinal, -3),
                id(declaration.slot().ordinal(), declaration.slot().index(), declaration.raw()));
            boundObservations.add(ordinal);
          }
        });
    observations.clear();
    results.forEach(
        (ordinal, reference) -> {
          var candidates = local.getOrDefault(reference, List.of());
          int low = 0;
          int high = candidates.size();
          while (low < high) {
            int middle = (low + high) >>> 1;
            if (candidates.get(middle).slot().ordinal() <= ordinal) low = middle + 1;
            else high = middle;
          }
          if (low > 0) {
            var declaration = candidates.get(low - 1);
            String canonical =
                id(declaration.slot().ordinal(), declaration.slot().index(), declaration.raw());
            if (!canonical.equals(reference.raw())) ids.put(new Slot(ordinal, -2), canonical);
            // 结果只继承同物理来源、同执行 scope 中实际匹配声明的根执行证据。
            // 不能按裸 provider id 或歧义的 child 父关系推测声明 occurrence。
            if (rootSpawnSelfAnchors.contains(declaration.slot().ordinal())) {
              var relation = relations.get(ordinal);
              if (relation != null
                  && relation.parentToolCallId().filter(reference.raw()::equals).isPresent()
                  && relation.parentToolName().filter("spawn_agent"::equals).isPresent()) {
                rootSpawnResultAnchors.put(ordinal, canonical);
              }
            }
          }
        });
    Set<String> parentIds = new HashSet<>();
    relations.values().forEach(relation -> relation.parentToolCallId().ifPresent(parentIds::add));
    files.forEach(file -> file.parentToolUseId().ifPresent(parentIds::add));
    for (Declaration declaration : declarations) {
      if (parentIds.contains(declaration.raw())) index(declaration);
    }
    relations.replaceAll(
        (ordinal, relation) -> {
          // 根来源执行的自身锚点属于该 occurrence；子代理选父的歧义不能改变执行作用域。
          // 此投影不进入共享关系缓存，避免相同原始关系的 child 记录借用根执行身份。
          if (rootSpawnSelfAnchors.contains(ordinal)) {
            String raw = relation.parentToolCallId().orElseThrow();
            return relation(relation, Optional.of(id(ordinal, -1, raw)), relation.parentCallId());
          }
          if (rootSpawnResultAnchors.containsKey(ordinal)) {
            return relation(
                relation,
                Optional.of(rootSpawnResultAnchors.get(ordinal)),
                relation.parentCallId());
          }
          return resolve(relation, relationOrigins.get(ordinal), true);
        });
    results.clear();
    reserved.clear();
    declarations.clear();
    relationOrigins.clear();
    rootSpawnSelfAnchors.clear();
    rootSpawnResultAnchors.clear();
  }

  private void index(Declaration declaration) {
    for (Optional<String> name :
        List.of(Optional.<String>empty(), Optional.of(declaration.name()))) {
      addCandidate(new ParentLookup(declaration.raw(), name, Optional.empty(), false), declaration);
      declaration
          .child()
          .ifPresent(
              child ->
                  addCandidate(
                      new ParentLookup(declaration.raw(), name, Optional.of(child), false),
                      declaration));
      if (roots.contains(declaration.origin())) {
        addCandidate(
            new ParentLookup(declaration.raw(), name, Optional.empty(), true), declaration);
      }
    }
  }

  private void addCandidate(ParentLookup key, Declaration declaration) {
    parentIndex.computeIfAbsent(key, ignored -> new CandidateGroup()).add(declaration);
  }

  private SourceRecordRelation resolve(
      SourceRecordRelation relation, String incomingOrigin, boolean diagnose) {
    if (relation.parentToolCallId().isEmpty()) return relation;
    boolean knownChildOrigin =
        relation
            .subagentId()
            .map(child -> !childOrigins.getOrDefault(child, Set.of()).isEmpty())
            .orElse(false);
    Optional<String> excludedIncoming =
        knownChildOrigin || roots.contains(incomingOrigin)
            ? Optional.empty()
            : Optional.of(incomingOrigin);
    var key = new ResolutionKey(relation, excludedIncoming);
    var resolved = resolvedParents.get(key);
    if (resolved == null) {
      resolved = selectParent(relation, incomingOrigin);
      resolvedParents.put(key, resolved);
    }
    if (diagnose && resolved.parentToolCallId().isEmpty()) {
      Integer index = diagnosticIndices.get(relation);
      long occurrences =
          index == null
              ? 1L
              : ((Number) diagnostics.get(index).get("occurrenceCount")).longValue() + 1L;
      var diagnostic =
          Map.<String, Object>of(
              "code",
              "UNRESOLVED_TOOL_PARENT",
              "severity",
              "WARNING",
              "message",
              "No unambiguous source declaration supports the parent tool relation",
              "occurrenceCount",
              occurrences);
      if (index == null) {
        diagnosticIndices.put(relation, diagnostics.size());
        diagnostics.add(diagnostic);
      } else diagnostics.set(index, diagnostic);
    }
    return resolved;
  }

  private SourceRecordRelation selectParent(SourceRecordRelation relation, String incomingOrigin) {
    String raw = relation.parentToolCallId().orElseThrow();
    Set<String> excluded =
        new HashSet<>(
            relation
                .subagentId()
                .map(child -> childOrigins.getOrDefault(child, Set.of()))
                .orElse(Set.of()));
    // 子代理继承的锚点不能证明它派生了自身；根锚点和其他已知来源的显式父声明仍可参与关联。
    if (excluded.isEmpty() && !roots.contains(incomingOrigin)) excluded.add(incomingOrigin);
    excluded.removeAll(roots);
    var explicit =
        parentIndex.get(
            new ParentLookup(raw, relation.parentToolName(), relation.subagentId(), false));
    CandidateSelection selection = select(explicit, excluded);
    if (relation.subagentId().isEmpty() || selection.count() == 0) {
      selection =
          select(
              parentIndex.get(
                  new ParentLookup(raw, relation.parentToolName(), Optional.empty(), true)),
              excluded);
      if (selection.count() == 0 && roots.isEmpty()) {
        selection =
            select(
                parentIndex.get(
                    new ParentLookup(raw, relation.parentToolName(), Optional.empty(), false)),
                excluded);
      }
    }
    if (selection.count() == 1)
      return relation(
          relation,
          Optional.of(id(selection.only().slot().ordinal(), selection.only().slot().index(), raw)),
          relation.parentCallId());
    return relation(relation, Optional.empty(), Optional.empty());
  }

  private static CandidateSelection select(CandidateGroup group, Set<String> excluded) {
    return group == null ? new CandidateSelection(0, null) : group.select(excluded);
  }

  private static SourceRecordRelation relation(
      SourceRecordRelation old, Optional<String> tool, Optional<String> call) {
    return new SourceRecordRelation(
        old.subagentId(), old.parentThreadId(), tool, call, old.parentToolName());
  }

  SourceRecordRelation relation(long ordinal, SourceRecordRelation fallback) {
    return relations.getOrDefault(ordinal, fallback);
  }

  String id(long ordinal, int index, String fallback) {
    return ids.getOrDefault(new Slot(ordinal, index), fallback);
  }

  String scope(
      long ordinal,
      String original,
      String type,
      Optional<String> callId,
      Optional<String> toolUseId,
      Optional<String> name,
      Optional<String> subagent) {
    var relation = relations.get(ordinal);
    if (relation == null || subagent.isEmpty()) return original;
    String self =
        "tool_use".equals(type)
            ? callId.map(raw -> id(ordinal, -1, raw)).orElse("")
            : toolUseId.map(raw -> id(ordinal, -2, raw)).orElse("");
    boolean parentSpawn =
        "spawn_agent".equals(name.or(() -> relation.parentToolName()).orElse(""))
            && relation.parentToolCallId().filter(self::equals).isPresent();
    int separator = original.indexOf(':');
    int length = Integer.parseInt(original.substring(0, separator));
    String originPrefix = original.substring(0, separator + 1 + length);
    return original.equals(originPrefix) && !parentSpawn ? originPrefix + subagent.get() : original;
  }

  List<NormalizedSourceFile> sourceFiles() {
    return files.stream()
        .map(
            file -> {
              var resolved =
                  resolve(
                      new SourceRecordRelation(
                          file.subagentId(),
                          Optional.empty(),
                          file.parentToolUseId(),
                          Optional.empty(),
                          Optional.empty()),
                      origin(file.path().toString()),
                      false);
              return new NormalizedSourceFile(
                  file.role(), file.path(), file.subagentId(), resolved.parentToolCallId());
            })
        .toList();
  }

  SourceRecord project(long ordinal, SourceRecord record) {
    String call = record.callId().orElse(null);
    if ("tool_use".equals(record.eventType()) && call != null) call = id(ordinal, -1, call);
    var tools = new ArrayList<SourceToolCall>();
    for (int i = 0; i < record.toolCalls().size(); i++) {
      var tool = record.toolCalls().get(i);
      String canonical =
          "tool_use".equals(record.eventType())
                  && record.callId().filter(tool.toolCallId()::equals).isPresent()
              ? id(ordinal, -1, tool.toolCallId())
              : id(ordinal, i, tool.toolCallId());
      tools.add(new SourceToolCall(canonical, tool.name(), tool.input()));
    }
    var result = record.toolUseId().map(raw -> id(ordinal, -2, raw));
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        record.eventType(),
        Optional.ofNullable(call),
        record.model(),
        record.timestamp(),
        record.turnId(),
        record.usage(),
        tools,
        result,
        record.toolName(),
        record.toolError(),
        relation(ordinal, record.relation()),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing(),
        record.metaContext(),
        record.messageRole(),
        observation(ordinal, record.toolObservation()));
  }

  /** 只透传已唯一归属的观测，不制造声明或结果边。 */
  Optional<SourceToolObservation> observation(long ordinal, Optional<SourceToolObservation> value) {
    return boundObservations.contains(ordinal)
        ? value.map(item -> item.withToolCallId(id(ordinal, -3, item.toolCallId())))
        : Optional.empty();
  }

  SourceRecordSequence borrow(SourceRecordSequence source) {
    return new SourceRecordSequence() {
      @Override
      public long recordCount() {
        return source.recordCount();
      }

      @Override
      public RecordCursor openCursor(long ordinal) throws IOException {
        return new ProjectingCursor(source.openCursor(ordinal), ordinal);
      }

      @Override
      public void close() {
        /* 仅借用序列，源生命周期仍由调用方负责。 */
      }
    };
  }

  /** 接管单个借用游标的关闭责任，不关闭其所属源序列。 */
  private final class ProjectingCursor implements SourceRecordSequence.RecordCursor {
    private final SourceRecordSequence.RecordCursor delegate;
    private long position;

    private ProjectingCursor(SourceRecordSequence.RecordCursor delegate, long ordinal) {
      this.delegate = delegate;
      position = ordinal;
    }

    @Override
    public boolean hasNext() throws IOException {
      return delegate.hasNext();
    }

    @Override
    public SourceRecord next() throws IOException {
      return project(position++, delegate.next());
    }

    @Override
    public void close() throws IOException {
      delegate.close();
    }
  }

  /** 按物理来源聚合候选；排除子来源时无需遍历全部声明。 */
  private static final class CandidateGroup {
    private final Map<String, List<Declaration>> origins = new LinkedHashMap<>();
    private int count;

    void add(Declaration declaration) {
      origins.computeIfAbsent(declaration.origin(), ignored -> new ArrayList<>()).add(declaration);
      count++;
    }

    CandidateSelection select(Set<String> excluded) {
      int remaining = count;
      for (String origin : excluded) remaining -= origins.getOrDefault(origin, List.of()).size();
      if (remaining != 1) return new CandidateSelection(remaining, null);
      for (var entry : origins.entrySet()) {
        if (!excluded.contains(entry.getKey()))
          return new CandidateSelection(1, entry.getValue().getFirst());
      }
      throw new IllegalStateException("parent candidate count mismatch");
    }
  }

  /**
   * 声明在源序列中的位置和记录内工具序号。
   *
   * @param ordinal 源记录顺序号
   * @param index 记录内工具序号，独立声明使用负一
   */
  private record Slot(long ordinal, int index) {}

  /**
   * 同一来源作用域内的原始工具引用。
   *
   * @param scope 来源及调用作用域
   * @param raw 提供方原始工具标识
   */
  private record Reference(String scope, String raw) {}

  /**
   * 不含正文的工具声明及其显式子代理证据。
   *
   * @param slot 声明在源序列中的位置
   * @param origin 物理来源标识
   * @param scope 来源及调用作用域
   * @param raw 提供方原始工具标识
   * @param name 工具名称
   * @param child 显式派生的子代理标识
   */
  private record Declaration(
      Slot slot, String origin, String scope, String raw, String name, Optional<String> child) {}

  /**
   * 父声明索引键；名称和子代理为空时表示未施加该项约束。
   *
   * @param raw 提供方原始父工具标识
   * @param name 父工具名称约束
   * @param child 显式派生的子代理约束
   * @param rootOnly 是否仅考虑根来源声明
   */
  private record ParentLookup(
      String raw, Optional<String> name, Optional<String> child, boolean rootOnly) {}

  /**
   * 缺少子来源元数据时保留传入来源约束；已知子来源时共用同一排除集合。
   *
   * @param relation 待解析的父子关联
   * @param excludedIncomingOrigin 缺少子来源元数据时排除的传入来源
   */
  private record ResolutionKey(
      SourceRecordRelation relation, Optional<String> excludedIncomingOrigin) {}

  /**
   * 候选数量及唯一候选；非唯一时不持有任意候选以免静默选父。
   *
   * @param count 符合约束的候选数量
   * @param only 唯一候选，非唯一时为空
   */
  private record CandidateSelection(int count, Declaration only) {}
}
