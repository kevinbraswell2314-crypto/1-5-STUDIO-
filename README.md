# 1-5 Studios QR End-to-End Fix — QR-FIX-4

This build fixes the scene-package manifest parser for the real compact 1-5S QR format.

Validated against the provided QR payload:
- Header: 1-5S
- Package: QTDC-IMAGINATION-40S
- Scenes: S01 through S08
- Compact timing: 8 x 5 seconds = 40 seconds

The old false rejection "QR must contain one or more 15S ID tags" has been removed for valid 1-5S manifests.
