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
 *   <li>{@link com.feipi.session.browser.domain.enums.CallScope} &mdash; main, subagent
 *   <li>{@link com.feipi.session.browser.domain.enums.CallStatus} &mdash; success, error, timeout,
 *       cancelled
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenPrecision} &mdash; exact,
 *       provider_reported, estimated, heuristic, unknown
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenProvider} &mdash; anthropic, openai,
 *       qoder_broker, unknown
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenSourceKind} &mdash; provider_usage,
 *       transcript_reconstruction, estimation, residual, unknown
 *   <li>{@link com.feipi.session.browser.domain.enums.TokenTotalSemantics} &mdash;
 *       exclusive_component_sum, inclusive_of_cache, unknown
 * </ul>
 */
package com.feipi.session.browser.domain.enums;
