# SI-120: S3 Scan/Index 所有权与 Stage 收口

## Stage
S3 -- Java Scan + SQLite Index

## Goal
只读验证并同步 ownership 文档；发现 production 缺陷时返回 owning task。

## Boundary
stage.S3.closeout

## Owner Before
mixed scan/index ownership (Python scanners + Java scan engine)

## Owner After
Java scan/index owner; Python read-only query/Web

## Fallback
forbidden

## Kind
CLOSEOUT

## Verification Scope
- 冷构建 `./gradlew clean check --no-build-cache`
- warm cache `./gradlew check --configuration-cache`
- `./gradlew qualityFull`
- `./gradlew reuseAnalyzeIncremental`
- `bash scripts/harness/doctor.sh`
- `python3 -m pytest tests -q`
- `python3 scripts/quality/check_code_comment_language.py java/ scripts/ --jobs auto`
- production closeout diff 为空
- scan/index 所有权转移证明

## Allowed Files
- docs/**
- harness/**
- scripts/harness/**
- scripts/quality/**
- scripts/claude_hooks/classify.py
- AGENTS.md, CLAUDE.md, README.md
- .github/workflows/**
- tests/**
- java/contract-tests/**
- tmp/java-migration-run/**

## Forbidden Files
- java/**/src/main/**
- src/session_browser/index/**
- scripts/session-browser.sh

## Acceptance Criteria
- scan/index 仅 Java 写
- Python 只读 query/Web
- 0 skipped/aborted
- production 实现无 closeout 修改
- S3-ACCEPTED marker 生成
- durable ownership 文档更新
