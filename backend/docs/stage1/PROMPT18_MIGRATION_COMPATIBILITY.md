# Prompt 18 — Tariff Revision Migration and Compatibility

**Schema revision:** `c9d0e1f2a3b4`\
**Parent revision:** `b8c9d0e1f2`\
**Scope:** Immutable tariff revision storage and archiveable tariff identities.

## Migration behavior

`backend/alembic/versions/c9d0e1f2a3b4_add_immutable_tariff_revisions.py`
adds:

- Nullable `tariffs.archived_at` for soft-archiving the stable user-owned
  tariff identity.
- `tariff_revisions`, with a unique `(tariff_id, revision_number)` constraint,
  source type and optional source plan identifier, confirmation timestamp,
  explicit effective dates, rates/periods, GST flag, supply charge,
  unsupported-component list, illustrative flag and creation time.
- A tariff foreign key and lookup index.

The migration checks the live schema before adding fields/table because the
initial repository migration uses `Base.metadata.create_all()` and some
databases may already contain the model-defined objects.

## Historical-data policy

- Existing mutable `tariffs` rows are **not** copied into
  `tariff_revisions`. Their historical effective period and user confirmation
  cannot be established from the old row.
- A pre-existing tariff therefore does not become a confirmed historical
  contract by migration. Billing must return unavailable until the user
  reviews the terms and creates a confirmed revision with an evidenced
  effective-from date.
- Existing reading data, uploads and synthetic demonstration data are not
  changed by this migration.
- Generic AER catalog responses are not stored in tariff tables and are never
  backfilled as a customer's terms.
- Normal tariff deletion now archives the stable identity; revision history
  is retained. The API does not expose a hard-delete operation.

## API compatibility

- The existing `Tariff` identity and `/api/v1/tariffs` response remain as a
  compatibility projection of the latest revision.
- `GET /api/v1/tariffs/revisions` is additive and returns user-owned history.
- `POST /api/v1/tariffs` now requires explicit confirmation and appends a
  revision; it does not edit earlier snapshots.
- Illustrative presets remain available through the existing preset path but
  are stored as unconfirmed illustrative revisions.
- Customer billing no longer silently prices from a default or an illustrative
  preset. A scenario estimate requires an explicit scenario request.
- The AER routes are read-only and do not write either the compatibility
  projection or revision history.
- Recommendation cost context and scheduling cost previews resolve confirmed
  rates from tariff revision snapshots, not the mutable compatibility
  projection. Scheduling blocks when the requested horizon is uncovered,
  overlaps revisions, or crosses a revision boundary that the current
  single-revision pricing contract cannot represent.

## Reversibility and backup requirement

Alembic downgrade removes `tariff_revisions` and `archived_at`. The schema
change is reversible, but downgrading after revisions have been created
destroys revision history. Take and verify a database backup before
downgrading; do not treat downgrade as a data-preserving rollback.

No automatic downgrade is run by application startup. Upgrade and downgrade
verification uses a disposable database only.

## Validation record

The exact current Prompt 18 migration results, including the disposable
PostgreSQL availability check, are recorded in
[`PROMPT18_ACCEPTANCE.md`](PROMPT18_ACCEPTANCE.md) and the root
[`BASELINE_VERIFICATION.md`](../../../BASELINE_VERIFICATION.md).
