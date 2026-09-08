from __future__ import annotations

from .coding import CodingModule


INSTALL_MARKER = "_genesis_coding_valid_paths_installed"
ACTIVE_PATHS_ATTR = "_genesis_active_coding_valid_paths"
_MISSING = object()


def _normalize_path(value: object) -> str:
    return str(value).replace("\\", "/").lstrip("./")


def _declared_proposal_paths(module: CodingModule, proposal: dict) -> tuple[str, ...]:
    """Read provider-declared paths without applying or materializing any edit."""
    normalized = module._normalize_proposal_shape(proposal)
    raw_files = normalized.get("files")
    if isinstance(raw_files, dict):
        return tuple(_normalize_path(path) for path in raw_files)

    edits = normalized.get("edits")
    if not isinstance(edits, list):
        return ()

    paths: list[str] = []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        value = edit.get("path")
        if isinstance(value, str):
            paths.append(_normalize_path(value))
    return tuple(paths)


def install_coding_valid_paths() -> None:
    """Enforce the exact NUMBERED_CONTEXT path set before provider edits are applied.

    CodingModule already tells bounded providers to choose a path from VALID_PATHS,
    but the historical validator first materialized compact edits using the broader
    self-development sandbox. A model could therefore spend all bounded retries on
    a safe-but-unrelated file that was never supplied as context. This guard makes
    VALID_PATHS an execution boundary while preserving every existing path,
    syntax, test, security, review, and promotion check as defense in depth.
    """
    if getattr(CodingModule, INSTALL_MARKER, False):
        return

    original_propose = CodingModule.propose
    original_validate = CodingModule.validate_proposal

    def propose_with_active_valid_paths(
        self: CodingModule,
        objective: str,
        context_paths: list[str] | None = None,
        *,
        provider=None,
    ):
        # Keep a reference to the caller-owned list. The installed coding provider
        # policy may safely re-ground that same list before the original proposal
        # loop runs; validation will therefore see the final bounded context set.
        active_paths = context_paths if context_paths is not None else []
        previous = getattr(self, ACTIVE_PATHS_ATTR, _MISSING)
        setattr(self, ACTIVE_PATHS_ATTR, active_paths)
        try:
            return original_propose(self, objective, context_paths, provider=provider)
        finally:
            if previous is _MISSING:
                self.__dict__.pop(ACTIVE_PATHS_ATTR, None)
            else:
                setattr(self, ACTIVE_PATHS_ATTR, previous)

    def validate_with_active_valid_paths(
        self: CodingModule,
        proposal: dict,
        provider_name: str,
    ):
        active = getattr(self, ACTIVE_PATHS_ATTR, _MISSING)
        if active is not _MISSING and isinstance(proposal, dict):
            allowed = {_normalize_path(path) for path in active}
            declared = _declared_proposal_paths(self, proposal)
            invalid = tuple(path for path in declared if path not in allowed)
            if invalid:
                raise ValueError(
                    "coding proposal path must match VALID_PATHS exactly: "
                    + ", ".join(invalid)
                )
        return original_validate(self, proposal, provider_name)

    CodingModule.propose = propose_with_active_valid_paths
    CodingModule.validate_proposal = validate_with_active_valid_paths
    setattr(CodingModule, INSTALL_MARKER, True)
