package com.feipi.session.browser.contracttest.shadow;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Shadow 对比器。
 *
 * <p>比较两条 {@link NormalizedSessionArtifact} 归一化结果，将差异分类为：
 *
 * <ul>
 *   <li>{@link ShadowDiffCategory#EXACT_MATCH} -- 完全一致
 *   <li>{@link ShadowDiffCategory#COMPATIBLE_DIFFERENCE} -- 兼容差异
 *   <li>{@link ShadowDiffCategory#BREAKING_DIFFERENCE} -- 破坏性差异
 *   <li>{@link ShadowDiffCategory#INCOMPARABLE} -- 无法比较
 * </ul>
 *
 * <p>对比策略：
 *
 * <ol>
 *   <li>前置检查：null 和 agent 一致性。不一致则 {@code INCOMPARABLE}。
 *   <li>结构检查：schema 版本、调用数量、工具执行数量。不一致则 {@code BREAKING_DIFFERENCE}。
 *   <li>内容检查：逐调用对比 callId、model、token 用量、工具关联。 关键字段不一致则 {@code BREAKING_DIFFERENCE}。
 *   <li>兼容差异检测：session 元数据顺序、诊断信息顺序、空值表示等。 只有这类差异时归类为 {@code COMPATIBLE_DIFFERENCE}。
 * </ol>
 */
public final class ShadowComparator {

  /** 防止实例化。 */
  private ShadowComparator() {}

  /**
   * 对比基线和候选两条归一化制品。
   *
   * @param baseline 基线制品（通常来自参考实现或 golden 期望值），不得为 null
   * @param candidate 候选制品（通常来自 Java 管线），不得为 null
   * @return 分类对比结果
   */
  public static ShadowComparisonResult compare(
      NormalizedSessionArtifact baseline, NormalizedSessionArtifact candidate) {

    if (baseline == null || candidate == null) {
      return ShadowComparisonResult.incomparable("一侧或两侧制品为 null");
    }

    // 1. 前置检查
    if (!Objects.equals(baseline.agent(), candidate.agent())) {
      return ShadowComparisonResult.incomparable(
          "agent 不一致: baseline=" + baseline.agent() + ", candidate=" + candidate.agent());
    }

    List<String> breakingDiffs = new ArrayList<>();
    List<String> compatibleDiffs = new ArrayList<>();

    // 2. Schema 版本
    if (!Objects.equals(baseline.schemaVersion(), candidate.schemaVersion())) {
      breakingDiffs.add(
          "schemaVersion 不一致: baseline="
              + baseline.schemaVersion()
              + ", candidate="
              + candidate.schemaVersion());
    }

    // 3. 调用数量
    int baselineCallCount = baseline.calls().size();
    int candidateCallCount = candidate.calls().size();
    if (baselineCallCount != candidateCallCount) {
      breakingDiffs.add(
          "调用数量不一致: baseline=" + baselineCallCount + ", candidate=" + candidateCallCount);
    }

    // 4. 工具执行数量
    int baselineToolCount = baseline.toolExecutions().size();
    int candidateToolCount = candidate.toolExecutions().size();
    if (baselineToolCount != candidateToolCount) {
      breakingDiffs.add(
          "工具执行数量不一致: baseline=" + baselineToolCount + ", candidate=" + candidateToolCount);
    }

    // 5. 逐调用对比（取两侧最小范围）
    int minCallCount = Math.min(baselineCallCount, candidateCallCount);
    for (int i = 0; i < minCallCount; i++) {
      compareCall(
          baseline.calls().get(i), candidate.calls().get(i), i, breakingDiffs, compatibleDiffs);
    }

    // 6. 逐工具执行对比
    int minToolCount = Math.min(baselineToolCount, candidateToolCount);
    for (int i = 0; i < minToolCount; i++) {
      compareToolExecution(
          baseline.toolExecutions().get(i),
          candidate.toolExecutions().get(i),
          i,
          breakingDiffs,
          compatibleDiffs);
    }

    // 7. Session 元数据对比
    compareSessionMetadata(baseline.session(), candidate.session(), breakingDiffs, compatibleDiffs);

    // 8. 诊断信息对比（仅检测数量差异，内容差异为兼容差异）
    int baselineDiagCount = baseline.diagnostics().size();
    int candidateDiagCount = candidate.diagnostics().size();
    if (baselineDiagCount != candidateDiagCount) {
      compatibleDiffs.add(
          "诊断数量差异: baseline=" + baselineDiagCount + ", candidate=" + candidateDiagCount);
    }

    // 9. 源文件对比
    if (baseline.sourceFiles().size() != candidate.sourceFiles().size()) {
      compatibleDiffs.add(
          "源文件数量差异: baseline="
              + baseline.sourceFiles().size()
              + ", candidate="
              + candidate.sourceFiles().size());
    }

    // 10. 分类汇总
    if (!breakingDiffs.isEmpty()) {
      List<String> allDiffs = new ArrayList<>(breakingDiffs);
      allDiffs.addAll(compatibleDiffs);
      return new ShadowComparisonResult(
          ShadowDiffCategory.BREAKING_DIFFERENCE,
          allDiffs,
          baselineCallCount,
          candidateCallCount,
          baselineToolCount,
          candidateToolCount);
    }

    if (!compatibleDiffs.isEmpty()) {
      return new ShadowComparisonResult(
          ShadowDiffCategory.COMPATIBLE_DIFFERENCE,
          compatibleDiffs,
          baselineCallCount,
          candidateCallCount,
          baselineToolCount,
          candidateToolCount);
    }

    return ShadowComparisonResult.exactMatch(baselineCallCount, baselineToolCount);
  }

  private static void compareCall(
      NormalizedCall baselineCall,
      NormalizedCall candidateCall,
      int index,
      List<String> breakingDiffs,
      List<String> compatibleDiffs) {

    // callId 是关键标识
    if (!Objects.equals(baselineCall.callId(), candidateCall.callId())) {
      breakingDiffs.add(
          "调用["
              + index
              + "] callId 不一致: "
              + baselineCall.callId()
              + " vs "
              + candidateCall.callId());
    }

    // model 是关键字段
    if (!Objects.equals(baselineCall.model(), candidateCall.model())) {
      compatibleDiffs.add(
          "调用[" + index + "] model 差异: " + baselineCall.model() + " vs " + candidateCall.model());
    }

    // callIndex 和 callKey 必须一致
    if (baselineCall.callIndex() != candidateCall.callIndex()) {
      breakingDiffs.add(
          "调用["
              + index
              + "] callIndex 不一致: "
              + baselineCall.callIndex()
              + " vs "
              + candidateCall.callIndex());
    }

    // Token 用量对比
    long baselineTotal = baselineCall.usage().total();
    long candidateTotal = candidateCall.usage().total();
    if (baselineTotal != candidateTotal) {
      breakingDiffs.add(
          "调用[" + index + "] token 总量不一致: " + baselineTotal + " vs " + candidateTotal);
    }

    // 工具引用对比
    int baselineToolIds = baselineCall.response().toolCallIds().size();
    int candidateToolIds = candidateCall.response().toolCallIds().size();
    if (baselineToolIds != candidateToolIds) {
      breakingDiffs.add(
          "调用[" + index + "] 响应工具引用数不一致: " + baselineToolIds + " vs " + candidateToolIds);
    }

    int baselineResultIds = baselineCall.request().toolResultIds().size();
    int candidateResultIds = candidateCall.request().toolResultIds().size();
    if (baselineResultIds != candidateResultIds) {
      breakingDiffs.add(
          "调用[" + index + "] 请求工具结果数不一致: " + baselineResultIds + " vs " + candidateResultIds);
    }
  }

  private static void compareToolExecution(
      NormalizedToolExecution baselineExec,
      NormalizedToolExecution candidateExec,
      int index,
      List<String> breakingDiffs,
      List<String> compatibleDiffs) {

    if (!Objects.equals(baselineExec.toolCallId(), candidateExec.toolCallId())) {
      breakingDiffs.add(
          "工具执行["
              + index
              + "] toolCallId 不一致: "
              + baselineExec.toolCallId()
              + " vs "
              + candidateExec.toolCallId());
    }

    if (!Objects.equals(baselineExec.name(), candidateExec.name())) {
      compatibleDiffs.add(
          "工具执行[" + index + "] name 差异: " + baselineExec.name() + " vs " + candidateExec.name());
    }

    if (!Objects.equals(baselineExec.declaredByCallId(), candidateExec.declaredByCallId())) {
      breakingDiffs.add(
          "工具执行["
              + index
              + "] declaredByCallId 不一致: "
              + baselineExec.declaredByCallId()
              + " vs "
              + candidateExec.declaredByCallId());
    }
  }

  private static void compareSessionMetadata(
      Map<String, Object> baselineSession,
      Map<String, Object> candidateSession,
      List<String> breakingDiffs,
      List<String> compatibleDiffs) {

    // 对比关键字段
    for (String key :
        List.of("totalTokens", "eventCount", "declaredTools", "executedTools", "consumedResults")) {
      Object baseVal = baselineSession.get(key);
      Object candVal = candidateSession.get(key);
      if (!Objects.equals(baseVal, candVal)) {
        if ("totalTokens".equals(key)
            || "declaredTools".equals(key)
            || "executedTools".equals(key)) {
          breakingDiffs.add("session." + key + " 不一致: " + baseVal + " vs " + candVal);
        } else {
          compatibleDiffs.add("session." + key + " 差异: " + baseVal + " vs " + candVal);
        }
      }
    }

    // agent 字段已由前置检查覆盖
  }
}
