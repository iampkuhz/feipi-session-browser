package com.feipi.session.browser.application.imports;

import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.diagnostics.AnomalyDetector;
import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.ImportedSessionMetadata;
import com.feipi.session.browser.index.api.imports.SessionImportPort;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;
import java.util.Optional;

/** 独立导入应用用例，复用个人详情的纯装配逻辑但不接入个人仓库。 */
public final class ImportedSessionUseCase implements AutoCloseable {

  private final SessionImportPort imports;

  /**
   * 注入独立导入端口。
   *
   * @param imports 不持有个人写索引的分析端口
   */
  public ImportedSessionUseCase(SessionImportPort imports) {
    this.imports = Objects.requireNonNull(imports, "imports");
  }

  /** 从本次上传创建分析，返回不含正文或服务器路径的元信息。 */
  public ImportedSessionMetadata create(InputStream input, String filename, NormalizedAgent source)
      throws IOException {
    return imports.create(input, filename, source).metadata();
  }

  /** 查询独立导入的显示元信息。 */
  public Optional<ImportedSessionMetadata> find(String importId) {
    return imports.find(importId).map(analysis -> analysis.metadata());
  }

  /** 按导入标识和可见性装配既有详情上下文。 */
  public Optional<SessionDetailUseCase.DetailContext> getDetailContext(
      String importId, PayloadVisibility visibility) {
    Objects.requireNonNull(visibility, "visibility");
    return imports
        .find(importId)
        .map(
            analysis ->
                new SessionDetailUseCase.DetailContext(
                    SessionDetailAssembler.assemble(
                        analysis.sessionRow(),
                        analysis.artifact(),
                        visibility,
                        "import:" + analysis.metadata().importId(),
                        0),
                    analysis.artifact()));
  }

  /** 复用既有异常检测，为导入页面与 JSON API 提供完整上下文。 */
  public Optional<SessionDetailUseCase.AnnotatedDetailContext> getDetailContextWithAnomalies(
      String importId, PayloadVisibility visibility) {
    return getDetailContext(importId, visibility)
        .map(
            context ->
                new SessionDetailUseCase.AnnotatedDetailContext(
                    context.detail(),
                    AnomalyDetector.detect(context.detail().sessionRow()),
                    context.artifact()));
  }

  /** 删除单份独立分析。 */
  public boolean delete(String importId) throws IOException {
    return imports.delete(importId);
  }

  /** 返回上传和保留资源的策略。 */
  public ImportLimits limits() {
    return imports.limits();
  }

  /** 关闭服务并释放所有导入数据。 */
  @Override
  public void close() throws IOException {
    imports.close();
  }
}
