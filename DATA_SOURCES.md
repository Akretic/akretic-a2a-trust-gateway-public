# Data Sources

This repository uses a synthetic enterprise corpus created for the challenge.

## Included Sources

- `corpus/metadata.json`: source IDs, classifications, source types, allowed
  groups, document types, sensitivity tags, storage URIs, content hashes, and
  index status.
- `corpus/documents/*.md`: synthetic documents for the VendorNova demo,
  including procurement policy, security policy, contract-review checklist,
  vendor profile, vendor questionnaire, seeded public-risk snippets, and a
  restricted executive memo used to prove denial behavior.

## Data Boundaries

- No customer data is included.
- No private third-party data is included.
- No production enterprise data is included.
- No secrets, tokens, credentials, or service-account key files are
  included.

The corpus exists only to demonstrate policy-mediated A2A collaboration,
permission-preserving retrieval, approval-gated side effects, and
tamper-evident evidence in a challenge prototype.
