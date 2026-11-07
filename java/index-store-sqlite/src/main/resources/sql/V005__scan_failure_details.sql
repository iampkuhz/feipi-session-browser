ALTER TABLE scan_log ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scan_log ADD COLUMN failures_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE scan_log ADD COLUMN processed_count INTEGER NOT NULL DEFAULT 0;
UPDATE scan_log SET error_count = 1, failures_json = '[{"source":"","sessionKey":"","phase":"UNKNOWN","code":"LEGACY_SCAN_FAILURE","line":0}]' WHERE status = 'failure';
