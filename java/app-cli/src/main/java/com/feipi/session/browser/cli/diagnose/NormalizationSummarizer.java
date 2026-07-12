package com.feipi.session.browser.cli.diagnose;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.List;

/** 从 {@link NormalizedSessionArtifact} 生成归一化摘要。 */
final class NormalizationSummarizer {

  private NormalizationSummarizer() {}

  /**
   * 统计归一化制品的结构信息。
   *
   * @param artifact 归一化制品
   * @return 归一化摘要
   */
  static DiagnoseOutputModel.NormalizationInfo summarize(NormalizedSessionArtifact artifact) {
    List<NormalizedCall> calls = artifact.calls();
    List<NormalizedToolExecution> toolExecutions = artifact.toolExecutions();

    int mainCalls = 0;
    int subagentCalls = 0;
    for (NormalizedCall call : calls) {
      if (call.scope() == CallScope.MAIN) {
        mainCalls++;
      } else {
        subagentCalls++;
      }
    }

    long totalTokens = 0;
    for (NormalizedCall call : calls) {
      totalTokens += call.usage().total();
    }

    return new DiagnoseOutputModel.NormalizationInfo(
        "OBSERVED",
        artifact.schemaVersion(),
        calls.size(),
        mainCalls,
        subagentCalls,
        toolExecutions.size(),
        artifact.diagnostics().size(),
        totalTokens,
        artifact.sourceFiles().size());
  }
}
