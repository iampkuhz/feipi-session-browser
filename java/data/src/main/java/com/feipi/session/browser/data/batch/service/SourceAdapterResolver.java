package com.feipi.session.browser.data.batch.service;

import com.feipi.session.browser.source.spi.SourceAdapter;

/** 根据 sourceId 解析源适配器的函数式接口。 */
@FunctionalInterface
public interface SourceAdapterResolver {

  /**
   * 根据源标识返回对应的源适配器。
   *
   * @param sourceId 源标识字符串
   * @return 源适配器
   */
  SourceAdapter forSourceId(String sourceId);
}
