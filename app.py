import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required; authoritative registry is not configured")

app = FastAPI(title="1-5 Studios Librarian Resolver", version="1.0.0")
ACTIVE_STATUSES = ("REGISTERED", "ACTIVE", "APPROVED", "AUTHORITATIVE")

class ProvisionalIn(BaseModel):
    provisional_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    source_ref: Optional[str] = None
    project_id: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)

class AuthorityDecision(BaseModel):
    provisional_id: str
    action: Literal["REDIRECT_TO_EXISTING", "QUARANTINE"]
    target_permanent_id: Optional[str] = None
    approved_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: Dict[str, Any] = Field(default_factory=dict)

class AuthorityRegistration(BaseModel):
    permanent_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    authority_type: str = Field(min_length=1)
    evidence: Dict[str, Any] = Field(default_factory=dict)

def actor(request: Request, x_actor_id: Optional[str] = Header(default=None)) -> str:
    value = x_actor_id or request.headers.get("authorization")
    if not value:
        raise HTTPException(401, "authenticated actor required")
    return x_actor_id or value.removeprefix("Bearer ")

@contextmanager
def db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            yield conn

def audit(cur, correlation_id, actor_type, actor_id, action, target_type, target_id, result, metadata, request_id=None):
    cur.execute("""INSERT INTO audit_events
      (correlation_id,request_id,transaction_id,actor_type,actor_id,action,target_type,target_id,result,metadata_json)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
      (correlation_id, request_id, str(uuid.uuid4()), actor_type, actor_id, action,
       target_type, target_id, result, json.dumps(metadata)))

@app.get("/health")
def health():
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "authority": "postgresql-master-library"}
    except Exception:
        raise HTTPException(503, "authoritative registry unavailable")

@app.post("/api/v1/identities/provisional")
def upsert_provisional(payload: ProvisionalIn, request: Request, actor_id: str = Depends(actor)):
    correlation = uuid.uuid4()
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO provisional_identities
          (provisional_id,category,canonical_name,source_ref,project_id,evidence_json,status)
          VALUES (%s,%s,%s,%s,%s,%s::jsonb,'PROVISIONAL')
          ON CONFLICT (provisional_id) DO UPDATE SET category=EXCLUDED.category,
          canonical_name=EXCLUDED.canonical_name, source_ref=EXCLUDED.source_ref,
          project_id=EXCLUDED.project_id, evidence_json=EXCLUDED.evidence_json, updated_at=now()
          RETURNING provisional_id""",
          (payload.provisional_id, payload.category, payload.canonical_name, payload.source_ref,
           payload.project_id, json.dumps(payload.evidence)))
        audit(cur, correlation, "SERVICE", actor_id, "PROVISIONAL_UPSERT", "PROVISIONAL_ID",
              payload.provisional_id, "RECORDED", payload.evidence, request.headers.get("x-request-id"))
    return {"status": "PROVISIONAL", "provisional_id": payload.provisional_id}

@app.post("/api/v1/identities/resolve")
def resolve(payload: ProvisionalIn, request: Request, actor_id: str = Depends(actor)):
    correlation = uuid.uuid4()
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT target_permanent_id FROM identity_redirects WHERE provisional_id=%s", (payload.provisional_id,))
        redirect = cur.fetchone()
        if redirect:
            cur.execute("SELECT permanent_id,category,canonical_name,status,authority_record_id FROM permanent_identities WHERE permanent_id=%s", (redirect["target_permanent_id"],))
            row = cur.fetchone()
            evidence = {"source": "identity_redirects", "authority_record_id": str(row["authority_record_id"])}
            audit(cur, correlation, "SERVICE", actor_id, "RESOLVE", "PROVISIONAL_ID", payload.provisional_id, "EXACT_MATCH", evidence, request.headers.get("x-request-id"))
            return {"outcome": "EXACT_MATCH", "provisional_id": payload.provisional_id, "permanent_id": row["permanent_id"], "registry_evidence": {**dict(row), **evidence}}

        cur.execute("""SELECT permanent_id,category,canonical_name,status,authority_record_id,created_at,first_legitimate_assignment_at
          FROM permanent_identities WHERE lower(category)=lower(%s) AND lower(canonical_name)=lower(%s)
          AND status = ANY(%s) ORDER BY created_at ASC""", (payload.category, payload.canonical_name, list(ACTIVE_STATUSES)))
        rows = cur.fetchall()
        if len(rows) == 1:
            match = dict(rows[0])
            cur.execute("""INSERT INTO duplicate_cases (provisional_id,candidate_permanent_id,case_type,evidence_json)
              VALUES (%s,%s,'EXACT_MATCH',%s::jsonb)""", (payload.provisional_id, match["permanent_id"], json.dumps({"registry_row": match})))
            audit(cur, correlation, "SERVICE", actor_id, "RESOLVE", "PROVISIONAL_ID", payload.provisional_id, "EXACT_MATCH_CANDIDATE", {"registry_row": match}, request.headers.get("x-request-id"))
            return {"outcome": "EXACT_MATCH", "requires_authority_decision": True, "provisional_id": payload.provisional_id, "candidate_permanent_id": match["permanent_id"], "registry_evidence": match}
        if len(rows) > 1:
            candidates = [dict(r) for r in rows]
            cur.execute("INSERT INTO duplicate_cases (provisional_id,case_type,evidence_json) VALUES (%s,'COLLISION',%s::jsonb)", (payload.provisional_id, json.dumps({"candidates": candidates})))
            audit(cur, correlation, "SERVICE", actor_id, "RESOLVE", "PROVISIONAL_ID", payload.provisional_id, "COLLISION", {"candidates": candidates}, request.headers.get("x-request-id"))
            return {"outcome": "COLLISION", "requires_authority_decision": True, "provisional_id": payload.provisional_id, "candidates": candidates}
        cur.execute("INSERT INTO duplicate_cases (provisional_id,case_type,evidence_json) VALUES (%s,'NO_MATCH',%s::jsonb)", (payload.provisional_id, json.dumps({"searched_category": payload.category, "searched_name": payload.canonical_name})))
        audit(cur, correlation, "SERVICE", actor_id, "RESOLVE", "PROVISIONAL_ID", payload.provisional_id, "NO_MATCH_REGISTRATION_REQUIRED", {"searched_category": payload.category, "searched_name": payload.canonical_name}, request.headers.get("x-request-id"))
        return {"outcome": "NO_MATCH / REGISTRATION REQUIRED", "provisional_id": payload.provisional_id, "registry_evidence": {"authoritative_candidates": []}}

