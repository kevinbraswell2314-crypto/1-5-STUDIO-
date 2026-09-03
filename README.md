# 1-5 Studios — Librarian Manifest Registration v1

This is the first backend authority service required before a valid production QR can exist.

## What it does

It accepts a complete scene-package manifest and checks the pre-registration gates:

- SCENE_LOCKED
- REQUIRED_TAGS_RESOLVED
- CANONICAL_PACKAGES_FOUND
- RELATIONSHIPS_VALID

If any required reference is still provisional/unresolved, registration is blocked.

If all pre-registration gates pass, one database transaction:

1. checks whether this exact manifest body is already registered;
2. reuses the existing registration if found;
3. otherwise creates one registry-issued opaque Manifest ID;
4. computes a SHA-256 checksum bound to MK1 + Manifest ID + body fingerprint;
5. stores the manifest;
6. stores its references;
7. appends an audit event;
8. returns the exact compact QR payload:

`MK1|<REGISTERED_MANIFEST_ID>|<CHECKSUM>`

The service does **not** invent Permanent Asset IDs. Those must already be Librarian-resolved before the manifest can register.

## Important

Running this code against your real PostgreSQL database is the act that creates the real registry record. The example request deliberately contains a provisional placeholder so it will BLOCK until the Librarian resolution step is complete.

## Run locally

1. Create a PostgreSQL database.
2. Run `schema.sql`.
3. Set `DATABASE_URL`.
4. Install `requirements.txt`.
5. Start:

`uvicorn app:app --host 0.0.0.0 --port 8000`

6. POST the complete QTDC manifest to `/api/v1/manifests/register`.

## Next build after this service

Connect the Master Library/Librarian Resolver so the QTDC provisional IDs are reconciled into authoritative references. Then submit the complete 8-scene QTDC manifest to this service. Only the service's returned `manifest_id` and `checksum` should be handed to the QR generator.
