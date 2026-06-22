package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.List;

/**
 * 单次调用的响应侧工具调用边。
 *
 * <p>建模一次 LLM 调用响应侧声明的工具调用标识符列表。语义构建器仅存储工具调用标识符，
 * 该模型是短生命周期的不可变传输对象，用于制品验证阶段。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code toolCallIds} 使用不可变副本，大小不超过 {@link NormalizedConstants#MAX_COLLECTION_SIZE}。
 * </ul>
 *
 * @param toolCallIds 该 LLM 响应声明的工具调用标识符列表，按归一化响应顺序排列
 */
@DomainModel
public record NormalizedCallResponse(List<String> toolCallIds) {

  /**
   * 紧凑构造器，执行防御性拷贝和大小约束。
   *
   * @throws IllegalArgumentException 当列表超过大小上限时
   */
  public NormalizedCallResponse {
    List<String> copy = toolCallIds == null ? Collections.emptyList() : List.copyOf(toolCallIds);
    if (copy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "toolCallIds size " + copy.size() + " exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    toolCallIds = copy;
  }

  /**
   * 创建空响应。
   *
   * @return 无工具调用边的空响应实例
   */
  public static NormalizedCallResponse empty() {
    return new NormalizedCallResponse(Collections.emptyList());
  }
}
