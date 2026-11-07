ALTER TABLE sessions ADD COLUMN round_count INTEGER CHECK (round_count >= 0);
ALTER TABLE sessions ADD COLUMN llm_call_count INTEGER CHECK (llm_call_count >= 0);
ALTER TABLE sessions ADD COLUMN content_measured INTEGER NOT NULL DEFAULT 0 CHECK (content_measured IN (0, 1));
