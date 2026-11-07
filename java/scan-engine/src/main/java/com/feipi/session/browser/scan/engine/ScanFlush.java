package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.IndexWriterPort;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 两种扫描共用的暂存刷写及进度反馈；不提交事务或发布索引。 */
final class ScanFlush {
  private static final Logger LOG = LoggerFactory.getLogger(ScanFlush.class);

  private ScanFlush() {}

  /** 刷写失败时保留阶段问题，由调用方统一回滚扫描；失败阶段不发送完成回调。 */
  static boolean flush(
      IndexWriterPort writer,
      ScanProgress progress,
      String phase,
      String source,
      List<ScanIssue> issues) {
    try {
      long started = System.nanoTime();
      if (progress != null) progress.onPhaseStart(phase);
      writer.flushPendingWrites();
      if (progress != null) progress.onPhaseEnd(phase, (System.nanoTime() - started) / 1_000_000);
      return true;
    } catch (RuntimeException error) {
      LOG.error("index writer {} 失败", phase, error);
      issues.add(
          new ScanIssue(
              "",
              source,
              ScanIssue.ScanPhase.INDEX_WRITE,
              error.getMessage() == null || error.getMessage().isBlank()
                  ? error.getClass().getName()
                  : error.getMessage()));
      return false;
    }
  }
}
