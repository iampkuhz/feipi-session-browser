package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import java.io.IOException;
import java.util.List;
import java.util.Map;

/** 统一旧制品扫描与有界内容扫描的候选元数据覆盖顺序，保持完整会话信息一致。 */
final class CandidateContentMetadata {
  private CandidateContentMetadata() {}

  /** 补充完整逻辑会话的候选元数据，不把所有内容单元合并成完整列表。 */
  static void apply(
      Map<String, Object> session,
      Candidate candidate,
      SourceAdapter adapter,
      NormalizedSessionContent content)
      throws IOException {
    Map<String, String> meta = candidate.metadata();
    session.putAll(TokenProvenance.fromMetadata(meta).toMetadata());

    putStringIfAbsent(session, "title", meta.get("title"));
    putStringIfAbsent(session, "model", meta.get("model"));
    putStringIfAbsent(session, "git_branch", meta.get("git_branch"));
    putStringIfAbsent(
        session, "source", meta.getOrDefault("source", adapter.sourceId().getValue()));

    String cwd = meta.getOrDefault("cwd", "");
    if (!cwd.isBlank()) {
      session.put("cwd", cwd);
      if (FullScanEngine.isMeaningfulProject(cwd)) {
        session.put("project_key", cwd);
      }
    }
    String projectKey = stringValue(session.get("project_key"));
    if (!projectKey.isBlank()) {
      session.put("project_name", projectName(projectKey));
    }

    Summary summary = summarize(content);
    boolean hasMaterializedSubagentRecords = summary.hasSubagent();
    TokenComponents base = tokenComponentsFromSessionOrCalls(session, summary.tokens());
    TokenComponents direct =
        new TokenComponents(
            longMeta(meta, "freshInputTokens"),
            longMeta(meta, "cacheReadTokens"),
            longMeta(meta, "cacheWriteTokens"),
            longMeta(meta, "outputTokens"));
    TokenComponents subagent =
        new TokenComponents(
            longMeta(meta, "subagentFreshInputTokens"),
            longMeta(meta, "subagentCacheReadTokens"),
            longMeta(meta, "subagentCacheWriteTokens"),
            longMeta(meta, "subagentOutputTokens"));
    if (direct.total() > 0) {
      putTokenComponents(session, direct);
    } else if (subagent.total() > 0 && !hasMaterializedSubagentRecords) {
      putTokenComponents(session, base.plus(subagent));
    }

    long directTotal = longMeta(meta, "totalTokens");
    if (directTotal > 0) {
      session.put("totalTokens", directTotal);
    }
    long subagentTotal = longMeta(meta, "subagentTotalTokens");
    if (subagentTotal > 0
        && direct.total() == 0
        && subagent.total() == 0
        && !hasMaterializedSubagentRecords) {
      long baseTotal = numberValue(session.get("totalTokens"));
      session.put("totalTokens", baseTotal + subagentTotal);
    }

    long subagentTools = longMeta(meta, "subagentToolCallCount");
    if (subagentTools > 0 && !hasMaterializedSubagentRecords) {
      long baseTools =
          session.get("toolCallCount") instanceof Number num
              ? num.longValue()
              : content.header().totals().get("toolExecutions");
      session.put("toolCallCount", baseTools + subagentTools);
    }

    long subagentFailed = longMeta(meta, "subagentFailedToolCount");
    if (subagentFailed > 0 && !hasMaterializedSubagentRecords) {
      long baseFailed = numberValue(session.get("failedToolCount"));
      session.put("failedToolCount", baseFailed + subagentFailed);
    }

    long subagentInstances = longMeta(meta, "subagentInstanceCount");
    if (subagentInstances > 0) {
      session.put("subagentInstanceCount", subagentInstances);
    }
  }

