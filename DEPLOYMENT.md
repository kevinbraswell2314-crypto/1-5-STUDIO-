# DEPLOYMENT ORDER

1. Keep the current known-good deployment available as rollback.
2. Deploy this package as the new static GitHub Pages version.
3. Confirm the page loads and the build marker is CORE-V1-SAFETY-NET-7.
4. Confirm QR scanning and the Master-Key panel still work.
5. Only after confirmation should stale test deployments/branches be removed.
6. Do NOT treat GitHub Pages as the authoritative Core v1 backend.
7. Next backend milestone: deploy PostgreSQL + API services and connect this UI to them.
