import os, json, hashlib, hmac
from typing import Optional, List, Dict, Any
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
REGISTRY_API_KEY = os.environ.get("REGISTRY_API_KEY")
AUTH_STATES = ("REGISTERED","ACTIVE","AUTHORITATIVE","APPROVED")

app = FastAPI(title="1-5 Studios Master Library Registry Resolver", version="1.1.0")

DEFAULT_ORIGINS = [
    "https://kevinbraswell2314-crypto.github.io",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Registry-Key"],
)

def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def auth(key):
    if REGISTRY_API_KEY and key != REGISTRY_API_KEY:
        raise HTTPException(401, "Unauthorized")

class ProvisionalInput(BaseModel):
    provisional_id: str
    category: str
    canonical_name: str
    source_ref: Optional[str] = None
    project_id: Optional[str] = None
    security_state: str = "CLEARED"
    evidence: Dict[str, Any] = {}

class RegisterDecision(BaseModel):
    provisional_id: str
    actor_id: str
    reason: str
    scope: str = "CANONICAL_LIBRARY"

@app.get("/health")
def health():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        return {"status":"ok","database":cur.fetchone()["ok"] == 1}

@app.post("/api/v1/provisionals")
def add_provisional(item: ProvisionalInput, x_registry_key: Optional[str] = Header(default=None)):
    auth(x_registry_key)
    with connect() as conn:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(
                '''INSERT INTO provisional_tags(
                     provisional_id,category,canonical_name,source_ref,project_id,security_state,evidence_json
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (provisional_id) DO UPDATE SET
                     category=EXCLUDED.category,
                     canonical_name=EXCLUDED.canonical_name,
                     source_ref=EXCLUDED.source_ref,
                     project_id=EXCLUDED.project_id,
                     security_state=EXCLUDED.security_state,
                     evidence_json=EXCLUDED.evidence_json,
                     updated_at=now()''',
                (item.provisional_id,item.category,item.canonical_name,item.source_ref,
                 item.project_id,item.security_state,json.dumps(item.evidence))
            )
    return {"status":"PROVISIONAL_RECORDED","provisional_id":item.provisional_id}

def resolve_one(cur, provisional_id):
    cur.execute("SELECT * FROM provisional_tags WHERE provisional_id=%s", (provisional_id,))
    p = cur.fetchone()
    if not p:
        return {"outcome":"ERROR","provisional_id":provisional_id,"detail":"Provisional tag not found"}

    if p["security_state"] not in ("CLEARED","FALSE_POSITIVE","RELEASED"):
        return {"outcome":"QUARANTINED","provisional_id":provisional_id}

    cur.execute("SELECT target_permanent_id FROM redirects WHERE source_id=%s", (provisional_id,))
    r = cur.fetchone()
    if r:
        return {"outcome":"VALID_MATCH","match_type":"REDIRECT",
                "provisional_id":provisional_id,"permanent_id":r["target_permanent_id"]}

    cur.execute(
        '''SELECT permanent_id FROM permanent_ids
           WHERE lower(category)=lower(%s)
             AND lower(canonical_name)=lower(%s)
             AND authority_state = ANY(%s)
           ORDER BY first_legitimate_assignment_at ASC''',
        (p["category"],p["canonical_name"],list(AUTH_STATES))
    )
    matches = cur.fetchall()

    if len(matches) == 1:
        return {"outcome":"VALID_MATCH_CANDIDATE","provisional_id":provisional_id,
                "permanent_id":matches[0]["permanent_id"],"requires_authority_decision":True}
    if len(matches) > 1:
        return {"outcome":"COLLISION","provisional_id":provisional_id,
                "candidates":[m["permanent_id"] for m in matches],"requires_authority_decision":True}

    return {"outcome":"REGISTRATION_REQUIRED","provisional_id":provisional_id,
            "reason":"No authoritative Permanent-ID match exists."}

@app.get("/api/v1/resolve/{provisional_id}")
def resolve(provisional_id: str, x_registry_key: Optional[str] = Header(default=None)):
    auth(x_registry_key)
    with connect() as conn, conn.cursor() as cur:
        return resolve_one(cur, provisional_id)

@app.post("/api/v1/resolve-batch")
def resolve_batch(ids: List[str], x_registry_key: Optional[str] = Header(default=None)):
    auth(x_registry_key)
    with connect() as conn, conn.cursor() as cur:
        return {"results":[resolve_one(cur, i) for i in ids]}

