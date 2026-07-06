package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.Collections;
import java.util.List;

/**
 * 归一化制品的源文件集合。
 *
 * @param files 对 artifact 有贡献的源文件列表
 */
@DomainModel
public record NormalizedArtifactSource(List<NormalizedSourceFile> files) {

  /** 校验并复制源文件列表。 */
  public NormalizedArtifactSource {
    List<NormalizedSourceFile> copy = files == null ? Collections.emptyList() : List.copyOf(files);
    if (copy.size() > NormalizedConstants.MAX_COLLECTION_SIZE) {
      throw new IllegalArgumentException(
          "source files size exceeds limit " + NormalizedConstants.MAX_COLLECTION_SIZE);
    }
    files = copy;
  }
}
