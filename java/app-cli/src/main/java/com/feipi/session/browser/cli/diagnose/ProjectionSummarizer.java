package com.feipi.session.browser.cli.diagnose;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * 从归一化制品生成轻量投影摘要。
 *
 * <p>该投影不依赖 index，直接从 {@link NormalizedSessionArtifact} 提取结构信息， 等价于 Web/查询层在无 index 场景下的最小结构视图。
 */
final class ProjectionSummarizer {

  private ProjectionSummarizer() {}

  /**
   * 从归一化制品生成投影摘要。
   *
   * @param artifact 归一化制品
   * @return 投影摘要
   */
  static DiagnoseOutputModel.ProjectionInfo summarize(NormalizedSessionArtifact artifact) {
    List<NormalizedCall> calls = artifact.calls();
    List<NormalizedToolExecution> toolExecutions = artifact.toolExecutions();

    // 检测到的 agent 数量：主 agent 算 1，每个唯一 subagent 再各算 1
    Set<String> subagentIds = new LinkedHashSet<>();
    int mainToolCalls = 0;
    int subagentToolCalls = 0;

    for (NormalizedCall call : calls) {
      if (call.scope() == CallScope.MAIN) {
        // 主 agent 的 tool call 数量
        mainToolCalls += call.response().toolCallIds().size();
      } else {
        // 子 agent 的 tool call 数量
        subagentToolCalls += call.response().toolCallIds().size();
        call.subagentId().ifPresent(subagentIds::add);
      }
    }

    // 从 toolExecutions 补充统计（如果 calls 中没有 toolCallIds）
    if (mainToolCalls == 0 && subagentToolCalls == 0 && !toolExecutions.isEmpty()) {
      // 回退：使用 toolExecutions 总数作为 main tool call count
      mainToolCalls = toolExecutions.size();
    }

    int detectedAgents = subagentIds.isEmpty() ? 1 : 1 + subagentIds.size();

    return new DiagnoseOutputModel.ProjectionInfo(
        "OBSERVED",
        detectedAgents,
        subagentIds.size(),
        mainToolCalls,
        subagentToolCalls,
        calls.size());
  }
}