@app.post("/api/v1/register")
def register(decision: RegisterDecision, x_registry_key: Optional[str] = Header(default=None)):
    auth(x_registry_key)
    with connect() as conn:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("SELECT * FROM provisional_tags WHERE provisional_id=%s FOR UPDATE",
                        (decision.provisional_id,))
            p = cur.fetchone()
            if not p:
                raise HTTPException(404, "Provisional tag not found")
            if p["security_state"] not in ("CLEARED","FALSE_POSITIVE","RELEASED"):
                raise HTTPException(409, "Security state blocks registration")

            outcome = resolve_one(cur, decision.provisional_id)
            if outcome["outcome"] != "REGISTRATION_REQUIRED":
                raise HTTPException(409, outcome)

            cur.execute(
                "SELECT issue_permanent_id(%s,%s,%s,%s,%s,%s) AS permanent_id",
                (p["category"],p["canonical_name"],decision.actor_id,
                 decision.scope,decision.reason,p["source_ref"])
            )
            permanent_id = cur.fetchone()["permanent_id"]

            cur.execute(
                '''INSERT INTO redirects(source_id,target_permanent_id,redirect_type,reason,authority_record_id)
                   SELECT %s,%s,'PROVISIONAL_TO_PERMANENT',%s,authority_record_id
                   FROM permanent_ids WHERE permanent_id=%s''',
                (decision.provisional_id,permanent_id,decision.reason,permanent_id)
            )
            cur.execute(
                '''UPDATE provisional_tags
                   SET resolution_state='RESOLVED',resolved_permanent_id=%s,updated_at=now()
                   WHERE provisional_id=%s''',
                (permanent_id,decision.provisional_id)
            )

    return {"outcome":"REGISTERED","provisional_id":decision.provisional_id,
            "permanent_id":permanent_id}


class ManifestVerifyInput(BaseModel):
    mk: str
    manifest_id: str
    checksum: str

@app.post("/api/v1/manifests/verify")
def verify_manifest(item: ManifestVerifyInput):
    # Public read-only verifier. Do not expose REGISTRY_API_KEY in browser JavaScript.
    if item.mk.strip().upper() != "MK1":
        raise HTTPException(400, "Unsupported Master-Key authority")

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT manifest_id::text AS manifest_id, authority_code, package_code, project_id, title,
                      manifest_version, manifest_state, body_fingerprint, checksum, registered_at
                 FROM registered_manifests
                WHERE manifest_id::text=%s""",
            (item.manifest_id.strip(),)
        )
        manifest = cur.fetchone()
        if not manifest:
            raise HTTPException(404, "Registered manifest not found")

        registered = manifest["manifest_state"] in AUTH_STATES and manifest["authority_code"] == "MK1"
        expected = hashlib.sha256(
            f'MK1|{manifest["manifest_id"]}|{manifest["body_fingerprint"]}'.encode("utf-8")
        ).hexdigest()
        supplied_checksum = item.checksum.strip().lower()
        stored_checksum = (manifest["checksum"] or "").strip().lower()
        checksum_verified = bool(stored_checksum) and hmac.compare_digest(expected, stored_checksum) and hmac.compare_digest(stored_checksum, supplied_checksum)

        cur.execute(
            """SELECT
                     count(*) FILTER (WHERE r.required) AS required_count,
                     count(*) FILTER (WHERE r.required AND r.permanent_id IS NULL) AS unresolved_count,
                     count(*) FILTER (WHERE r.required AND (p.permanent_id IS NULL OR p.authority_state <> ALL(%s))) AS non_authoritative_count
                   FROM manifest_identity_refs r
                   LEFT JOIN permanent_ids p ON p.permanent_id=r.permanent_id
                  WHERE r.manifest_id::text=%s""",
            (list(AUTH_STATES), item.manifest_id.strip())
        )
        counts = cur.fetchone()
        required_tags_resolved = (counts["required_count"] or 0) > 0 and (counts["unresolved_count"] or 0) == 0 and (counts["non_authoritative_count"] or 0) == 0

        cur.execute(
            """SELECT scene_locked, canonical_packages_found, relationships_valid, reviewed_by, evidence_json, updated_at
                 FROM manifest_readiness_evidence
                WHERE manifest_id::text=%s""",
            (item.manifest_id.strip(),)
        )
        evidence = cur.fetchone() or {
            "scene_locked": False,
            "canonical_packages_found": False,
            "relationships_valid": False,
            "reviewed_by": None,
            "evidence_json": {},
            "updated_at": None,
        }

        gates = {
            "SCENE_LOCKED": bool(evidence["scene_locked"]),
            "REQUIRED_TAGS_RESOLVED": bool(required_tags_resolved),
            "CANONICAL_PACKAGES_FOUND": bool(evidence["canonical_packages_found"]),
            "RELATIONSHIPS_VALID": bool(evidence["relationships_valid"]),
            "MANIFEST_REGISTERED": bool(registered),
            "CHECKSUM_VERIFIED": bool(checksum_verified),
        }
        passed = sum(1 for value in gates.values() if value)

        return {
            "status": "QR_READY" if passed == 6 else "READINESS_BLOCKED",
            "mk": "MK1",
            "manifest_id": manifest["manifest_id"],
            "package_code": manifest["package_code"],
            "manifest_version": manifest["manifest_version"],
            "manifest_state": manifest["manifest_state"],
            "checksum_verified": checksum_verified,
            "required_reference_count": counts["required_count"] or 0,
            "gates": gates,
            "passed": passed,
            "total": 6,
            "ready": passed == 6,
            "evidence_reviewed_by": evidence["reviewed_by"],
            "evidence": evidence["evidence_json"],
        }
