import os, json, uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="1-5 Studios Librarian Permanent-ID Resolver", version="1.0.0")

AUTHORITATIVE_STATES = {"REGISTERED", "ACTIVE", "AUTHORITATIVE", "APPROVED"}

class ResolveRequest(BaseModel):
    provisional_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    source_ref: Optional[str] = None
    project_id: Optional[str] = None
    evidence: Dict[str, Any] = {}
    allow_registration: bool = False

class AuthorityDecision(BaseModel):
    provisional_id: str
    action: str
    target_permanent_id: Optional[str] = None
    approved_by: Optional[str] = None
    reason: Optional[str] = None

def now():
    return datetime.now(timezone.utc)

@app.get("/health")
def health():
    return {"status":"ok","service":"librarian-permanent-id-resolver-v1"}

@app.post("/api/v1/identities/provisional")
def upsert_provisional(req: ResolveRequest):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO provisional_identities
                    (provisional_id, category, canonical_name, source_ref, project_id, evidence_json,
                     status, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,'PROVISIONAL',%s,%s)
                    ON CONFLICT (provisional_id) DO UPDATE SET
                      category=EXCLUDED.category,
                      canonical_name=EXCLUDED.canonical_name,
                      source_ref=EXCLUDED.source_ref,
                      project_id=EXCLUDED.project_id,
                      evidence_json=EXCLUDED.evidence_json,
                      updated_at=EXCLUDED.updated_at
                """, (req.provisional_id, req.category, req.canonical_name, req.source_ref,
                      req.project_id, json.dumps(req.evidence), now(), now()))
        conn.commit()
    return {"status":"PROVISIONAL","provisional_id":req.provisional_id}

@app.post("/api/v1/identities/resolve")
def resolve(req: ResolveRequest):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                # 1) exact existing redirect
                cur.execute("""
                    SELECT target_permanent_id
                    FROM identity_redirects
                    WHERE provisional_id=%s
                """, (req.provisional_id,))
                redirect = cur.fetchone()
                if redirect:
                    return {
                        "resolution":"EXACT_MATCH",
                        "provisional_id":req.provisional_id,
                        "permanent_id":redirect["target_permanent_id"],
                        "message":"Existing authoritative redirect found."
                    }

                # 2) exact authoritative canonical match by category + canonical name
                cur.execute("""
                    SELECT permanent_id, category, canonical_name, status
                    FROM permanent_identities
                    WHERE lower(category)=lower(%s)
                      AND lower(canonical_name)=lower(%s)
                      AND status IN ('REGISTERED','ACTIVE','AUTHORITATIVE','APPROVED')
                    ORDER BY created_at ASC
                """, (req.category, req.canonical_name))
                rows = cur.fetchall()

                if len(rows) == 1:
                    match = rows[0]
                    cur.execute("""
                        INSERT INTO duplicate_cases
                        (case_id, provisional_id, candidate_permanent_id, case_type, status, created_at)
                        VALUES (%s,%s,%s,'EXACT_MATCH','OPEN',%s)
                    """, (str(uuid.uuid4()), req.provisional_id, match["permanent_id"], now()))
                    return {
                        "resolution":"EXACT_MATCH",
                        "provisional_id":req.provisional_id,
                        "candidate_permanent_id":match["permanent_id"],
                        "requires_authority_decision": True
                    }

                if len(rows) > 1:
                    return {
                        "resolution":"COLLISION",
                        "provisional_id":req.provisional_id,
                        "candidates":[r["permanent_id"] for r in rows],
                        "requires_authority_decision": True
                    }

                # 3) no exact match: return registration candidate, never auto-issue unless explicitly enabled
                if not req.allow_registration:
                    return {
                        "resolution":"NO_MATCH",
                        "provisional_id":req.provisional_id,
                        "registration_candidate": True,
                        "message":"No authoritative match found. Registration authority review required."
                    }

                # 4) controlled registration path
                permanent_id = f"15S-{req.category.upper()}-{uuid.uuid4()}"
                cur.execute("""
                    INSERT INTO permanent_identities
                    (permanent_id, category, canonical_name, status, authority_record,
                     source_ref, created_at, first_legitimate_assignment_at)
                    VALUES (%s,%s,%s,'REGISTERED',%s,%s,%s,%s)
                """, (
                    permanent_id, req.category, req.canonical_name,
                    "librarian-permanent-id-resolver-v1", req.source_ref, now(), now()
                ))

                cur.execute("""
                    INSERT INTO id_history
                    (id_value, id_namespace, status, created_at)
                    VALUES (%s,'PERMANENT','ISSUED',%s)
                """, (permanent_id, now()))

                cur.execute("""
                    INSERT INTO identity_redirects
                    (provisional_id, target_permanent_id, reason, created_at)
                    VALUES (%s,%s,'LIBRARIAN_REGISTERED',%s)
                """, (req.provisional_id, permanent_id, now()))

                cur.execute("""
                    UPDATE provisional_identities
                    SET status='RESOLVED', resolved_permanent_id=%s, updated_at=%s
                    WHERE provisional_id=%s
                """, (permanent_id, now(), req.provisional_id))

                cur.execute("""
                    INSERT INTO audit_events
                    (event_id, event_type, actor_type, actor_id, entity_id, details_json, created_at)
                    VALUES (%s,'PERMANENT_ID_REGISTERED','SERVICE',
                            'librarian-permanent-id-resolver-v1',%s,%s::jsonb,%s)
                """, (
                    str(uuid.uuid4()), permanent_id,
                    json.dumps({
                        "provisional_id":req.provisional_id,
                        "category":req.category,
                        "canonical_name":req.canonical_name
                    }),
                    now()
                ))

        conn.commit()

    return {
        "resolution":"REGISTERED",
        "provisional_id":req.provisional_id,
        "permanent_id":permanent_id,
        "status":"REGISTERED"
    }

@app.post("/api/v1/identities/authority-decision")
def authority_decision(req: AuthorityDecision):
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                if req.action == "REDIRECT_TO_EXISTING":
                    if not req.target_permanent_id:
                        raise HTTPException(400, "target_permanent_id required")
                    cur.execute("""
                        SELECT permanent_id FROM permanent_identities
                        WHERE permanent_id=%s
                          AND status IN ('REGISTERED','ACTIVE','AUTHORITATIVE','APPROVED')
                    """, (req.target_permanent_id,))
                    if not cur.fetchone():
                        raise HTTPException(404, "authoritative target not found")

                    cur.execute("""
                        INSERT INTO identity_redirects
                        (provisional_id, target_permanent_id, reason, created_at)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (provisional_id) DO UPDATE SET
                          target_permanent_id=EXCLUDED.target_permanent_id,
                          reason=EXCLUDED.reason,
                          created_at=EXCLUDED.created_at
                    """, (req.provisional_id, req.target_permanent_id,
                          req.reason or "AUTHORITATIVE_MATCH", now()))

                    cur.execute("""
                        UPDATE provisional_identities
                        SET status='RESOLVED', resolved_permanent_id=%s, updated_at=%s
                        WHERE provisional_id=%s
                    """, (req.target_permanent_id, now(), req.provisional_id))

                elif req.action == "QUARANTINE":
                    cur.execute("""
                        UPDATE provisional_identities
                        SET status='QUARANTINED', updated_at=%s
                        WHERE provisional_id=%s
                    """, (now(), req.provisional_id))

                else:
                    raise HTTPException(400, "Unsupported authority action")

                cur.execute("""
                    INSERT INTO audit_events
                    (event_id,event_type,actor_type,actor_id,entity_id,details_json,created_at)
                    VALUES (%s,'AUTHORITY_DECISION','HUMAN',%s,%s,%s::jsonb,%s)
                """, (
                    str(uuid.uuid4()),
                    req.approved_by or "UNSPECIFIED_AUTHORITY",
                    req.provisional_id,
                    json.dumps(req.model_dump()),
                    now()
                ))
        conn.commit()

    return {"status":"RECORDED","provisional_id":req.provisional_id,"action":req.action}
