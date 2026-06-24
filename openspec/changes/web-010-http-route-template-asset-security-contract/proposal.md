# WEB-010: HTTP、Route、Template、Asset 与安全契约清单

## Stage

S5 - Web + serve/stop

## Kind

PLAN - 契约冻结

## Goal

审计 Python web 层（routes.py、template_env.py、safe_render.py、mhtml.py、templates/、static/、presenters/、renderers/），冻结 Java Web 行为和安全边界。

## Scope

- openspec/changes/web-010-http-route-template-asset-security-contract/
- docs/acceptance-contracts/web-010-http-route-template-asset-security.md
- tmp/java-migration-run/20260623-222713/34-WEB-010/

## Constraints

- 不修改 production (java/**/src/main/**, src/session_browser/**)
- PLAN 任务，只产出契约文档和审计结果
- 所有新增注释使用简体中文，技术术语英文
