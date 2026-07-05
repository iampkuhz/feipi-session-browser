# Spec: Java Code Conciseness Delta

## Requirement: Records document data components

Java records used as immutable data carriers SHALL document each component with Chinese Javadoc so compact data declarations remain maintainable after class-to-record simplification.

### Scenario: Data record declares all component meanings

- **Given** a Java record is used to carry query, API, or page data
- **When** a developer reads the record declaration
- **Then** the type Javadoc SHALL include one `@param` entry for each record component
- **And** each `@param` entry SHALL explain the component in Chinese while keeping code identifiers and technical terms in English.

### Scenario: Compact constructor does not replace component documentation

- **Given** a record has a compact constructor that validates invariants
- **When** the record component documentation gate runs
- **Then** constructor Javadoc SHALL NOT satisfy component documentation
- **And** the record type Javadoc SHALL still document every component.
