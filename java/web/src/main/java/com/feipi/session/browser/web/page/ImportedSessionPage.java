package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.web.model.PayloadVisibilityQuery;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/** 仅上传文件范围的入口与详情页面，不查询个人索引。 */
public final class ImportedSessionPage {

  private final ImportedSessionUseCase imports;
  private final PebbleEnvironment templates;
  private final SessionDetailPage detailPage;

  /**
   * 复用既有详情渲染器，但数据只由导入用例提供。
   *
   * @param imports 独立导入用例
   * @param templates 模板环境
   * @param detailPage 共用详情渲染器
   */
  public ImportedSessionPage(
      ImportedSessionUseCase imports, PebbleEnvironment templates, SessionDetailPage detailPage) {
    this.imports = Objects.requireNonNull(imports, "imports");
    this.templates = Objects.requireNonNull(templates, "templates");
    this.detailPage = Objects.requireNonNull(detailPage, "detailPage");
  }

  /** 渲染上传表单及当前资源/生命周期提示。 */
  public void handleIndex(Context ctx) {
    long maxFileBytes = imports.limits().maxFileBytes();
    ctx.html(
        templates.render(
            "import-session.html",
            new HashMap<>(
                Map.of(
                    "active_page",
                    "imports",
                    "import_max_bytes",
                    maxFileBytes,
                    "import_max_display",
                    formatMebibytes(maxFileBytes),
                    "import_lifetime_message",
                    "导入分析仅在当前服务运行期间保留，服务停止或重启后失效；不计入个人统计。"))));
  }

  private static String formatMebibytes(long bytes) {
    long mebibyte = 1024L * 1024;
    return bytes % mebibyte == 0
        ? (bytes / mebibyte) + " MiB"
        : String.format(Locale.ROOT, "%.1f MiB", bytes / (double) mebibyte);
  }

  /** 根据不透明导入标识渲染独立详情。 */
  public void handleDetail(Context ctx) {
    String id = ctx.pathParam("importId");
    var metadata = imports.find(id);
    var visibility = PayloadVisibilityQuery.parse(ctx);
    var detail = imports.getDetailContextWithAnomalies(id, visibility);
    if (metadata.isEmpty() || detail.isEmpty()) {
      ctx.status(HttpStatus.NOT_FOUND);
      ctx.attribute(
          "custom_error_html",
          templates.render(
              "404.html",
              new HashMap<>(
                  Map.of(
                      "error",
                      "导入不存在或已失效",
                      "active_page",
                      "imports",
                      "back_url",
                      "/imports",
                      "back_label",
                      "重新导入 JSONL"))));
      return;
    }
    detailPage.renderImported(
        ctx,
        detail.get().detail(),
        detail.get().anomalies(),
        id,
        metadata.get().filename(),
        visibility);
  }
}
