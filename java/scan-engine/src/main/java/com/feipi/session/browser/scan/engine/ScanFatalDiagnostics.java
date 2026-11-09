package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.ScanFailure;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** JVM 致命错误的有界、可分享诊断。只输出类型和代码栈帧，不展开 Throwable 文本。 */
public final class ScanFatalDiagnostics {
  private static final Logger LOG = LoggerFactory.getLogger(ScanFatalDiagnostics.class);
  private static final ThreadLocal<WeakReference<Error>> REPORTED = new ThreadLocal<>();
  private static final int MAX_FRAMES = 8;

  private final String mode;
  private String phase = "ARTIFACT_PREPARE";
  private String source = "";
  private long scanLogId;
  private ScanFailure failure;
  private boolean jvmErrorReported;

  ScanFatalDiagnostics(String mode) {
    this.mode = mode;
  }

  void at(String phase, String source) {
    this.phase = phase;
    this.source = source;
  }

  void scanStarted(long scanLogId) {
    this.scanLogId = scanLogId;
  }

  long scanLogId() {
    return scanLogId;
  }

  ScanIssue setupFailure(ScanIssue.ScanPhase scanPhase, String code, Exception error) {
    failure = new ScanFailure("", "", scanPhase.name(), code, 0);
    LOG.error(
        "扫描阶段失败 mode={} scanLogId={} phase={} code={} exception={} hint={}",
        mode,
        scanLogId,
        phase,
        code,
        error.getClass().getName(),
        ScanDiagnostics.hint(code));
    return new ScanIssue("", "", scanPhase, "", code);
  }

  /** 在 CLI 或调度边界报告引擎之外的 Error，同一个 Error 不重复报告。 */
  public static void reportAtBoundary(Error error, String mode, String phase) {
    var previous = REPORTED.get();
    if (previous != null && previous.refersTo(error)) return;
    var diagnostic = new ScanFatalDiagnostics(mode);
    diagnostic.at(phase, "");
    diagnostic.report(error);
  }

  /** 入口结束时释放线程持有的致命异常引用。 */
  public static void clearReported() {
    REPORTED.remove();
  }

  void report(Error error) {
    if (jvmErrorReported) return;
    String code =
        switch (error) {
          case OutOfMemoryError ignored -> "SCAN_JVM_OUT_OF_MEMORY";
          case StackOverflowError ignored -> "SCAN_JVM_STACK_OVERFLOW";
          case LinkageError ignored -> "SCAN_JVM_LINKAGE_ERROR";
          default -> "SCAN_JVM_FATAL";
        };
    failure = new ScanFailure(source, "", phase, code, 0);
    LOG.error(
        "扫描致命错误 severity=FATAL mode={} scanLogId={} source={} phase={} code={}"
            + " exception={} causes={} frames={} hint={}",
        mode,
        scanLogId,
        source,
        phase,
        code,
        error.getClass().getName(),
        causeTypes(error),
        frames(error),
        ScanDiagnostics.hint(code));
    REPORTED.set(new WeakReference<>(error));
    jvmErrorReported = true;
  }

  List<ScanFailure> failures() {
    return failure == null ? List.of(ScanFailure.generic()) : List.of(failure);
  }

  boolean hasReportedJvmError() {
    return jvmErrorReported;
  }

  private static List<String> causeTypes(Error error) {
    var types = new ArrayList<String>();
    Throwable cause = error.getCause();
    while (cause != null && types.size() < 4) {
      types.add(cause.getClass().getName());
      cause = cause.getCause();
    }
    return types;
  }

  private static List<String> frames(Error error) {
    var frames = new ArrayList<String>();
    for (StackTraceElement frame : error.getStackTrace()) {
      if (frames.size() == MAX_FRAMES) break;
      String symbol = frame.getClassName() + "." + frame.getMethodName();
      if (symbol.matches("[A-Za-z0-9_.$<>]{1,240}")) {
        frames.add(symbol + ":" + frame.getLineNumber());
      }
    }
    return frames;
  }
}
