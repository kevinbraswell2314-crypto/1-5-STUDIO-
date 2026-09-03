# 1-5 Studios — Master-Key / Librarian Protocol Upgrade

Corrects the prior browser-side ID issuance behavior.

Implemented rules:
- Scene Roll and Animator do NOT issue Permanent IDs.
- Exact match -> reuse existing Permanent ID + canonical package.
- Multiple approved matches -> stop for human selection.
- No match -> send only the unresolved element to Librarian Registration.
- Controlled registration path is displayed in the UI.
- Production QR contains only MK1 authority + registered manifest ID + checksum.
- Descriptive/full scene-manifest QRs HARD STOP as non-production-ready.
- Six readiness gates are enforced in the interface.

Static-host limitation:
GitHub Pages does not provide the authoritative Librarian Registry/backend. This build refuses to fake manifest lookup or checksum verification. A real Librarian backend connection is required for production.

Build marker: MASTER-KEY-PROTOCOL-6
