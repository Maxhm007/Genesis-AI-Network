# Security Policy

Genesis AI Network is public by design, but public source code does **not** mean public secrets, private identities, personal data, or sensitive runtime state.

## Never commit

Do not commit any of the following:

- node or release private signing keys
- API keys, personal access tokens, OAuth secrets, passwords, cookies, session tokens, SMTP credentials, or service-account credentials
- `.env` files containing real values
- private SSH/TLS keys or PKCS#12/PFX bundles
- personal user conversations or identifying user data
- confidential research datasets or unpublished security findings
- local runtime databases, learning memory, peer-local state, or sensitive logs

Use environment variables, local ignored files, or an appropriate external secret store. Public keys, hashes, signatures, release manifests, and non-sensitive provenance may be public.

## Genesis identity boundary

`GENESIS_CONSTITUTION.md` and `GENESIS_BLOCK.json` are protected public identity artifacts. Private node keys are local operator secrets and must never become part of the canonical Genesis identity or repository history.

## Reporting a vulnerability

Do not publish exploitable vulnerabilities, private keys, credentials, or sensitive data in a public GitHub issue. Contact the repository owner privately through an appropriate private channel before public disclosure. After remediation, a public advisory may document the issue without exposing live secrets.

## Secret response procedure

If a secret is ever committed:

1. Treat it as compromised immediately, even if the commit is later deleted or the repository becomes private.
2. Revoke/rotate the credential or key first.
3. Remove it from the current tree.
4. Rewrite Git history when appropriate and coordinate a force-update carefully.
5. Re-scan all refs and releases.
6. Review logs for unauthorized use.

## Automated guard

`python scripts/secret_guard.py --history` scans tracked files and reachable Git-history blobs for common credential/private-key signatures and risky secret-bearing filenames. The `Genesis Secret Guard` workflow runs this check on pushes, pull requests, and a recurring schedule.

The scanner is a defense-in-depth control, not a guarantee that every possible secret format will be detected.
