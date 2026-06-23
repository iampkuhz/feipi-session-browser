package com.feipi.session.browser.query.api;

/**
 * query-api 模块标记接口。
 *
 * <p>供架构测试识别 query-api 模块边界，不作为业务逻辑使用。
 */
public sealed interface QueryApiMarker permits QueryApiMarkerInternal {}
