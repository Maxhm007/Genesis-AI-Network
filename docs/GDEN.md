# Genesis Decentralized Evolution Network (GDEN)

## Mission

GDEN is the peer-to-peer evolution layer for Genesis AI Network. Its purpose is to let independently operated Genesis nodes cooperate, contribute resources and accumulate validated improvements while preserving the permanent Genesis mission and Constitution.

Genesis remains provider-independent and node-owner controlled. Network usage may create observations and candidate improvements, but usage alone never promotes code, scientific claims or permissions.

## V0.1 implemented

- Persistent Ed25519 node identity generated locally on first run.
- Node ID derived from the node public key.
- Signed peer advertisements at `/genesis/handshake`.
- Constitution-hash and protocol checks before authenticated peer status.
- Owner-controlled contribution limits for CPU, memory, storage, research, validation, model inference and task execution.
- Signed state-root advertisement.
- Local append-only signed evolution ledger using a hash chain.
- Tamper detection for peer advertisements and local ledger history.
- Offline-safe node state under `state/gden/`.
- Private node keys excluded from Git by `.gitignore`.

## Not yet implemented

GDEN V0.1 is not a cryptocurrency and does not use proof-of-work. It does not yet implement decentralized consensus over competing ledger histories, automatic internet-wide peer discovery, NAT traversal, distributed task settlement, replicated knowledge blobs, or durable validator reputation.

## Evolution rule

```text
usage
  -> observation
  -> signed candidate/provenance
  -> benchmark/test
  -> independent validation
  -> accepted network state
  -> compatible peers synchronize
```

No peer may use network consensus to override the Genesis Constitution, protected identity, node-owner resource limits or validation requirements.

## Run a node

```bash
python run_peer_node.py --port 8761
```

The first run creates a local cryptographic identity under `state/gden/`. To connect known peers:

```bash
python run_peer_node.py --port 8761 --peer http://127.0.0.1:8762
```

Model inference is opt-in:

```bash
python run_peer_node.py --port 8761 --allow-model-inference
```

## Next protocol milestones

1. Signed peer discovery records and bootstrap lists.
2. Replay-resistant challenge/response handshakes.
3. Replicated content-addressed state manifests.
4. Distributed task offers, claims and completion proofs.
5. Independent validator identities and durable trust policies.
6. Multi-peer ledger reconciliation and fork-choice/consensus rules based on validated evidence rather than compute waste.
7. Candidate/release propagation with exact hashes and rollback proofs.
