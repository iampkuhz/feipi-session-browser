package com.feipi.session.browser.web.api;

import com.feipi.session.browser.web.api.GlossaryApiResponses.GlossarySectionResponse;
import com.feipi.session.browser.web.api.GlossaryApiResponses.GlossarySummaryResponse;
import com.feipi.session.browser.web.api.GlossaryApiResponses.GlossaryTermDto;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import io.javalin.http.Context;
import java.util.List;

/** Token Glossary 页面的静态资源 API。 */
public final class GlossaryApiHandler {

  private static final List<GlossaryTermDto> TOKEN_TYPES =
      List.of(
          term("fresh", "Fresh", "互斥的新输入组件。", "Provider input - cache read", "input_tokens"),
          term(
              "cache_read",
              "Cache Read",
              "Provider/broker 上报的缓存命中输入 token。",
              "cache_read_input_tokens",
              "cached_tokens"),
          term(
              "cache_write",
              "Cache Write",
              "写入 provider prompt cache 的输入 token。",
              "cache_write_input_tokens",
              "cache_creation_input_tokens"),
          term("output", "Output", "模型可见输出 token。", "output_tokens", "completion_tokens"),
          term(
              "input_side_total",
              "Input-side Component Total",
              "所有输入侧 token 组件合计。",
              "Fresh + Cache Read + Cache Write"),
          term(
              "total_tokens",
              "Total Tokens",
              "输入侧组件合计加可见输出。",
              "Fresh + Cache Read + Cache Write + Output"));

  private static final List<GlossaryTermDto> DERIVED_METRICS =
      List.of(
          term(
              "cache_read_ratio",
              "Cache Read Ratio",
              "衡量 cache reuse health。",
              "Cache Read / Input-side Component Total"),
          term(
              "cache_write_ratio",
              "Cache Write Ratio",
              "展示 prompt cache 写入活跃度。",
              "Cache Write / Input-side Component Total"),
          term(
              "output_input_ratio",
              "Output/Input Ratio",
              "突出输出密度。",
              "Output / Input-side Component Total"),
          term("tools_per_round", "Tools / Round", "对比交互密度。", "tool_calls / rounds"),
          term("tokens_per_round", "Tokens / Round", "诊断超大 round。", "Total Tokens / rounds"),
          term("tokens_per_minute", "Tokens / Minute", "衡量吞吐。", "Total Tokens / duration_minutes"),
          term(
              "failed_per_session",
              "Failed / Session",
              "衡量工具失败密度。",
              "failed_tool_count / sessions"));

  private static final List<GlossaryTermDto> PROVIDER_MAPPING =
      List.of(
          term(
              "anthropic",
              "Anthropic",
              "支持 fresh/cache read/cache write/output 字段映射。",
              "",
              "input_tokens",
              "cache_read_input_tokens",
              "cache_creation_input_tokens",
              "output_tokens"),
          term(
              "openai",
              "OpenAI Responses",
              "使用 prompt/completion details 推导 cache 与 visible output。",
              "",
              "prompt_tokens",
              "cached_tokens",
              "completion_tokens",
              "reasoning_tokens"),
          term(
              "codex",
              "Codex",
              "优先使用 cached_input_tokens 与 provider 输出字段。",
              "",
              "cached_input_tokens",
              "output_tokens"),
          term(
              "qoder",
              "Qoder",
              "可上报 cache_read_input_tokens 或 cached_tokens。",
              "",
              "cache_read_input_tokens",
              "cached_tokens"),
          term("not_reported", "Not reported", "字段缺失不是伪造零值，需显式标记不可用。", ""));

  private static final List<GlossaryTermDto> ROUND_SIGNALS =
      List.of(
          term("trace_id", "Trace ID", "跨来源关联一次调用链。", "trace_id"),
          term("turn_id", "Turn ID", "合并同 provider turn 的调用。", "turn_id"),
          term("tool_call_id", "Tool Call ID", "关联工具声明与结果。", "tool_call_id"),
          term("failure", "Failure", "工具执行失败信号。", "failed_tool_count"),
          term("subagent", "Subagent", "子 agent 调用及父调用归因。", "parent_call_id"),
          term(
              "payload_visibility",
              "Payload Visibility",
              "standard/full payload 可见性。",
              "visibility"));

  /** 处理 /api/glossary/summary 的 GET 请求。 */
  public void handleSummary(Context ctx) {
    ctx.json(
        new GlossarySummaryResponse(
            ApiResponses.SCHEMA_VERSION,
            TOKEN_TYPES.size(),
            DERIVED_METRICS.size(),
            PROVIDER_MAPPING.size(),
            ROUND_SIGNALS.size(),
            PageStateDto.ready()));
  }

  /** 处理 /api/glossary/token-types 的 GET 请求。 */
  public void handleTokenTypes(Context ctx) {
    ctx.json(section("token-types", TOKEN_TYPES));
  }

  /** 处理 /api/glossary/derived-metrics 的 GET 请求。 */
  public void handleDerivedMetrics(Context ctx) {
    ctx.json(section("derived-metrics", DERIVED_METRICS));
  }

  /** 处理 /api/glossary/provider-mapping 的 GET 请求。 */
  public void handleProviderMapping(Context ctx) {
    ctx.json(section("provider-mapping", PROVIDER_MAPPING));
  }

  /** 处理 /api/glossary/round-signals 的 GET 请求。 */
  public void handleRoundSignals(Context ctx) {
    ctx.json(section("round-signals", ROUND_SIGNALS));
  }

  private static GlossarySectionResponse section(String name, List<GlossaryTermDto> terms) {
    return new GlossarySectionResponse(
        ApiResponses.SCHEMA_VERSION, name, terms.size(), terms, PageStateDto.ready());
  }

  private static GlossaryTermDto term(
      String key, String label, String definition, String formula, String... providerFields) {
    return new GlossaryTermDto(key, label, definition, formula, List.of(providerFields));
  }
}
