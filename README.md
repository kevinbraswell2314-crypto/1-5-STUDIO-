# 1-5 Studios Cinematic UI — Scene Package QR Upgrade

Single-page cinematic interface prototype for the **1-5 Studios** workflow.

## Files

- `index.html` — self-contained working site.

## 1-5 Studios QR scanner

The QR scanner is scoped to **1-5 Studios only**.

The QR code is treated as a compact carrier of **ID tags / references**, not as storage for the actual video, audio, animation, or scene files. One scan can represent one scene or a multi-scene package of roughly **30 minutes of material** by carrying the IDs that point 1-5 Studios to the stored production material.

The scanner can read:

- a single 1-5 Studios package or scene ID;
- a compact ID-tag manifest containing scene, shot, character, prop, environment, audio, animation, and other IDs;
- a QR image when the browser supports native QR detection;
- a live camera QR scan when the browser supports `BarcodeDetector`;
- manual pasted package/manifest text as a fallback.

The prototype deduplicates ID tags found in a scan and avoids creating a second local package record when the same package ID is scanned again.

### Example compact payload

`15SQR|PKG=15S-PKG-000001|DUR=30|SCENES=15S-SCN-001,15S-SCN-002|AUDIO=15S-AUD-014`

The actual media remains in 1-5 Studios; the QR only tells the system which stored identities/material belong to the package.

> Prototype note: package lookup and global uniqueness are currently browser-local. A production system should resolve these IDs against the authoritative 1-5 Studios database/service so package identity and no-duplicate guarantees work across devices.
