package com.feipi.session.browser.index.api.imports;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import java.io.IOException;
import java.io.InputStream;
import java.util.Optional;

/** 单文件隔离分析端口；实现不得持有个人索引写端口。 */
public interface SessionImportPort extends AutoCloseable {

  /**
   * 从借用的输入流分析一个文件；输入流由调用者关闭。
   *
   * @param input 本次上传内容
   * @param filename 仅用于显示的客户端文件名
   * @param source 用户选择的来源
   * @return 独立导入结果
   * @throws IOException 输入或解析失败，安全错误使用 SessionImportException
   */
  ImportedSessionAnalysis create(InputStream input, String filename, NormalizedAgent source)
      throws IOException;

  /** 按随机导入标识查询，不回退到个人会话。 */
  Optional<ImportedSessionAnalysis> find(String importId);

  /** 删除一份导入并释放资源；不影响个人数据。 */
  boolean delete(String importId) throws IOException;

  /** 返回供边界展示与校验使用的资源策略。 */
  ImportLimits limits();

  /** 清理全部临时资源，停止后旧导入标识失效。 */
  @Override
  void close() throws IOException;
}
