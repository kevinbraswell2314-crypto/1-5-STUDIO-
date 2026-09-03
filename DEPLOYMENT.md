# DEPLOYMENT — QR FIX 8

1. Upload/replace the deployed site files with this package.
2. Open the deployed page and hard-refresh once.
3. Scan the QTDC descriptive QR.
4. Expected result:
   - "Descriptive QTDC package recognized"
   - "WORKING / PREVIEW — Safety-Net"
   - button: "Load working package"
5. Load it.
6. Expected registry text:
   - package ID, never `undefined`
   - 0 approved Permanent-ID references
   - Librarian checksum NOT verified
   - final authoritative release blocked
7. Do not delete the prior known-good deployment until this passes.
8. Production-authority QR remains unavailable until the real Librarian backend registers a manifest and checksum.
