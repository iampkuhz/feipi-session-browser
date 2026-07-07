package com.feipi.session.browser.data.batch.protocol;

/** normalized batch NDJSON 协议常量。 */
public final class NormalizedBatchProtocol {

  /** 协议名称。 */
  public static final String PROTOCOL_NAME = "normalized-batch";

  /** 协议版本。 */
  public static final String PROTOCOL_VERSION = "1.0";

  /** 通用字段：协议名。 */
  public static final String FIELD_PROTOCOL = "protocol";

  /** 通用字段：版本。 */
  public static final String FIELD_VERSION = "version";

  /** 通用字段：记录类型。 */
  public static final String FIELD_TYPE = "type";

  /** 请求标识字段。 */
  public static final String FIELD_REQUEST_ID = "requestId";

  /** 源标识字段。 */
  public static final String FIELD_SOURCE_ID = "sourceId";

  /** 根路径字段。 */
  public static final String FIELD_ROOT_PATH = "rootPath";

  /** 总请求数字段。 */
  public static final String FIELD_TOTAL_REQUESTS = "totalRequests";

  /** 请求记录类型。 */
  public static final String TYPE_REQUEST = "request";

  /** 结束摘要记录类型。 */
  public static final String TYPE_END = "end";

  /** 处理成功状态。 */
  public static final String STATUS_SUCCESS = "success";

  /** 处理失败状态。 */
  public static final String STATUS_ERROR = "error";

  /** 跳过处理状态。 */
  public static final String STATUS_SKIPPED = "skipped";

  private NormalizedBatchProtocol() {}
}
