package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.nio.file.Path;

/** 为 Session Detail 组装读取标准化 session artifact。 */
@FunctionalInterface
public interface NormalizedArtifactReader {

  /** 从磁盘加载并校验单个标准化 artifact。 */
  NormalizedSessionArtifact load(Path artifactPath) throws IOException;

  /** 打开可重放的完整内容；旧实现仍只需提供原有的单一抽象方法。 */
  default com.feipi.session.browser.domain.normalized.NormalizedSessionContent open(Path path)
      throws IOException {
    return com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
        load(path));
  }
}
