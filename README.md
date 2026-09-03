# 1-5 Studios — Core v1 Safety-Net Deployment

This package supersedes the prior static Master-Key protocol prototype.

## What changed
- Separates Security/Intake tracking IDs, provisional TMP identities, and Permanent authoritative IDs.
- A true no-match may receive a provisional TMP identity so working/preview production can continue.
- TMP identities are never represented as Permanent.
- Librarian reconciliation determines exact match, possible match, duplicate, collision, no-match registration, quarantine, or insufficient information.
- Final authoritative release remains blocked while any required identity is unresolved.
- Permanent IDs remain protected by a never-reuse rule.
- Production QR remains compact: MK1 authority + registered manifest ID + checksum.
- A descriptive/full scene-package QR is not production authority.

## Important deployment limitation
GitHub Pages is static hosting. It cannot provide the authoritative database, Security service,
Librarian resolver, Permanent Registry, atomic transactions, or real manifest/checksum verification.

This deployment is the browser/UI bridge for Core v1. It must not fabricate backend authority.
The included SQL file is the starter authoritative backend schema for the next implementation phase.

Build marker: CORE-V1-SAFETY-NET-7


## QR Fix 8
- Fixes legacy/stale registry rows that could display `undefined`.
- Never claims Librarian checksum verification unless an authoritative manifest record actually passed the six gates.
- Descriptive QTDC QR packages can now be loaded in WORKING / PREVIEW Safety-Net mode.
- Working package entries explicitly show 0 approved Permanent-ID references and final release blocked.
- Uses a new browser storage key to prevent stale state from the old deployment from contaminating the corrected QR registry.

Build marker: CORE-V1-SAFETY-NET-QR-FIX-8
