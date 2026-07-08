/**
 * 容错 JSONL 读取器模块。
 *
 * <p>提供流式、不加载整文件的 JSON/JSONL 解析能力， 支持美化打印、拼接对象、非法 UTF-8 和截断等边界场景。 解析结果通过 {@link
 * com.feipi.session.browser.source.json.JsonlReaderResult} 返回， 诊断信息复用 source-spi 的 {@link
 * com.feipi.session.browser.source.spi.SourceDiagnostic}。
 */
package com.feipi.session.browser.source.json;
