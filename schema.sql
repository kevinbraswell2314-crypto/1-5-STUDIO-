CREATE TABLE IF NOT EXISTS manifests (
    manifest_id UUID PRIMARY KEY,
    authority TEXT NOT NULL,
    package_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('REGISTERED','RETIRED','INVALIDATED')),
    body_json JSONB NOT NULL,
    body_fingerprint TEXT NOT NULL,
    checksum TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    UNIQUE(authority, body_fingerprint),
    UNIQUE(authority, checksum)
);

CREATE TABLE IF NOT EXISTS manifest_references (
    manifest_id UUID NOT NULL REFERENCES manifests(manifest_id) ON DELETE RESTRICT,
    ref_id TEXT NOT NULL,
    ref_type TEXT NOT NULL,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    authority_state TEXT NOT NULL,
    package_version_id TEXT,
    PRIMARY KEY (manifest_id, ref_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    manifest_id UUID,
    details_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_manifests_package_id ON manifests(package_id);
CREATE INDEX IF NOT EXISTS idx_manifest_refs_ref_id ON manifest_references(ref_id);
CREATE INDEX IF NOT EXISTS idx_audit_manifest_id ON audit_events(manifest_id);
