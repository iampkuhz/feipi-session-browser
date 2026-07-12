package com.feipi.session.browser.cli.diagnose;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;

/** JSON 格式渲染器。 */
public final class JsonRenderer {

  private static final ObjectMapper MAPPER =
      new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

  private JsonRenderer() {}

  /**
   * 将诊断输出渲染为 JSON 字符串。
   *
   * @param output 诊断输出
   * @return 格式化的 JSON
   */
  public static String render(DiagnoseOutputModel.DiagnoseOutput output) {
    try {
      return MAPPER.writeValueAsString(output);
    } catch (JsonProcessingException e) {
      return "{\"error\": \"JSON 序列化失败: " + e.getMessage() + "\"}";
    }
  }
}
