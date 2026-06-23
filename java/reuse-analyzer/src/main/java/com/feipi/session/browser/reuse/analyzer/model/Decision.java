package com.feipi.session.browser.reuse.analyzer.model;

/** Finding 决策类型。 */
public enum Decision {
  REUSE_EXISTING,
  MOVE_TO_EXISTING_OWNER,
  EXTRACT_SHARED_COMPONENT,
  MOVE_TO_PROVIDER_COMPONENT,
  KEEP_ON_OWNER,
  INTENTIONAL_DUPLICATION,
  DEFER,
}
