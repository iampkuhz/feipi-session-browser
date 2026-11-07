ALTER TABLE sessions ADD COLUMN user_message_measured INTEGER NOT NULL DEFAULT 0 CHECK (user_message_measured IN (0, 1));
ALTER TABLE sessions ADD COLUMN assistant_message_measured INTEGER NOT NULL DEFAULT 0 CHECK (assistant_message_measured IN (0, 1));
