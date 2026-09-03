# 1-5 Studios Master Library + Resolver v1

This is an implementation starter for a real PostgreSQL-backed authority service. It does not contain registry records and it never generates a Permanent ID. A Permanent ID can enter the registry only through the authenticated `authority-register` endpoint with the ID supplied by an authorized human/authority.

## Apply migrations

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_initial.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/002_manifest.sql
```

## Run

```bash
python -m pip install -r requirements.txt
DATABASE_URL='postgresql://...' uvicorn app:app --host 0.0.0.0 --port 8000
```

Every API call requires `X-Actor-Id`. In production replace this development boundary with verified OIDC/JWT middleware and map actor IDs to roles. The browser/UI must not hold database credentials.

## Resolver outcomes

- `EXACT_MATCH`: one authoritative registry record, with registry evidence; authority decision is still required unless an existing redirect is present.
- `COLLISION`: multiple authoritative records; returns all evidence-backed candidates and stops.
- `NO_MATCH / REGISTRATION REQUIRED`: no authoritative record; no ID is created.
- `QUARANTINED`: returned by the authority-decision flow when a record is unsafe or insufficient.

## Security guarantees implemented

- `id_history` is checked before registration and prevents reuse of any historical Permanent ID.
- Permanent registration requires an authenticated actor, an explicit authority record, and a caller-supplied Permanent ID; the service does not generate IDs.
- Redirects require an existing active authoritative target.
- Audit events are inserted in the same transaction as state changes and are protected by database triggers against update/delete.
- Resolver search uses authoritative status and returns database evidence, never name-only inference in the response.

## Still required before production

1. Provision PostgreSQL with TLS, backups, PITR, monitoring, and separate staging/production databases.
2. Create least-privilege DB roles; prevent the API runtime role from deleting/updating `audit_events` and from registering IDs unless it is the dedicated authority service.
3. Add OIDC/JWT verification, role checks (`RESOLVER_SERVICE`, `LIBRARIAN`, `REGISTRATION_AUTHORITY`, `AUDITOR`), rate limits, and secret-manager delivery.
4. Add integration tests against PostgreSQL, including concurrent registration, duplicate registration, redirect, collision, quarantine, and audit immutability.
5. Build the Manifest Registration service that validates all required references, computes/verifies checksum, registers/locks the manifest, and only then emits the compact MK1 QR payload.

No seed records are included. Load only authority-approved records through the controlled registration process.
