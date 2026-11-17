# Semantic catalogue

Public, human- and agent-readable definitions of every dataset and measure served.
See [ADR 0007](../docs/adr/0007-semantic-catalogue.md). Validated by `nhs_data_api.catalogue`.

- `datasets/*.yaml`: one file per dataset: metadata, dimensions, measures, caveats.
- `sources/*.yaml`: manifests of publication file URLs ([ADR 0009](../docs/adr/0009-source-acquisition.md)).

Entries marked `status: draft` contain details still to be checked against the source
publication and its technical guidance.
