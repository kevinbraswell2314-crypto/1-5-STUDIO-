# 1-5 Studios — ID Department Wired

This build keeps the front page simple and wires the QR scene-package scanner into a persistent browser-side ID Department prototype.

Flow:
QR -> manifest inventory -> registry lookup -> reuse existing ID or issue missing unique ID -> duplicate check -> package ready.

The parser inventories package, scenes, named characters, CH additions, and explicit EL inventory items. Quantity tokens such as SPACE-HELMETx6 become six individually addressable identities. Re-scanning the same package reuses the same IDs instead of issuing duplicates.

For QTDC-IMAGINATION-40S the UI now reports the real duration as 40 sec rather than 0.666666... minutes.

Important: this is still a static GitHub Pages prototype. The registry is persisted in that browser's localStorage. A production-wide registry shared across devices will require a backend/database.
