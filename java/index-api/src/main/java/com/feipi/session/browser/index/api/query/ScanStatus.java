package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.index.api.write.ScanFailure;
import java.util.List;

/**
 * 最新扫描的运行状态，与已发布索引代号独立。
 *
 * @param id 扫描日志标识
 * @param status running、success 或 failure
 * @param mode 扫描模式
 * @param startedAt 开始时间，epoch 秒
 * @param finishedAt 结束时间，尚未结束为未知
 * @param processedCount 本次已处理的候选项数，失败时没有发布
 * @param errorCount 本次失败原因数
 * @param failures 安全失败定位记录，包含仅供本机存储使用的会话键
 * @param publishedDataAvailable 是否已有成功发布的有效索引
 */
public record ScanStatus(
    long id,
    String status,
    String mode,
    double startedAt,
    Double finishedAt,
    int processedCount,
    int errorCount,
    List<ScanFailure> failures,
    boolean publishedDataAvailable) {
  /** 防御性复制失败列表。 */
  public ScanStatus {
    failures = List.copyOf(failures);
  }
}
