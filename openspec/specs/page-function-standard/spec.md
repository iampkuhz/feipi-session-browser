# Page Function Standard Spec

## Requirements

### Requirement: UI page contract v3 is the current target standard

The repository SHALL use `docs/ui/contracts/03-page-contracts.md` as the current page function standard. The standard SHALL be derived from `/Users/zhehan/Downloads/feipi-ui-page-spec-v3` and organized into the repository UI contract system.

#### Scenario: Read the current page standard

- **Given** a developer or agent needs to determine the target behavior for a page
- **When** they read `docs/ui/contracts/03-page-contracts.md`
- **Then** the document SHALL define target requirements for Dashboard, Sessions, Session Detail, Projects, Project Detail, and Agent Detail
- **And** the document SHALL state that v3 overrides older HIFI or contract clauses when they conflict

### Requirement: Main navigation and agent pages are consolidated

The page standard SHALL NOT provide a standalone Agents list page. Agent list information SHALL be displayed on Dashboard, and single-agent deep statistics SHALL be displayed on Agent Detail.

#### Scenario: Define sidebar navigation

- **Given** a developer modifies Sidebar navigation
- **When** they apply the current page function standard
- **Then** the primary Sidebar navigation SHALL include Dashboard, Sessions, and Projects
- **And** Agent Detail SHALL be reached from Dashboard agent rows or the Agent Detail selector

### Requirement: Session Detail has Trace and Payload main tabs only

Session Detail SHALL explain a single session's trace, payload, and attribution with exactly two main tabs: Trace and Payload.

#### Scenario: Define Session Detail tabs

- **Given** a developer modifies Session Detail
- **When** they apply the current page function standard
- **Then** the page SHALL expose Trace and Payload as the only main tabs
- **And** request/response attribution SHALL be part of Payload call detail
- **And** the page SHALL NOT expose separate Attribution or Insights tabs

### Requirement: List pages preserve complete user operations

Sessions, Projects, and project-level sessions tables SHALL preserve search, filtering, sorting, pagination, row navigation, and core fields.

#### Scenario: Reorganize a list page

- **Given** a developer changes list page layout
- **When** fields, controls, or column widths are reorganized
- **Then** the UI MAY reorganize information
- **And** the UI SHALL NOT reduce visible or operable information
- **And** constrained layouts SHALL use horizontal scrolling, truncation, and tooltip
- **And** constrained layouts SHALL NOT allow text overlap

### Requirement: Page acceptance checklist is available

The repository SHALL provide a page function standard v3 acceptance checklist.

#### Scenario: Review page compliance

- **Given** a developer needs to review page compliance against v3
- **When** they read `tests/acceptance/PAGE_ACCEPTANCE_CHECKLIST.md`
- **Then** the checklist SHALL cover Dashboard, Sessions, Session Detail, Projects, and Agent Detail
- **And** the checklist SHALL reference `docs/ui/contracts/03-page-contracts.md` as the detailed standard
