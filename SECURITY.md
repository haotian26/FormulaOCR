# Security policy

Security fixes are provided for the latest published FormulaOCR release. Use a
private GitHub security advisory for suspected vulnerabilities. Do not include
API keys, private formula images or history databases in a public issue.

Remote endpoints require HTTPS; HTTP is accepted only for localhost loopback.
The Tauri capability and CSP scope should remain minimal. Model and dependency
hashes must be verified before packaging.
