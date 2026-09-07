from pathlib import Path

from capture.catalog import PromptCatalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bundled_catalog_preserves_trade_type_mapping() -> None:
    catalog = PromptCatalog(
        {"capture": {"catalog_backend": "filesystem"}},
        PROJECT_ROOT,
    )
    initialized = catalog.initialize()
    assert initialized["version"] == "1"
    iam = catalog.trade_type_config("iamLoan")
    assert iam["prompt_blob"] == "prompts/mltLoan.txt"
    assert iam["view_entity"] == "loanDeposit"
    assert "Only generate the xml" in catalog.prompt_text(iam["prompt_blob"])


def test_unknown_type_uses_legacy_default_prompt() -> None:
    catalog = PromptCatalog(
        {"capture": {"catalog_backend": "filesystem"}},
        PROJECT_ROOT,
    )
    catalog.initialize()
    result = catalog.trade_type_config("newFutureType")
    assert result["prompt_blob"] == "prompts/mltLoan.txt"
