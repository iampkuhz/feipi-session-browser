#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
log = Path(".claude/change-log.jsonl")
log.parent.mkdir(parents=True, exist_ok=True)
log.write_text(log.read_text(encoding="utf-8") if log.exists() else "", encoding="utf-8")
with log.open("a", encoding="utf-8") as f:
    f.write('{"ts":"%s","event":"post-edit"}\n' % datetime.utcnow().isoformat())
