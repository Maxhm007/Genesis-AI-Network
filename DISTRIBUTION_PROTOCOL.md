# Distribution Protocol

## Goal

A canonical Genesis AI release must be identifiable by cryptographic content, not by where it is hosted.

## Release artifacts

Each release should include:

- version
- manifest
- SHA-256 hashes
- release signature(s)
- constitution hash
- source commit
- compatibility metadata

## Mirrors

Releases may be mirrored to GitHub, Google Drive, Dropbox, TeraBox, IPFS-compatible storage, archival networks, and community nodes.

Mirrors are transport/storage locations only. A mirror does not define authenticity.

## Verification

A node should:

1. fetch a candidate release;
2. verify the manifest hash;
3. verify file hashes;
4. verify authorized release signatures;
5. verify the Genesis Constitution hash;
6. reject rollback or incompatible releases;
7. install only after policy checks succeed.

## Write access

Public mirrors should not all receive unrestricted autonomous write credentials. Genesis AI should publish signed snapshots/releases rather than expose master credentials broadly.

## Future hardening

The project should evaluate threshold signatures, Sigstore/Cosign-style signing, TUF-style update metadata, IPFS CIDs, and multi-node release validation.
