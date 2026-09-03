# 1-5 Studios — Librarian Permanent-ID Resolver v1

This is the next backend authority component before QTDC can receive a registered MK1 manifest.

## Purpose

Resolve `15S-TMP-*` working identities against the Master Library without fabricating or silently duplicating authoritative identities.

Resolution outcomes:
- EXACT_MATCH
- NO_MATCH
- COLLISION
- REGISTERED

## Important authority rule

A provisional TMP tag is never treated as a Permanent ID.

The service first searches the authoritative Permanent Identity Registry.

If an exact authoritative match exists, it returns that candidate and requires an authority decision to redirect the TMP record to the surviving Permanent ID.

If no match exists, it returns a registration candidate. A Permanent ID is only created when the controlled registration path is explicitly enabled.

## QTDC core seed

`qtdc_core_seed.json` contains the first eight reusable provisional identities:
Malik, Marcus, Lucy, Sophie, Kai, Kenji, the recurring green dinosaur, and the magical book.

## Next step after this

Run these QTDC provisional identities through the Resolver against the real Master Library. Once every required QTDC reference is resolved to authoritative Permanent IDs, submit the complete 8-scene manifest to the Manifest Registration service. That service then returns the real registered Manifest ID and verified checksum needed for the new production QR.