@app.post("/api/v1/identities/authority-decision")
def decision(payload: AuthorityDecision, request: Request, actor_id: str = Depends(actor)):
    if actor_id != payload.approved_by:
        raise HTTPException(403, "approved_by must match authenticated actor")
    correlation = uuid.uuid4()
    with db() as conn:
        cur = conn.cursor()
        if payload.action == "REDIRECT_TO_EXISTING":
            if not payload.target_permanent_id: raise HTTPException(400, "target_permanent_id required")
            cur.execute("SELECT permanent_id FROM permanent_identities WHERE permanent_id=%s AND status=ANY(%s)", (payload.target_permanent_id, list(ACTIVE_STATUSES)))
            if not cur.fetchone(): raise HTTPException(404, "authoritative target not found")
            cur.execute("INSERT INTO authority_records (authority_type,authority_subject,decision,evidence_json,approved_by) VALUES ('IDENTITY_REDIRECT',%s,%s,%s::jsonb,%s) RETURNING authority_record_id", (payload.provisional_id, payload.action, json.dumps(payload.evidence), actor_id))
            auth = cur.fetchone()["authority_record_id"]
            cur.execute("INSERT INTO identity_redirects (provisional_id,target_permanent_id,reason,authority_record_id) VALUES (%s,%s,%s,%s) ON CONFLICT (provisional_id) DO UPDATE SET target_permanent_id=EXCLUDED.target_permanent_id,reason=EXCLUDED.reason,authority_record_id=EXCLUDED.authority_record_id", (payload.provisional_id, payload.target_permanent_id, payload.reason, auth))
            cur.execute("UPDATE provisional_identities SET status='RESOLVED',resolved_permanent_id=%s,updated_at=now() WHERE provisional_id=%s", (payload.target_permanent_id, payload.provisional_id))
        else:
            cur.execute("UPDATE provisional_identities SET status='QUARANTINED',updated_at=now() WHERE provisional_id=%s", (payload.provisional_id,))
            cur.execute("UPDATE duplicate_cases SET status='QUARANTINED',resolved_at=now() WHERE provisional_id=%s AND status='OPEN'", (payload.provisional_id,))
        audit(cur, correlation, "HUMAN", actor_id, "AUTHORITY_DECISION", "PROVISIONAL_ID", payload.provisional_id, payload.action, payload.model_dump(), request.headers.get("x-request-id"))
    return {"status": "RECORDED", "outcome": payload.action, "provisional_id": payload.provisional_id}

@app.post("/api/v1/identities/authority-register")
def authority_register(payload: AuthorityRegistration, request: Request, actor_id: str = Depends(actor)):
    if actor_id != payload.approved_by: raise HTTPException(403, "approved_by must match authenticated actor")
    correlation = uuid.uuid4()
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM id_history WHERE id_value=%s", (payload.permanent_id,))
        if cur.fetchone(): raise HTTPException(409, "Permanent ID already exists in immutable history")
        cur.execute("INSERT INTO authority_records (authority_type,authority_subject,decision,evidence_json,approved_by) VALUES (%s,%s,'REGISTER',%s::jsonb,%s) RETURNING authority_record_id", (payload.authority_type, payload.permanent_id, json.dumps(payload.evidence), actor_id))
        auth = cur.fetchone()["authority_record_id"]
        cur.execute("INSERT INTO permanent_identities (permanent_id,category,canonical_name,status,authority_record_id) VALUES (%s,%s,%s,'REGISTERED',%s)", (payload.permanent_id, payload.category, payload.canonical_name, auth))
        cur.execute("INSERT INTO id_history (id_value,id_namespace,status) VALUES (%s,'PERMANENT','ISSUED')", (payload.permanent_id,))
        audit(cur, correlation, "HUMAN", actor_id, "PERMANENT_ID_REGISTERED", "PERMANENT_ID", payload.permanent_id, "REGISTERED", payload.model_dump(), request.headers.get("x-request-id"))
    return {"status": "REGISTERED", "permanent_id": payload.permanent_id, "authority_record_id": str(auth)}
