# MHTML Export Spec

## Requirements

### Requirement: Self-contained session export

The system SHALL export one published session as a static offline archive in
HTML and MHTML. For managed content, both formats SHALL include all indexed
model-call and tool records independently of the live view window, preserving
recorded bodies, call and tool ownership, and token values and provenance
subject to the export redaction policy. Trace row and call record totals SHALL
be distinguished from confirmed model calls; record groups without a
confirmed boundary SHALL NOT be labeled as confirmed calls.

#### Scenario: Open a large managed archive offline

- **WHEN** a supported browser opens a downloaded HTML or MHTML archive offline
- **THEN** records at the beginning and end of the archive SHALL be available
  through native mouse and keyboard disclosure controls without JavaScript or
  network access
- **AND** the archive is not required to reproduce live tabs, filters, or modals.

#### Scenario: Respect the archive size limit

- **WHEN** encoding a download would exceed 50 MiB
- **THEN** the export SHALL return HTTP 413 without serving a partial archive.
