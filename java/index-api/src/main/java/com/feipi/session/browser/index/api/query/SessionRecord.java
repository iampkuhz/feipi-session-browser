package com.feipi.session.browser.index.api.query;

/** 索引查询端口暴露的抽象 session 查询结果。 */
public interface SessionRecord {
  /** 返回会话在索引中的稳定唯一键。 */
  String sessionKey();

  /** 返回产生会话的源适配器标识。 */
  String agent();

  /** 返回来源系统中的会话标识。 */
  String sessionId();

  /** 返回会话的展示标题。 */
  String title();

  /** 返回会话所属项目的唯一键。 */
  String projectKey();

  /** 返回会话所属项目的展示名称。 */
  String projectName();

  /** 返回会话运行时的工作目录。 */
  String cwd();

  /** 返回会话首事件的 ISO8601 时间文本。 */
  String startedAt();

  /** 返回会话末事件的 ISO8601 时间文本。 */
  String endedAt();

  /** 返回会话首末事件之间的墙钟秒数。 */
  double durationSeconds();

  /** 返回模型推理累计执行的秒数。 */
  double modelExecutionSeconds();

  /** 返回工具调用累计执行的秒数。 */
  double toolExecutionSeconds();

  /** 返回会话使用的模型名称。 */
  String model();

  /** 返回会话记录的 Git 分支。 */
  String gitBranch();

  /** 返回会话的运行时来源标识。 */
  String source();

  /** 返回会话中的用户消息数。 */
  long userMessageCount();

  /** 返回会话中的助手消息数。 */
  long assistantMessageCount();

  /** 返回会话记录的工具调用数。 */
  long toolCallCount();

  /** 返回会话生成的输出 token 数。 */
  long outputTokens();

  /** 返回会话消耗的新鲜输入 token 数。 */
  long freshInputTokens();

  /** 返回会话命中的缓存读取 token 数。 */
  long cacheReadTokens();

  /** 返回会话写入的缓存 token 数。 */
  long cacheWriteTokens();

  /** 返回会话消耗的全部 token 数。 */
  long totalTokens();

  /** 返回会话中失败的工具调用数。 */
  long failedToolCount();

  /** 返回会话包含的子 agent 实例数。 */
  long subagentInstanceCount();

  /** 返回会话写入索引时的 epoch 秒数。 */
  double indexedAt();

  /** 返回会话源文件修改时间的 epoch 秒数。 */
  double fileMtime();

  /** 返回会话源文件路径。 */
  String filePath();
}
