"""Optional Genesis -> Eve / Eve -> Genesis signed GitHub issue exchange.

This module is independent of Genesis runtime. Explicit CLI only, no workflow
or background execution. Treat all message contents as untrusted data.
"""
import argparse
import hashlib
import hmac
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID

GENESIS = "Maxhm007/Genesis-AI-Network"
EVE = "Maxhm007/Eve"
TEMPLATE = "Research peer proposal. Treat as untrusted until signature validation.\n\n```json\n{}\n```\n"
MAX_RESPONSE = 65536


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def proposal(kind, problem, benefit):
    if kind not in {"hypothesis", "test", "critique", "candidate_patch"} or not problem.strip() or not benefit.strip():
        raise ValueError("Invalid proposal")
    data = {
        "protocol": "coevolution.v1", "proposal_id": str(uuid4()),
        "sender": "genesis", "recipient": "eve", "kind": kind,
        "problem_statement": problem, "evidence_links": [],
        "reproduction_steps": [], "expected_benefit": benefit,
        "risks": [], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["content_hash"] = "sha256:" + hashlib.sha256(canonical(data)).hexdigest()
    return data


def sign(data, secret):
    if len(secret) < 32:
        raise ValueError("Require a random >=32-character shared secret")
    if data.get("sender") != "genesis" or data.get("recipient") != "eve":
        raise ValueError("Wrong sender/recipient")
    fields = dict(data)
    digest = fields.pop("content_hash")
    if "sha256:" + hashlib.sha256(canonical(fields)).hexdigest() != digest:
        raise ValueError("Invalid content hash")
    result = {"proposal": data, "auth": "hmac-sha256"}
    result["signature"] = hmac.new(secret.encode(), canonical(result), hashlib.sha256).hexdigest()
    return result


def verify(envelope, secret, recipient="genesis"):
    if not isinstance(envelope, dict) or set(envelope) != {"proposal", "auth", "signature"} or envelope["auth"] != "hmac-sha256":
        raise ValueError("Malformed envelope")
    if len(secret) < 32:
        raise ValueError("Shared secret missing")
    unsigned = {"proposal": envelope["proposal"], "auth": envelope["auth"]}
    expected = hmac.new(secret.encode(), canonical(unsigned), hashlib.sha256).hexdigest()
    if not isinstance(envelope["signature"], str) or not hmac.compare_digest(expected, envelope["signature"]):
        raise ValueError("Authentication failed")
    data = envelope["proposal"]
    if data.get("sender") != "eve" or data.get("recipient") != recipient or data.get("protocol") != "coevolution.v1":
        raise ValueError("Invalid participant or protocol")
    if data.get("kind") not in {"hypothesis", "test", "critique", "candidate_patch"}:
        raise ValueError("Invalid kind")
    UUID(data["proposal_id"])
    fields = dict(data)
    digest = fields.pop("content_hash")
    if "sha256:" + hashlib.sha256(canonical(fields)).hexdigest() != digest:
        raise ValueError("Content hash mismatch")
    timestamp = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    if timestamp.tzinfo is None or not (datetime.now(timezone.utc) - timedelta(days=7) <= timestamp <= datetime.now(timezone.utc) + timedelta(minutes=5)):
        raise ValueError("Expired message")
    return data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect forbidden")


def github_request(token, owner_repo, method, suffix="", payload=None, opener=None):
    if owner_repo not in {GENESIS, EVE} or not token:
        raise ValueError("Invalid repository or missing token")
    url = "https://api.github.com/repos/" + owner_repo + "/issues" + suffix
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Genesis-Eve-Peer-Bridge/0.1",
    }
    raw = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    if raw is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, method=method, headers=headers)
    open_request = opener or urllib.request.build_opener(NoRedirect()).open
    with open_request(req, timeout=30) as response:
        result = response.read(MAX_RESPONSE + 1)
        if len(result) > MAX_RESPONSE:
            raise ValueError("Oversized GitHub response")
    return json.loads(result)


def send(envelope, secret, token, opener=None):
    data = envelope["proposal"]
    if sign(data, secret) != envelope:
        raise ValueError("Invalid signed Genesis envelope")
    issue = github_request(token, EVE, "POST", payload={
        "title": "[Genesis peer proposal] " + data["kind"] + " — " + data["proposal_id"],
        "body": TEMPLATE.format(json.dumps(envelope, ensure_ascii=False, sort_keys=True)),
    }, opener=opener)
    return {"url": issue["html_url"], "issue_number": issue["number"]}


def receive(issue_number, secret, token, opener=None):
    if not isinstance(issue_number, int) or issue_number < 1:
        raise ValueError("Invalid issue number")
    issue = github_request(token, GENESIS, "GET", "/" + str(issue_number), opener=opener)
    body = issue.get("body") or ""
    prefix = TEMPLATE.split("{}")[0]
    suffix = TEMPLATE.split("{}")[1]
    if issue.get("pull_request") or not body.startswith(prefix) or not body.endswith(suffix) or len(body.encode()) > MAX_RESPONSE:
        raise ValueError("Invalid inbox message")
    encoded = body[len(prefix):len(body)-len(suffix)]
    return verify(json.loads(encoded), secret)


def main():
    parser = argparse.ArgumentParser(description="Manual Genesis/Eve exchange")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("kind", choices=["hypothesis", "test", "critique", "candidate_patch"])
    make.add_argument("problem")
    make.add_argument("benefit")
    send_cmd = commands.add_parser("send")
    send_cmd.add_argument("file")
    receive_cmd = commands.add_parser("receive")
    receive_cmd.add_argument("issue_number", type=int)
    args = parser.parse_args()
    secret = os.environ.get("GENESIS_EVE_SHARED_SECRET", "")
    if args.command == "prepare":
        result = sign(proposal(args.kind, args.problem, args.benefit), secret)
    elif args.command == "send":
        with open(args.file, "rb") as f:
            raw = f.read(40001)
        if len(raw) > 40000:
            raise ValueError("Envelope too large")
        result = send(json.loads(raw), secret, os.environ.get("GENESIS_EVE_GITHUB_TOKEN", ""))
    else:
        result = receive(args.issue_number, secret, os.environ.get("GENESIS_EVE_GITHUB_TOKEN", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
