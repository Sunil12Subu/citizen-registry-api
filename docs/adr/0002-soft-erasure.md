# ADR 0002: Implement the right to erasure as anonymisation, not row deletion

- **Status:** Accepted
- **Date:** 2026-11-24

## Context

DPDP gives citizens the right to have their personal data erased. The system also keeps
an audit trail (`audit_logs`) of who accessed or changed each record, which references
`citizens.id`. Deleting the citizen row would either break those references or force us
to delete the audit history too, destroying evidence of past access.

## Decision

`POST /citizens/{id}/erase`:

1. Sets every personal column (`full_name`, `date_of_birth`, `mobile`, `email`,
   `district`, `aadhaar_hash`, `aadhaar_last4`) to `NULL`.
2. Sets `erased_at`.
3. Withdraws all active consents.
4. Writes a `citizen.erase` audit entry, all in one transaction.

The row remains as an anonymous shell: an ID and timestamps only.

## Alternatives considered

| Option | Why rejected |
|---|---|
| Hard `DELETE` with cascade | Also deletes the audit trail, so we could no longer show who accessed the data before erasure |
| Hard `DELETE`, audit `citizen_id` set to NULL | Audit entries lose their meaning ("someone's record was read") |
| `is_deleted` flag, data kept | Not erasure: the personal data is still stored |

## Consequences

- ✅ Personal data is really gone. Tests verify the **stored row**, not just the API response.
- ✅ The audit trail stays complete and meaningful after erasure.
- ✅ Clearing `aadhaar_hash` lets the same person register again in future.
- ⚠️ Every new personal column must be added to `PERSONAL_FIELDS` in `services/rights.py`.
  Mitigation: the erasure test checks the whole row as text.
- ⚠️ Erasure cannot be undone. The endpoint documentation says so.
- ⚠️ Database backups still contain the data until they expire. Backup retention must be
  covered by the operational data-retention policy (out of scope here).