package com.feipi.session.browser.source.codex.db;

import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * {@link ThreadsDbReader} 的读取结果，包含线程数据和可选的诊断信息。
 *
 * <p>当 SQLite 读取成功时，{@link #threads()} 包含线程数据，{@link #diagnostic()} 为空。 当读取失败时（如数据库损坏、驱动缺失），{@link
 * #threads()} 为空列表， {@link #diagnostic()} 携带错误描述。
 *
 * <p>该类不可变，线程安全。
 *
 * @param threads Threads DB 线程列表。
 * @param diagnostic 诊断信息。
 */
public record ThreadsDbResult(
    /* Threads DB 线程列表 */
    @NotNull List<Map<String, String>> threads,
    /* 诊断信息 */
    Optional<SourceDiagnostic> diagnostic) {

  /** 紧凑构造器，验证不变量并防御性拷贝。 */
  public ThreadsDbResult {
    ValidationSupport.validateCanonicalConstructor(ThreadsDbResult.class, threads, diagnostic);
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
