package com.feipi.session.browser.index.api.query;

import java.util.List;
import java.util.Optional;

/** session detail artifact 查找读取端口。 */
public interface SessionDetailPort {

  /** 按 route 或 canonical session key 查找单个 session。 */
  Optional<SessionRecord> findSession(String sessionKey);

  /** 列出与单个 session 关联的 artifact。 */
  List<SessionArtifactRecord> findArtifacts(String sessionKey);

  /** 查找与单个 session 关联的标准化 artifact。 */
  Optional<SessionArtifactRecord> findNormalizedArtifact(String sessionKey);
}
