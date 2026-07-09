/**
 * Java typed query API 模块。
 *
 * <p>提供会话浏览器的查询端口层类型：分页、排序、过滤器。 所有校验在 API factory 完成，下游 repository 信任已验证的类型不变量。
 *
 * <p>本模块不依赖 Web/JDBC 等具体实现层。
 */
package com.feipi.session.browser.query.api;
