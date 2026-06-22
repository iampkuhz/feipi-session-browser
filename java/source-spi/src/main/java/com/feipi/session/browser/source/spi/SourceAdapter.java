package com.feipi.session.browser.source.spi;

import java.nio.file.Path;
import java.util.Optional;

/**
 * 会话源适配器 SPI 接口。
 *
 * <p>定义三种 agent 会话源（Claude Code、Codex、Qoder）的统一操作契约。 每个适配器实现负责从特定源发现候选会话、生成文件指纹和执行解析。
 *
 * <p>SPI 设计原则：
 *
 * <ul>
 *   <li>不泄漏 provider 特定载荷（如 Jackson {@code JsonNode}）。
 *   <li>批次处理层接收候选项（{@link Candidate}），而非原始根目录。
 *   <li>所有操作返回密封结果类型（{@link SourceResult}），禁止 null 返回值。
 *   <li>发现结果按确定性排序，通过 {@link BoundedStream} 限制大小。
 * </ul>
 *
 * <p>实现方必须保证：
 *
 * <ul>
 *   <li>{@link #discover(Path)} 对同一输入产生确定排序的结果。
 *   <li>{@link #fingerprint(Path)} 包含内容哈希作为 mtime 之外的一致性证据。
 *   <li>{@link #checkRoot(Path)} 检测符号链接和路径逃逸。
 * </ul>
 */
public interface SourceAdapter {

  /**
   * 返回该适配器处理的源标识。
   *
   * @return 非 null 的源标识
   */
  SourceId sourceId();

  /**
   * 检查源根目录的安全性和可用性。
   *
   * <p>实现必须检测符号链接跟踪、路径逃逸和只读状态。
   *
   * @param rootPath 待检查的根目录路径
   * @return 源根安全检查结果
   */
  SourceRoot checkRoot(Path rootPath);

  /**
   * 从源根目录发现候选会话。
   *
   * <p>返回按确定性排序的有界候选项流。排序规则由实现定义但必须一致。 目录不存在或为空时返回空的 {@link BoundedStream}。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  BoundedStream<Candidate> discover(Path rootPath);

  /**
   * 为指定源文件生成指纹。
   *
   * <p>指纹必须包含路径、源标识、文件大小和修改时间。 当实现支持内容哈希时，应填充 {@code contentHash} 字段， 使其作为 mtime 之外的独立一致性证据。
   *
   * @param filePath 源文件路径
   * @return 文件指纹
   */
  SourceFingerprint fingerprint(Path filePath);

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>解析结果封装为密封类型，明确区分成功、可重试、跳过和致命错误。 实现不得抛出异常来表示可预期的解析失败，应通过 {@link SourceResult} 返回。
   *
   * @param candidate 待解析的候选项
   * @param cancellation 可选的取消信号
   * @return 密封的解析结果
   */
  SourceResult parse(Candidate candidate, Optional<CancellationSignal> cancellation);

  /**
   * 取消信号接口。
   *
   * <p>用于在长时间解析操作中传递取消请求。
   */
  interface CancellationSignal {

    /**
     * 判断是否已请求取消。
     *
     * @return 已请求取消时返回 {@code true}
     */
    boolean isCancelled();
  }
}
