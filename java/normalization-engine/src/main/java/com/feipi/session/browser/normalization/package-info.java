/**
 * 归一化引擎包。
 *
 * <p>将源适配器解析的 JSON 事件转换为不可变的、带 schema 版本的 {@code
 * com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact}。
 * 引擎为纯函数，不读写文件、不访问环境变量、不生成随机 ID。相同输入保证产生相同输出。
 */
package com.feipi.session.browser.normalization;
