package com.feipi.session.browser.source.codex;

import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * {@link ThreadsDbReader} 的读取结果，包含线程数据和可选的诊断信息。
 *
 * <p>当 SQLite 读取成功时，{@link #threads()} 包含线程数据，{@link #diagnostic()} 为空。 当读取失败时（如数据库损坏、驱动缺失），{@link
 * #threads()} 为空列表， {@link #diagnostic()} 携带错误描述。
 *
 * <p>该类不可变，线程安全。
 */
public record ThreadsDbResult(
    List<Map<String, String>> threads, Optional<SourceDiagnostic> diagnostic) {

  /** 紧凑构造器，验证不变量并防御性拷贝。 */
  public ThreadsDbResult {
    Objects.requireNonNull(threads, "threads 不得为 null");
    threads = List.copyOf(threads);
    diagnostic = diagnostic == null ? Optional.empty() : diagnostic;
  }

  /**
   * 判断读取是否成功（无诊断错误）。
   *
   * @return 成功时返回 {@code true}
   */
  public boolean isSuccess() {
    return diagnostic.isEmpty();
  }
}
