package com.feipi.session.browser.contracttest.support;

import com.feipi.session.browser.application.QueryCache;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteAggregateQueryRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionDetailRepository;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteSessionQueryRepository;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;

/** contract 测试专用组合辅助器，用于集中维护构造器 wiring。 */
public final class ContractTestComposition {

  private ContractTestComposition() {}

  public static QueryCompositionRoot queryRoot(
      IndexConnection indexConnection, SchemaVersion schemaVersion) {
    return queryRoot(indexConnection, schemaVersion, null);
  }

  public static QueryCompositionRoot queryRoot(
      IndexConnection indexConnection, SchemaVersion schemaVersion, QueryCache cache) {
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
        cache);
  }
}
