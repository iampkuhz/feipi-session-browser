# Session Detail Runtime Spec

## ADDED Requirements

### Requirement: Session detail page shall render without server error

The system SHALL render a session detail page for an existing session id without returning a 5xx error.

#### Scenario: Existing session detail route is opened
- GIVEN a session exists in the index with a valid agent and session_id
- WHEN the user opens `/sessions/<agent>/<session_id>`
- THEN the server returns HTTP 200
- AND the response contains the session title or prompt preview
- AND the response contains the core session metrics area
- AND the response contains the tab/workbench container

### Requirement: Session detail page shall handle missing ConversationRound.title gracefully

The system SHALL NOT raise an AttributeError when building the session_rounds context for the sidebar round map.

#### Scenario: Session rounds are built for sidebar
- WHEN the route handler constructs the `session_rounds` list
- THEN each round's name uses an available field (`preview_text`) on `ConversationRound`
- AND a fallback label (e.g., "Round N") is used if the field is empty

### Requirement: Session detail static assets shall load

The system SHALL serve required CSS and JavaScript assets for the session detail page.

#### Scenario: Session detail page references static assets
- WHEN the rendered HTML references CSS or JavaScript at `/static/` paths
- THEN those asset URLs resolve with HTTP 200
- AND no required asset path points to a missing file

### Requirement: Runtime smoke test shall cover session detail

The system SHALL include an automated smoke test that catches session detail startup failures.

#### Scenario: Test suite runs
- WHEN the regression test suite runs
- THEN it exercises the session detail route
- AND fails if the page cannot render
- AND the test does not require Playwright or a real browser
