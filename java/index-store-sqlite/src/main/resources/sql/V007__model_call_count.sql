ALTER TABLE sessions ADD COLUMN model_call_count INTEGER CHECK (model_call_count >= 0);
