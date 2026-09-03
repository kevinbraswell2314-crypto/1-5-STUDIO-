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
