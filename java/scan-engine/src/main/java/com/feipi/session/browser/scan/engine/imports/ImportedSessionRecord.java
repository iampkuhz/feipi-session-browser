package com.feipi.session.browser.scan.engine.imports;

import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.query.SessionRecord;
import java.util.function.ToLongFunction;

/**
 * 只在独立分析内使用的详情投影，不持有个人索引行。
 *
 * @param metadata 独立导入的身份与显示元数据
 * @param artifact 本次单文件分析的归一化制品
 */
record ImportedSessionRecord(ImportedSessionMetadata metadata, NormalizedSessionArtifact artifact)
    implements SessionRecord {
  @Override
  public TokenProvenance tokenProvenance() {
    return TokenProvenance.fromMetadata(artifact.session());
  }

  @Override
  public SessionTiming timing() {
    return SessionTiming.fromMetadata(artifact.session());
  }

  @Override
  public String sessionKey() {
    return "import:" + metadata.importId();
  }

  @Override
  public String agent() {
    return metadata.source().getValue();
  }

  @Override
  public String sessionId() {
    return metadata.originalSessionId().isEmpty()
        ? metadata.importId()
        : metadata.originalSessionId();
  }

  @Override
  public String title() {
    return metadata.filename();
  }

  @Override
  public String projectKey() {
    return "";
  }

  @Override
  public String projectName() {
    return "独立分析";
  }

  @Override
  public String cwd() {
    return "";
  }

  @Override
  public String startedAt() {
    return text("started_at");
  }

  @Override
  public String endedAt() {
    return text("ended_at");
  }

  @Override
  public double durationSeconds() {
    return number("duration_seconds").doubleValue();
  }

  @Override
  public double modelExecutionSeconds() {
    return number("modelExecutionSeconds").doubleValue();
  }

  @Override
  public double toolExecutionSeconds() {
    return number("toolExecutionSeconds").doubleValue();
  }

  @Override
  public String model() {
    return text("model");
  }

  @Override
  public String gitBranch() {
    return "";
  }

  @Override
  public String source() {
    return "imported";
  }

  @Override
  public long userMessageCount() {
    return number("userMessageCount").longValue();
  }

  @Override
  public long assistantMessageCount() {
    return number("assistantMessageCount").longValue();
  }

  @Override
  public long toolCallCount() {
    return number("toolCallCount").longValue();
  }

  @Override
  public long outputTokens() {
    return usage("outputTokens", NormalizedCallUsage::output);
  }

  @Override
  public long freshInputTokens() {
    return usage("freshInputTokens", NormalizedCallUsage::fresh);
  }

  @Override
  public long cacheReadTokens() {
    return usage("cacheReadTokens", NormalizedCallUsage::cacheRead);
  }

  @Override
  public long cacheWriteTokens() {
    return usage("cacheWriteTokens", NormalizedCallUsage::cacheWrite);
  }

  @Override
  public long totalTokens() {
    return usage("totalTokens", NormalizedCallUsage::total);
  }

  @Override
  public long failedToolCount() {
    return number("failedToolCount").longValue();
  }

  @Override
  public long subagentInstanceCount() {
    return artifact.calls().stream().flatMap(call -> call.subagentId().stream()).distinct().count();
  }

  @Override
  public double indexedAt() {
    return metadata.createdAt().toEpochMilli() / 1000.0;
  }

  @Override
  public double fileMtime() {
    return indexedAt();
  }

  @Override
  public String filePath() {
    return "imports/" + metadata.importId() + "/upload.jsonl";
  }

  private String text(String key) {
    Object value = artifact.session().get(key);
    return value instanceof String string ? string : "";
  }

  private Number number(String key) {
    Object value = artifact.session().get(key);
    return value instanceof Number number ? number : 0;
  }

  private long usage(String key, ToLongFunction<NormalizedCallUsage> component) {
    if (artifact.session().get(key) instanceof Number value) {
      return value.longValue();
    }
    return artifact.calls().stream().mapToLong(call -> component.applyAsLong(call.usage())).sum();
  }
}
