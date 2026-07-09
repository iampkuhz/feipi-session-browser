package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import java.io.IOException;
import java.nio.file.Path;

/** 为 Session Detail 组装读取标准化 session artifact。 */
@FunctionalInterface
public interface NormalizedArtifactReader {

  /** 从磁盘加载并校验单个标准化 artifact。 */
  NormalizedSessionArtifact load(Path artifactPath) throws IOException;
}
