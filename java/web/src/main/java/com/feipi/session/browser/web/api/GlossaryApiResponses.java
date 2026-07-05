package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import java.util.List;
import java.util.Objects;

/** static glossary contracts 的类型化 JSON 响应。 */
public final class GlossaryApiResponses {

  private GlossaryApiResponses() {}

  /**
   * 表示 GlossarySummaryResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param tokenTypeCount token 类型数量。
   * @param derivedMetricCount 衍生指标数量。
   * @param providerMappingCount provider 映射数量。
   * @param roundSignalCount round signal 数量。
   * @param state 页面或 API 状态描述。
   */
  public record GlossarySummaryResponse(
      String schemaVersion,
      long tokenTypeCount,
      long derivedMetricCount,
      long providerMappingCount,
      long roundSignalCount,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public GlossarySummaryResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      Objects.requireNonNull(state, "state must not be null");
      if (tokenTypeCount < 0
          || derivedMetricCount < 0
          || providerMappingCount < 0
          || roundSignalCount < 0) {
        throw new IllegalArgumentException("glossary counts must be non-negative");
      }
    }
  }

  /**
   * 表示 GlossarySectionResponse 数据。
   *
   * @param schemaVersion 响应 schema 版本号。
   * @param section 术语 section 名称。
   * @param count 数量。
   * @param terms 术语列表。
   * @param state 页面或 API 状态描述。
   */
  public record GlossarySectionResponse(
      String schemaVersion,
      String section,
      long count,
      List<GlossaryTermDto> terms,
      PageStateDto state) {

    /** 校验字段和业务不变量。 */
    public GlossarySectionResponse {
      schemaVersion = schemaVersion == null ? ApiResponses.SCHEMA_VERSION : schemaVersion;
      section = ApiResponses.required(section, "section");
      Objects.requireNonNull(terms, "terms must not be null");
      Objects.requireNonNull(state, "state must not be null");
      terms = List.copyOf(terms);
      if (count < 0) {
        throw new IllegalArgumentException("count must be non-negative");
      }
      if (count != terms.size()) {
        throw new IllegalArgumentException("count must equal term size");
      }
    }
  }

  /**
   * 表示 GlossaryTermDto 数据。
   *
   * @param key 该字段在 API 响应中的业务值。
   * @param label 用户可读标签。
   * @param definition 该字段在 API 响应中的业务值。
   * @param formula 该字段在 API 响应中的业务值。
   * @param providerFields 该字段在 API 响应中的业务值。
   */
  public record GlossaryTermDto(
      String key, String label, String definition, String formula, List<String> providerFields) {

    /** 校验字段和业务不变量。 */
    public GlossaryTermDto {
      key = ApiResponses.required(key, "key");
      label = ApiResponses.required(label, "label");
      definition = ApiResponses.required(definition, "definition");
      formula = formula == null ? "" : formula;
      providerFields = providerFields == null ? List.of() : List.copyOf(providerFields);
    }
  }
}
