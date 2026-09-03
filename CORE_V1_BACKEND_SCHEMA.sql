-- 1-5 Studios Core v1 — PostgreSQL authority spine (starter schema)
-- This is intentionally conservative: the database enforces identity non-reuse and
-- separates intake/security IDs, provisional identities, and Permanent identities.

BEGIN;

CREATE TABLE IF NOT EXISTS id_history (
    namespace       text NOT NULL,
    identifier      text NOT NULL,
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    retired_at      timestamptz,
    PRIMARY KEY (namespace, identifier)
);

CREATE TABLE IF NOT EXISTS intake_records (
    intake_id       text PRIMARY KEY,
    security_tag    text UNIQUE NOT NULL,
    source_kind     text NOT NULL,
    source_ref      text,
    content_hash    text,
    security_status text NOT NULL DEFAULT 'RECEIVED',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provisional_identities (
    provisional_id      text PRIMARY KEY,
    intake_id           text REFERENCES intake_records(intake_id),
    category            text NOT NULL,
    working_name        text,
    status              text NOT NULL DEFAULT 'PROVISIONAL',
    resolution_status   text NOT NULL DEFAULT 'UNRESOLVED',
    resolved_permanent_id text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    resolved_at         timestamptz
);

CREATE TABLE IF NOT EXISTS permanent_identities (
    permanent_id     text PRIMARY KEY,
    category         text NOT NULL,
    canonical_name   text NOT NULL,
    status           text NOT NULL DEFAULT 'ACTIVE',
    authority_record text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    retired_at       timestamptz
);

ALTER TABLE provisional_identities
    DROP CONSTRAINT IF EXISTS provisional_resolved_fk;
ALTER TABLE provisional_identities
    ADD CONSTRAINT provisional_resolved_fk
    FOREIGN KEY (resolved_permanent_id)
    REFERENCES permanent_identities(permanent_id);

CREATE TABLE IF NOT EXISTS aliases (
    alias_id          bigserial PRIMARY KEY,
    permanent_id      text NOT NULL REFERENCES permanent_identities(permanent_id),
    alias_text        text NOT NULL,
    authority_status  text NOT NULL DEFAULT 'APPROVED',
    UNIQUE (permanent_id, alias_text)
);

CREATE TABLE IF NOT EXISTS redirects (
    old_permanent_id  text PRIMARY KEY REFERENCES permanent_identities(permanent_id),
    surviving_permanent_id text NOT NULL REFERENCES permanent_identities(permanent_id),
    reason            text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (old_permanent_id <> surviving_permanent_id)
);

CREATE TABLE IF NOT EXISTS canonical_packages (
    package_id        text PRIMARY KEY,
    permanent_id      text REFERENCES permanent_identities(permanent_id),
    package_type      text NOT NULL,
    status            text NOT NULL DEFAULT 'WORKING',
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS package_versions (
    version_id        text PRIMARY KEY,
    package_id        text NOT NULL REFERENCES canonical_packages(package_id),
    version_number    integer NOT NULL,
    payload_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    authority_status  text NOT NULL DEFAULT 'WORKING',
    approved_at       timestamptz,
    UNIQUE(package_id, version_number)
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id   text PRIMARY KEY,
    subject_id        text NOT NULL,
    predicate         text NOT NULL,
    object_id         text NOT NULL,
    authority_status  text NOT NULL DEFAULT 'WORKING',
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS state_deltas (
    delta_id          text PRIMARY KEY,
    identity_id       text NOT NULL,
    scene_id          text,
    shot_id           text,
    delta_json        jsonb NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS manifests (
    manifest_id       text PRIMARY KEY,
    project_id        text NOT NULL,
    scene_id          text,
    shot_id           text,
    status            text NOT NULL DEFAULT 'WORKING',
    checksum          text,
    registered_at     timestamptz
);

CREATE TABLE IF NOT EXISTS manifest_references (
    manifest_id       text NOT NULL REFERENCES manifests(manifest_id) ON DELETE CASCADE,
    reference_id      text NOT NULL,
    reference_kind    text NOT NULL,
    required          boolean NOT NULL DEFAULT true,
    resolved_permanent_id text REFERENCES permanent_identities(permanent_id),
    PRIMARY KEY (manifest_id, reference_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id       text PRIMARY KEY,
    target_type       text NOT NULL,
    target_id         text NOT NULL,
    target_version    text,
    approval_scope    text NOT NULL,
    actor_type        text NOT NULL,
    actor_id          text NOT NULL,
    status            text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS locks (
    lock_id            text PRIMARY KEY,
    target_type        text NOT NULL,
    target_id          text NOT NULL,
    target_version     text NOT NULL,
    approval_id        text REFERENCES approvals(approval_id),
    content_hash       text,
    locked_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id     text PRIMARY KEY,
    correlation_id     text NOT NULL,
    request_id         text,
    transaction_id     text,
    parent_event_id    text,
    actor_type         text NOT NULL,
    actor_id           text NOT NULL,
    action             text NOT NULL,
    target_type        text,
    target_id          text,
    result             text NOT NULL,
    metadata_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now()
);

-- Guardrail view: manifests that are NOT eligible for final authoritative release
-- because at least one required reference lacks a resolved Permanent ID.
CREATE OR REPLACE VIEW manifest_unresolved_required AS
SELECT mr.manifest_id, mr.reference_id, mr.reference_kind
FROM manifest_references mr
WHERE mr.required = true
  AND mr.resolved_permanent_id IS NULL;

COMMIT;

-- Application transaction law:
-- Permanent registration, merge, redirect, collision repair, manifest registration,
-- final approval and lock MUST run inside controlled atomic transactions that also
-- append audit events and check id_history before committing.
