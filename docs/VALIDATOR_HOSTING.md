# Independent Validator Hosting

Genesis promotion requires at least two distinct validator identities. For real failure-domain independence, run them on two separate hosts.

## Host A

Clone the repository to `/opt/genesis-ai`, create a Python virtual environment, install `requirements.txt`, install `deploy/genesis-validator.service`, and create `/etc/genesis-validator.env`:

```env
GENESIS_VALIDATOR_ID=validator-a
GENESIS_VALIDATOR_KEY_PATH=/opt/genesis-ai/state/validator_keys/validator-a.key
GENESIS_VALIDATOR_PORT=18871
```

Enable with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now genesis-validator
```

## Host B

Use the same steps with:

```env
GENESIS_VALIDATOR_ID=validator-b
GENESIS_VALIDATOR_KEY_PATH=/opt/genesis-ai/state/validator_keys/validator-b.key
GENESIS_VALIDATOR_PORT=18872
```

## Trust bootstrap

Each validator exposes `/health` with its Ed25519 public key and Constitution hash. The promotion node must trust the exact public keys out-of-band before counting their votes.

Private validator keys are generated locally on first start and must never be committed to GitHub or copied between validators.

## Validation endpoint

`POST /validate`

```json
{"candidate_commit":"<exact commit sha>"}
```

The validator independently checks:

1. candidate descends from `main`;
2. Genesis Constitution and Genesis Block are unchanged;
3. the exact candidate is exported into an isolated temporary archive sandbox;
4. the full test suite passes;
5. only then is an Ed25519-signed approval returned.

A rejection is signed in the same way and blocks promotion.

## Same-host development mode

For development only, `python run_validator_pair.py` runs and supervises two validator services with separate local keys. This proves protocol behavior but is not a separate failure domain. Production independence requires separate hosts.