  private static Summary summarize(NormalizedSessionContent content) throws IOException {
    boolean hasSubagent = false;
    TokenComponents tokens = new TokenComponents(0, 0, 0, 0);
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        tokens = tokens.plus(tokenComponents(unit.calls()));
        hasSubagent |= unit.calls().stream().anyMatch(call -> call.scope() == CallScope.SUBAGENT);
        hasSubagent |=
            unit.toolExecutions().stream()
                .anyMatch(
                    tool -> tool.scope() == CallScope.SUBAGENT || tool.subagentId().isPresent());
        hasSubagent |=
            unit.sourceFiles().stream()
                .anyMatch(
                    file ->
                        file.subagentId().isPresent()
                            || file.path().toString().replace('\\', '/').contains("/subagents/"));
      }
    }
    return new Summary(hasSubagent, tokens);
  }

  /**
   * 只保留扫描汇总所需的紧凑元数据，不持有包含正文的内容单元。
   *
   * @param hasSubagent 是否观察到子代理来源或调用
   * @param tokens 跨所有内容单元累计的用量分量
   */
  private record Summary(boolean hasSubagent, TokenComponents tokens) {}

  private static void putStringIfAbsent(Map<String, Object> session, String key, String value) {
    if (value == null || value.isBlank()) {
      return;
    }
    Object existing = session.get(key);
    if (existing == null || existing.toString().isBlank()) {
      session.put(key, value);
    }
  }

  private static void putTokenComponents(Map<String, Object> session, TokenComponents components) {
    session.put("freshInputTokens", components.freshInputTokens());
    session.put("cacheReadTokens", components.cacheReadTokens());
    session.put("cacheWriteTokens", components.cacheWriteTokens());
    session.put("outputTokens", components.outputTokens());
    session.put("totalTokens", components.total());
  }

  private static TokenComponents tokenComponents(List<NormalizedCall> calls) {
    long fresh = 0;
    long cacheRead = 0;
    long cacheWrite = 0;
    long output = 0;
    for (NormalizedCall call : calls) {
      fresh += call.usage().fresh();
      cacheRead += call.usage().cacheRead();
      cacheWrite += call.usage().cacheWrite();
      output += call.usage().output();
    }
    return new TokenComponents(fresh, cacheRead, cacheWrite, output);
  }

  private static TokenComponents tokenComponentsFromSessionOrCalls(
      Map<String, Object> session, TokenComponents calls) {
    if (hasTokenOverride(session)) {
      return new TokenComponents(
          numberValue(session.get("freshInputTokens")),
          numberValue(session.get("cacheReadTokens")),
          numberValue(session.get("cacheWriteTokens")),
          numberValue(session.get("outputTokens")));
    }
    return calls;
  }

  private static boolean hasTokenOverride(Map<String, Object> session) {
    return session.get("freshInputTokens") instanceof Number
        || session.get("cacheReadTokens") instanceof Number
        || session.get("cacheWriteTokens") instanceof Number
        || session.get("outputTokens") instanceof Number;
  }

  private static long longMeta(Map<String, String> meta, String key) {
    String value = meta.get(key);
    if (value == null || value.isBlank()) {
      return 0;
    }
    try {
      return Math.max(0, Long.parseLong(value));
    } catch (NumberFormatException e) {
      return 0;
    }
  }

  private static long numberValue(Object value) {
    return value instanceof Number num ? num.longValue() : 0;
  }

  private static String stringValue(Object value) {
    return value == null ? "" : value.toString();
  }

  private static String projectName(String projectKey) {
    if (projectKey == null || projectKey.isBlank()) {
      return "";
    }
    int lastSlash = projectKey.lastIndexOf('/');
    if (lastSlash >= 0 && lastSlash < projectKey.length() - 1) {
      return projectKey.substring(lastSlash + 1);
    }
    return projectKey;
  }

  /**
   * 表示 token 组件汇总数据，用于保存输入、cache 与输出 token 数量。
   *
   * @param freshInputTokens 当前统计口径下的 fresh input token 数量。
   * @param cacheReadTokens 当前统计口径下的 cache read token 数量。
   * @param cacheWriteTokens 当前统计口径下的 cache write token 数量。
   * @param outputTokens 当前统计口径下的 output token 数量。
   */
  private record TokenComponents(
      /* 当前统计口径下的 fresh input token 数量。 */
      long freshInputTokens,

      /* 当前统计口径下的 cache read token 数量。 */
      long cacheReadTokens,

      /* 当前统计口径下的 cache write token 数量。 */
      long cacheWriteTokens,

      /* 当前统计口径下的 output token 数量。 */
      long outputTokens) {
    private long total() {
      return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    }

    private TokenComponents plus(TokenComponents other) {
      return new TokenComponents(
          freshInputTokens + other.freshInputTokens,
          cacheReadTokens + other.cacheReadTokens,
          cacheWriteTokens + other.cacheWriteTokens,
          outputTokens + other.outputTokens);
    }
  }
}
