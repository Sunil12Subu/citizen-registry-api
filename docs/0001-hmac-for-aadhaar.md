# ADR 0001: Store Aadhaar as an HMAC-SHA256 hash plus last 4 digits

- **Status:** Accepted
- **Date:** 2026-11-20

## Context

The registry must find citizens by Aadhaar number and prevent duplicate registrations,
but a database leak must not expose Aadhaar numbers. Aadhaar has only ~10^11 possible
values, so the input space is small.

## Decision

Store two columns instead of the number:

- `aadhaar_hash`: HMAC-SHA256 of the normalised 12-digit number, keyed with
  `ID_HASH_SECRET` (kept outside the database, in environment variables). Unique.
- `aadhaar_last4`: for display as `XXXX-XXXX-1234`.

Lookups hash the input with the same key and compare hashes.

## Alternatives considered

| Option | Why rejected |
|---|---|
| Plain text | A database leak exposes every Aadhaar directly |
| Plain SHA-256 | ~10^11 inputs can be hashed by an attacker in hours, reversing every hash |
| Salted hash (bcrypt/argon2, salt per row) | Slow by design and a different salt per row, so lookups and the UNIQUE constraint become impossible without scanning every row |
| Reversible encryption (AES) | Needed only if the full number must be shown again, which this system never does; adds key-rotation and decryption-access risks |

## Consequences

- ✅ A stolen database alone reveals nothing useful: the key lives elsewhere.
- ✅ Exact-match lookup and duplicate detection stay fast (indexed, unique).
- ⚠️ If `ID_HASH_SECRET` leaks **together with** the database, hashes can be brute-forced.
  The key must be stored and rotated like any production secret.
- ⚠️ Rotating the key means re-hashing, which needs the original numbers, which we don't keep.
  A rotation would require citizens to re-verify. Accepted trade-off for this scope.
- ⚠️ The full Aadhaar can never be shown or exported again, by design.