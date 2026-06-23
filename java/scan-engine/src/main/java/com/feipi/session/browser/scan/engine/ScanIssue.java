package com.feipi.session.browser.scan.engine;

import java.util.Objects;

/**
 * 扫描过程中遇到的单个问题。
 *
 * <p>记录候选项处理失败的原因和上下文，用于 {@link ScanSummary} 报告。
 *
 * @param sessionKey 相关会话键，空字符串表示非候选项级别的问题
 * @param sourceValue 源适配器协议值
 * @param phase 问题发生的阶段
 * @param message 问题描述
 */
public record ScanIssue(String sessionKey, String sourceValue, ScanPhase phase, String message) {

  /**
   * 紧凑构造器，验证非 null。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public ScanIssue {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(sourceValue, "sourceValue 不得为 null");
    Objects.requireNonNull(phase, "phase 不得为 null");
    Objects.requireNonNull(message, "message 不得为 null");
  }

  /**
   * 问题发生的扫描阶段。
   *
   * <p>标识候选项处理管线中哪个环节产生了问题。
   */
  public enum ScanPhase {
    /** 根目录安全检查阶段。 */
    ROOT_CHECK,
    /** 候选项发现阶段。 */
    DISCOVERY,
    /** 源解析阶段。 */
    PARSE,
    /** 归一化阶段。 */
    NORMALIZE,
    /** 制品写入阶段。 */
    ARTIFACT_WRITE,
    /** 索引写入阶段。 */
    INDEX_WRITE
  }
}
