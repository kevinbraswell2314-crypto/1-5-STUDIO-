CREATE TABLE IF NOT EXISTS id_history (
    id_value TEXT PRIMARY KEY,
    id_namespace TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS provisional_identities (
    provisional_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    source_ref TEXT,
    project_id TEXT,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL,
    resolved_permanent_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS permanent_identities (
    permanent_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    status TEXT NOT NULL,
    authority_record TEXT NOT NULL,
    source_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    first_legitimate_assignment_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_redirects (
    provisional_id TEXT PRIMARY KEY REFERENCES provisional_identities(provisional_id) ON DELETE RESTRICT,
    target_permanent_id TEXT NOT NULL REFERENCES permanent_identities(permanent_id) ON DELETE RESTRICT,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS duplicate_cases (
    case_id UUID PRIMARY KEY,
    provisional_id TEXT NOT NULL,
    candidate_permanent_id TEXT,
    case_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    entity_id TEXT,
    details_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_perm_name_cat ON permanent_identities(lower(category), lower(canonical_name));
CREATE INDEX IF NOT EXISTS idx_prov_status ON provisional_identities(status);
