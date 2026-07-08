/**
 * 发行可移植性与清洁机门禁测试。
 *
 * <p>验证发行包在清洁机环境下可正常工作：
 *
 * <ul>
 *   <li>只读安装目录不阻止启动。
 *   <li>路径含空格和非 ASCII 字符可正确处理。
 *   <li>发行包不依赖 Python 或 quality 工具。
 *   <li>构建信息资源存在于 classpath。
 * </ul>
 */
package com.feipi.session.browser.contracttest.distribution;
