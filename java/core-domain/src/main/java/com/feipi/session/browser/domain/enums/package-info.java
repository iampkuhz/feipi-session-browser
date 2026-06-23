/**
 * 领域枚举包。
 *
 * <p>包含与 Python {@code DomainStrEnum} 兼容的枚举类型， 用于 token 计量、调用状态和作用域分类。
 *
 * <h2>S2 契约冻结</h2>
 *
 * <p>以下枚举已在 S1 冻结，{@code getValue()} 返回的字符串必须与 Python 端保持一致：
 *
 * <ul>
 *   <li>{@link com.feipi.session.browser.domain.enums.CallScope} — {@code main, subagent}
 *   <li>{@link com.feipi.session.browser.domain.enums.CallStatus} — {@code ok, error}
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenPrecision} — {@code exact,
 *       provider_reported, estimated, unavailable}
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenProvider} — {@code anthropic, openai,
 *       codex, qwen-anthropic-compatible, qoder, unknown}
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenSourceKind} — {@code
 *       claude_code_jsonl_usage, codex_rollout_token_count, openai_responses_usage, ...}
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenTotalSemantics} — {@code
 *       exclusive_components_sum, reported_total, ...}
 * </ul>
 */
package com.feipi.session.browser.domain.enums;
