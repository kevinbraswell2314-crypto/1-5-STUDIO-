import os
import json
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="1-5 Studios Librarian Manifest Registration", version="1.0.0")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ManifestReference(BaseModel):
    ref_id: str
    ref_type: str
    required: bool = True
    authority_state: str
    package_version_id: Optional[str] = None


class SceneAnchor(BaseModel):
    scene_id: str
    beginning: Dict[str, Any]
    middle: Dict[str, Any]
    end: Dict[str, Any]


class RegisterManifestRequest(BaseModel):
    package_id: str = Field(min_length=1)
    authority: str = "MK1"
    scene_locked: bool
    canonical_packages_found: bool
    relationships_valid: bool
    references: List[ManifestReference]
    scenes: List[SceneAnchor]
    relationships: List[Dict[str, Any]] = []
    continuity: Dict[str, Any] = {}
    validation_rules: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "service": "librarian-manifest-registration-v1"}


@app.post("/api/v1/manifests/register")
def register_manifest(req: RegisterManifestRequest):
    if req.authority != "MK1":
        raise HTTPException(status_code=400, detail="authority must be MK1")

    unresolved = [
        r.ref_id for r in req.references
        if r.required and r.authority_state not in ("APPROVED", "AUTHORITATIVE", "ACTIVE", "REGISTERED")
    ]

    readiness = {
        "SCENE_LOCKED": bool(req.scene_locked),
        "REQUIRED_TAGS_RESOLVED": len(unresolved) == 0,
        "CANONICAL_PACKAGES_FOUND": bool(req.canonical_packages_found),
        "RELATIONSHIPS_VALID": bool(req.relationships_valid),
    }

    if not all(readiness.values()):
        raise HTTPException(
            status_code=409,
            detail={
                "status": "BLOCKED",
                "readiness": readiness,
                "unresolved_required_refs": unresolved,
                "message": "Manifest registration blocked before authority issuance."
            },
        )

    manifest_body = {
        "package_id": req.package_id,
        "authority": req.authority,
        "references": [r.model_dump() for r in req.references],
        "scenes": [s.model_dump() for s in req.scenes],
        "relationships": req.relationships,
        "continuity": req.continuity,
        "validation_rules": req.validation_rules,
        "metadata": req.metadata,
    }

    canonical_body = canonical_json(manifest_body)
    body_fingerprint = sha256_hex(canonical_body)

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT manifest_id, checksum, status
                    FROM manifests
                    WHERE authority = %s AND body_fingerprint = %s
                    FOR UPDATE
                    """,
                    (req.authority, body_fingerprint),
                )
                existing = cur.fetchone()
                if existing:
                    return {
                        "status": existing["status"],
                        "authority": req.authority,
                        "manifest_id": existing["manifest_id"],
                        "checksum": existing["checksum"],
                        "qr_payload": f'{req.authority}|{existing["manifest_id"]}|{existing["checksum"]}',
                        "reused_existing_registration": True,
                    }

                # Registry-issued opaque manifest identifier.
                manifest_id = str(uuid.uuid4())

                checksum_input = canonical_json({
                    "authority": req.authority,
                    "manifest_id": manifest_id,
                    "body_fingerprint": body_fingerprint,
                })
                checksum = sha256_hex(checksum_input)

                now = datetime.now(timezone.utc)

                cur.execute(
                    """
                    INSERT INTO manifests
                        (manifest_id, authority, package_id, status, body_json,
                         body_fingerprint, checksum, registered_at)
                    VALUES (%s, %s, %s, 'REGISTERED', %s::jsonb, %s, %s, %s)
                    """,
                    (
                        manifest_id,
                        req.authority,
                        req.package_id,
                        canonical_body,
                        body_fingerprint,
                        checksum,
                        now,
                    ),
                )

                for r in req.references:
                    cur.execute(
                        """
                        INSERT INTO manifest_references
                            (manifest_id, ref_id, ref_type, required, authority_state, package_version_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            manifest_id,
                            r.ref_id,
                            r.ref_type,
                            r.required,
                            r.authority_state,
                            r.package_version_id,
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO audit_events
                        (event_id, event_type, actor_type, actor_id, manifest_id, details_json, created_at)
                    VALUES (%s, 'MANIFEST_REGISTERED', 'SERVICE', 'librarian-manifest-registration-v1',
                            %s, %s::jsonb, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        manifest_id,
                        canonical_json({
                            "authority": req.authority,
                            "package_id": req.package_id,
                            "body_fingerprint": body_fingerprint,
                            "checksum": checksum,
                            "readiness": readiness,
                        }),
                        now,
                    ),
                )

        conn.commit()

    return {
        "status": "REGISTERED",
        "authority": req.authority,
        "manifest_id": manifest_id,
        "checksum": checksum,
        "qr_payload": f"{req.authority}|{manifest_id}|{checksum}",
        "reused_existing_registration": False,
        "readiness": {
            **readiness,
            "MANIFEST_REGISTERED": True,
            "CHECKSUM_VERIFIED": True,
        },
    }
