# Genesis ↔ Eve peer exchange — opt-in pilot

Genesis and [Eve](https://github.com/Maxhm007/Eve) are separate systems. This standalone bridge is **not enabled by existing Genesis workflows**; it cannot launch agents or merge code.

## Prerequisites

- Python 3.11+
- An authenticated GitHub token with narrowly scoped **Issues: Read and write** access to the designated recipient repository, and **Issues: Read** on the local inbox repository. Prefer separate, short-lived GitHub App installation credentials over persistent personal tokens.
- A securely provisioned random shared secret of at least 32 characters, configured in the two environments: `GENESIS_EVE_SHARED_SECRET` for Genesis and `EVE_PEER_SHARED_SECRET` for Eve. Do **not** add credentials to git, issues, logs, or shell history.

## Manual Genesis → Eve proposal

```sh
python scripts/eve_peer_bridge.py prepare hypothesis "Compare two research strategies" "Improve independent testing" > proposal.json
python scripts/eve_peer_bridge.py send proposal.json
```

The second command uses `GENESIS_EVE_GITHUB_TOKEN`. It posts an HMAC-signed JSON envelope to a new issue in the Eve repository. Eve can verify and hold it for review using `python -m eve github-receive ISSUE_NUMBER`.

## Manual Eve → Genesis proposal

From Eve, `python -m eve propose critique "Check a baseline" "Avoid confirmation bias" > proposal.json`, then `python -m eve sign proposal.json > envelope.json`, followed by `python -m eve github-send envelope.json`. On Genesis, run `python scripts/eve_peer_bridge.py receive ISSUE_NUMBER`.

## Boundaries

- HMAC does not distinguish holders of the shared secret. Rotate credentials and replace with per-agent asymmetric identities before unattended exchange.
- Human must explicitly launch CLI; no scheduled delivery, model execution or auto-merge.
- GitHub issues are only transport. Never treat a peer message as an authorized instruction or execute any code it contains.
- Genesis receive prints a verified envelope but does not persist or act on it. Durable replay protection remains a future integration task.
- Eve's memory records inbound proposals for independent manual review and blocks repeated proposal IDs locally.
- GitHub issue author authentication and HMAC payload authentication are separate; both matter.
