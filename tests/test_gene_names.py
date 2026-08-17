from __future__ import annotations

import pytest

from genesis.gene_names import (
    CORE_DISPLAY_NAME,
    COMMON_NAME,
    RESERVED_DISPLAY_NAME,
    identity_for_logical_id,
    logical_id_for_display_name,
    public_naming_scheme,
)


def test_main_gene_is_gene_0() -> None:
    identity = identity_for_logical_id("gene-node-1")
    assert identity.common_name == COMMON_NAME == "Gene"
    assert identity.display_name == CORE_DISPLAY_NAME == "Gene 0"
    assert identity.serial == 0


def test_numbered_genes_use_three_digits_from_002() -> None:
    assert identity_for_logical_id("gene-node-2").display_name == "Gene 002"
    assert identity_for_logical_id("gene-node-3").display_name == "Gene 003"
    assert identity_for_logical_id("gene-node-25").display_name == "Gene 025"


def test_gene_001_is_reserved() -> None:
    assert RESERVED_DISPLAY_NAME == "Gene 001"
    assert logical_id_for_display_name("Gene 001") is None
    with pytest.raises(ValueError):
        identity_for_logical_id("gene-node-1") if False else identity_for_logical_id("gene-node-01")


def test_specific_and_common_names_resolve_without_stealing_001() -> None:
    assert logical_id_for_display_name("Gene") is None
    assert logical_id_for_display_name("Gene 0") == "gene-node-1"
    assert logical_id_for_display_name("Gene 002") == "gene-node-2"
    scheme = public_naming_scheme()
    assert scheme["reserved"]["status"] == "reserved_for_owner_definition"
