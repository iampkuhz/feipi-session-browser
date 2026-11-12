package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.IOException;
import java.util.List;
import java.util.Optional;
import java.util.function.Function;

/** 重放会话内容进行查询，仅保留有界结果窗口和紧凑轮次索引。 */
public final class SessionContentReader {
  private final NormalizedSessionContent content;
  private final ContentRoundIndex index;

  /** 为一个不可变内容快照创建读取器。 */
  public SessionContentReader(NormalizedSessionContent content, long observedUserMessages)
      throws IOException {
    this.content = java.util.Objects.requireNonNull(content, "content");
    this.index = ContentRoundIndex.build(content, observedUserMessages);
  }

  /** 返回覆盖完整逻辑会话的紧凑轮次索引。 */
  public ContentRoundIndex roundIndex() {
    return index;
  }

  /** 区分实际保留的无调用输入与仅有消息计数的缺失正文。 */
  public boolean hasObservedInput() throws IOException {
    if (content.header().totals().getOrDefault("calls", 0L) != 0) return false;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var entry : cursor.next().sourceUnitCatalog().values()) {
          if ("observed_user_message".equals(entry.candidate())
              && !PayloadCallContentExtractor.catalogEntryText(entry).isBlank()) return true;
        }
      }
    }
    return false;
  }

  /** 只为没有调用的观测轮提取短输入；完整正文仍由 round Request 按需读取。 */
  public String observedInputPreview() throws IOException {
    if (content.header().totals().getOrDefault("calls", 0L) != 0) return "";
    com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry first = null;
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var entry : units.next().sourceUnitCatalog().values()) {
          if (!"observed_user_message".equals(entry.candidate())) continue;
          String preview =
              PayloadCallContentExtractor.catalogPreview(
                  entry,
                  Optional.of("user"),
                  true,
                  content.header().agent()
                      == com.feipi.session.browser.domain.normalized.NormalizedAgent.CODEX);
          if (!preview.isEmpty()
              && (first == null
                  || PayloadCallContentExtractor.OBSERVED_INPUT_ORDER.compare(entry, first) < 0))
            first = entry;
        }
      }
    }
    return first == null
        ? ""
        : PayloadCallContentExtractor.catalogPreview(
            first,
            Optional.of("user"),
            true,
            content.header().agent()
                == com.feipi.session.browser.domain.normalized.NormalizedAgent.CODEX);
  }

  /** 按匹配成员的偏移量读取逻辑轮次，每页最多返回五百个成员。 */
  public Window<NormalizedCall> calls(int roundIndex, long cursor, int limit) throws IOException {
    return calls(roundIndex, cursor, limit, Function.identity());
  }

  /** 在遍历命中调用时立即投影，只保留元数据窗口；映射结果不得捕获调用正文。 */
  public <T> Window<T> calls(
      int roundIndex, long cursor, int limit, Function<? super NormalizedCall, ? extends T> project)
      throws IOException {
    java.util.Objects.requireNonNull(project, "project");
    validateWindow(cursor, limit);
    if (roundIndex < 1 || roundIndex > index.roundCount()) {
      throw new IllegalArgumentException("roundIndex out of range");
    }
    var items = new java.util.ArrayList<T>();
    long total = 0;
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var call : units.next().calls()) {
          if (index.roundIndexForCall(call.callId()).orElse(0) != roundIndex) continue;
          if (total >= cursor && items.size() < limit) items.add(project.apply(call));
          total++;
        }
      }
    }
    return window(items, total, cursor);
  }

  /** 按稳定的全局调用顺序读取请求和响应的来源元数据。 */
  public Window<PayloadSource> payloadSources(PayloadVisibility visibility, long cursor, int limit)
      throws IOException {
    validateWindow(cursor, limit);
    var items = new java.util.ArrayList<PayloadSource>();
    long total = 0;
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var call : units.next().calls()) {
          for (var source : SessionDetailAssembler.buildPayloadSources(List.of(call), visibility)) {
            if (total >= cursor && items.size() < limit) items.add(source);
            total++;
          }
        }
      }
    }
    return window(items, total, cursor);
  }

  /** 通过重放查找指定调用，包括旧制品根集合上限以外的调用。 */
  public Optional<NormalizedCall> findCall(String callId) throws IOException {
    java.util.Objects.requireNonNull(callId, "callId");
    try (var units = content.openCursor()) {
      while (units.hasNext()) {
        for (var call : units.next().calls()) {
          if (call.callId().equals(callId)) return Optional.of(call);
        }
      }
    }
    return Optional.empty();
  }

  /** 在完整会话内容中解析单个载荷，并应用所选的隐私策略。 */
  public Optional<PayloadLookup.PayloadEntry> payload(
      String payloadId, PayloadVisibility visibility) throws IOException {
    return new ContentPayloadReader(content, this).read(payloadId, visibility);
  }

  /** 解析已经读取的调用，不再遍历内容查找调用身份。 */
  public PayloadLookup.PayloadEntry payload(
      NormalizedCall call, boolean request, PayloadVisibility visibility) throws IOException {
    return new ContentPayloadReader(content, this).read(call, request, visibility);
  }

  /** 为一次完整导出建立固定一次重放的私有磁盘载荷索引；调用方必须关闭。 */
  public ExportPayloads exportPayloads() throws IOException {
    return new ExportPayloads(ExportPayloadLookup.build(content));
  }

  /** 导出专用的载荷访问器，不改变单项 API 的重放及优先级语义。 */
  public final class ExportPayloads implements AutoCloseable {
    private final ExportPayloadLookup lookup;
    private final ContentPayloadReader payloadReader;

    private ExportPayloads(ExportPayloadLookup lookup) {
      this.lookup = lookup;
      this.payloadReader = new ContentPayloadReader(content, SessionContentReader.this, lookup);
    }

    /** 解析当前调用，正文仅在本次单项读取期间物化。 */
    public PayloadLookup.PayloadEntry payload(
        NormalizedCall call, boolean request, PayloadVisibility visibility) throws IOException {
      return payloadReader.read(call, request, visibility);
    }

    /** 按全局工具身份随机读取输入或结果。 */
    public Optional<PayloadLookup.PayloadEntry> payload(String id, PayloadVisibility visibility)
        throws IOException {
      if (!id.startsWith("tool:"))
        throw new IllegalArgumentException("Export tool identity required");
      return payloadReader.read(id, visibility);
    }

    /** 删除本次导出的全部临时正文。 */
    @Override
    public void close() throws IOException {
      lookup.close();
    }
  }

  private static void validateWindow(long cursor, int limit) {
    if (cursor < 0 || limit < 1 || limit > 500) {
      throw new IllegalArgumentException("cursor must be nonnegative and limit within 1..500");
    }
  }

  private static <T> Window<T> window(List<T> items, long total, long cursor) {
    long end = Math.addExact(cursor, items.size());
    return new Window<>(items, total, end < total ? end : null);
  }

  /**
   * 有界查询窗口，包含当前页结果、完整匹配总数和下一页位置。
   *
   * @param items 当前页的有界结果列表，不代表完整匹配集合
   * @param total 当前查询范围内的精确匹配总数，不是当前页条数
   * @param nextCursor 下一页的匹配成员偏移量；没有后续结果时为空
   */
  public record Window<T>(List<T> items, long total, Long nextCursor) {
    /** 复制有界结果列表，防止外部修改窗口内容。 */
    public Window {
      items = List.copyOf(items);
    }
  }
}
