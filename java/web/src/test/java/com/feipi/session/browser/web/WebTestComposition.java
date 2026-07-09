package com.feipi.session.browser.web;

import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;

/** web 测试专用组合辅助器，用于把具体 SQLite adapter 接入应用用例。 */
public final class WebTestComposition {

  private WebTestComposition() {}

  /** 构建 web 集成测试使用的应用查询根对象。 */
  public static QueryCompositionRoot queryRoot(
      IndexConnection indexConnection, SchemaVersion schemaVersion) {
    SqliteSessionQueryRepository sessionRepository =
        new SqliteSessionQueryRepository(indexConnection);
    SqliteAggregateQueryRepository aggregateRepository =
        new SqliteAggregateQueryRepository(indexConnection);
    SqliteSessionDetailRepository detailRepository =
        new SqliteSessionDetailRepository(sessionRepository);
    return new QueryCompositionRoot(
        sessionRepository,
        aggregateRepository,
        detailRepository,
        NormalizedArtifactLoader::load,
        schemaVersion.version(),
        QueryCache.withDefaultSize());
  }
}
