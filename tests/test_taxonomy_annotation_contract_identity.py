from __future__ import annotations

from yandex_analytics_reaper.taxonomy import (
    ANNOTATION_CONTRACT_V1_CONTENT_HASH,
    taxonomy_annotation_contract_content_hash,
)


def test_manual_annotation_contract_v1_complete_content_identity_is_frozen() -> None:
    assert ANNOTATION_CONTRACT_V1_CONTENT_HASH == (
        "9815b185ef709cb9275985474970165f16eef8f78ea74e73c1397b38fa646c17"
    )
    assert taxonomy_annotation_contract_content_hash() == ANNOTATION_CONTRACT_V1_CONTENT_HASH
