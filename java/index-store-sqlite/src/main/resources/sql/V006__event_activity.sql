CREATE TABLE IF NOT EXISTS event_activity_coverage (
 session_key TEXT PRIMARY KEY,
 observedUserMessages INTEGER NOT NULL,
 undatedUserMessages INTEGER NOT NULL,
 supportedUsageEvents INTEGER NOT NULL,
 undatedUsageEvents INTEGER NOT NULL,
 unsupportedUsageEvents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_activity_days (
 session_key TEXT NOT NULL,
 epoch_day INTEGER NOT NULL,
 latest_event_timestamp TEXT NOT NULL,
 observed_user_messages INTEGER NOT NULL,
 PRIMARY KEY(session_key, epoch_day)
);
CREATE TABLE IF NOT EXISTS event_activity_tokens (
 session_key TEXT NOT NULL,
 day_key TEXT NOT NULL,
 component TEXT NOT NULL,
 reportedTokens INTEGER NOT NULL,
 reportedSamples INTEGER NOT NULL,
 estimatedSamples INTEGER NOT NULL,
 unavailableSamples INTEGER NOT NULL,
 unknownSamples INTEGER NOT NULL,
 mixedSamples INTEGER NOT NULL,
 PRIMARY KEY(session_key, day_key, component)
);
