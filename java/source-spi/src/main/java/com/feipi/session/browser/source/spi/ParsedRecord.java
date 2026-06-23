package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 源中性的已解析记录标记接口。
 *
 * <p>代表源适配器解析出的单条源中性记录。具体实现由各源适配器提供， 但通过此接口在 SPI 层统一承载，避免泄漏 provider 特定载荷。
 *
 * <p>设计原则：
 *
 * <ul>
 *   <li>不引用 Jackson {@code JsonNode} 或其他 provider 特定类型。
 *   <li>实现类必须不可变。
 *   <li>通过 {@link SourceResult.Success#records()} 在解析成功时携带。
 * </ul>
 */
@DomainModel
public interface ParsedRecord {

  /**
   * 返回该记录的源中性 locator 标识。
   *
   * <p>locator 应为稳定标识（如相对路径、会话内偏移），不得使用绝对 home 路径作为持久身份。
   *
   * @return 非 null 的 locator 字符串
   */
  String locator();
}
