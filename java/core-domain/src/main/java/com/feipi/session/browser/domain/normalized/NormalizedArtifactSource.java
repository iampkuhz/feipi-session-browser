package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.common.validation.ImmutableCopies;
import com.feipi.session.browser.domain.annotation.DomainModel;
import java.util.List;

/**
 * 归一化制品的源文件集合。
 *
 * @param files 对 artifact 有贡献的源文件列表
 */
@DomainModel
public record NormalizedArtifactSource(
    /* 对 artifact 有贡献的源文件列表。 */
    List<NormalizedSourceFile> files) {

  /** 校验并复制源文件列表。 */
  public NormalizedArtifactSource {
    files =
        ImmutableCopies.boundedListOrEmpty(
            files, NormalizedConstants.MAX_COLLECTION_SIZE, "source files");
  }
}
