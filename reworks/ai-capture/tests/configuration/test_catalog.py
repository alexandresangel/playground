"""Bundled Capture mappings, catalog formats, and default selection."""

import pytest

from capture.workflow import prompts


@pytest.mark.parametrize(
    "trade_type,prompt,view,menu",
    [
        ("buyDiscountedPaper", "buyDiscountedPaper", "commercialPaper", "commercialPaper"),
        (
            "buyCertificateOfDeposit",
            "buyCertificateOfDeposit",
            "commercialPaper",
            "commercialPaper",
        ),
        ("iamLoan", "mltLoan", "loanDeposit", "loanDeposit"),
        ("mltLoan", "mltLoan", "loanDeposit", "loanDeposit"),
        ("mltLoanPerpetual", "mltLoanPerpetual", "loanDeposit", "loanDeposit"),
        ("commercialLease", "commercialLeaseClassic", "loanDeposit", "commercialLease"),
        ("discountedDeposit", "discountedDeposit", "loanDeposit", "loanDeposit"),
        ("unknown-type", "mltLoan", "loanDeposit", "loanDeposit"),
    ],
)
def test_bundled_trade_type_selects_prompt_view_and_menu(trade_type, prompt, view, menu):
    assert prompts.get_trade_type_config(trade_type) == {
        "trade_type": trade_type,
        "prompt_path": f"prompts/{prompt}.txt",
        "view_entity": view,
        "menu_name": menu,
    }


def test_trade_types_are_sorted_unique_and_all_have_readable_prompts():
    types = prompts.capture_trade_types()
    assert types == sorted(set(types))
    assert {"iamLoan", "commercialLease", "buyDiscountedPaper"} <= set(types)
    for trade_type in types:
        config = prompts.get_trade_type_config(trade_type)
        assert prompts.get_prompt_text({}, config["prompt_path"]).strip()


@pytest.mark.parametrize(
    "entry", [[" loan ", "", None], {"types": [" loan ", "", None]}], ids=["list", "object"]
)
def test_supported_catalog_formats_apply_defaults(monkeypatch, entry):
    monkeypatch.setattr(
        prompts,
        "_catalog",
        {
            "default_view_entity": "entity",
            "default_menu_name": "menu",
            "prompts": {"prompt.txt": entry},
        },
    )
    assert prompts.capture_trade_types() == ["loan"]
    assert prompts.get_trade_type_config(" loan ") == {
        "trade_type": "loan",
        "prompt_path": "prompt.txt",
        "view_entity": "entity",
        "menu_name": "menu",
    }


def test_catalog_entry_can_override_view_and_menu(monkeypatch):
    monkeypatch.setattr(
        prompts,
        "_catalog",
        {
            "default_view_entity": "default",
            "default_menu_name": "default-menu",
            "prompts": {
                "prompt.txt": {
                    "types": ["loan"],
                    "view_entity": "custom",
                    "menu_name": "custom-menu",
                }
            },
        },
    )
    assert prompts.get_trade_type_config("loan") == {
        "trade_type": "loan",
        "prompt_path": "prompt.txt",
        "view_entity": "custom",
        "menu_name": "custom-menu",
    }


def test_unknown_type_without_default_lists_known_types(monkeypatch):
    monkeypatch.setattr(prompts, "_catalog", {"prompts": {"prompt.txt": ["b", "a"]}})
    with pytest.raises(ValueError, match="Unknown trade_type 'unknown'.*known: a, b"):
        prompts.get_trade_type_config("unknown")
