package com.feipi.session.browser.index.api.write;

/**
 * 安全的扫描失败定位信息，不承载原文、诊断 preview 或原始异常消息。
 *
 * @param source 源适配器标识
 * @param sessionKey 仅供本机数据库定位的会话键
 * @param phase 扫描阶段
 * @param code 稳定失败代码
 * @param line 源文件行号，未知为零
 */
public record ScanFailure(String source, String sessionKey, String phase, String code, int line) {
  /** 创建通用失败原因，确保异常收尾也有可解释的失败记录。 */
  public static ScanFailure generic() {
    return new ScanFailure("", "", "UNKNOWN", "SCAN_ABORTED", 0);
  }
}
