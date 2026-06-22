package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * 单次调用的请求侧工具结果边。
 *
 * <p>建模一次 LLM 调用请求侧消费的工具结果标识符列表。语义构建器存储轻量级边标识符，
 * 制品模型将该对象视为不可变的调用输入元数据。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code toolResultIds} 使用不可变副本，大小不超过 {@link NormalizedConstants#MAX_COLLECTION_SIZE}。
 * </ul>
 *
 * @param toolResultIds 该 LLM 请求消费的工具调用标识符列表，按归一化源顺序排列
 */
@DomainModel
public record NormalizedCallRequest(List<String> toolResultIds) {

  /**
   * 紧凑构造器，执行防御性拷贝和大小约束。
   *
   * @throws IllegalArgumentException 当列表超过大小上限时
   */
  public NormalizedCallRequest {
    List<String> copy =
        toolResultIds == null ? Collections.emptyList() : List.copyOf(toolResultIds);
    if (copy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "toolResultIds size " + copy.size() + " exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    toolResultIds = copy;
  }

  /**
   * 创建空请求。
   *
   * @return 无工具结果边的空请求实例
   */
  public static NormalizedCallRequest empty() {
    return new NormalizedCallRequest(Collections.emptyList());
  }
}
