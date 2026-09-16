#!/usr/bin/env python3

import json
import unittest
from pathlib import Path


from capture.workflow import prompts as capture_prompt_loader  # noqa: E402
from capture.workflow.prompts import get_trade_type_config  # noqa: E402
from capture.workflow.prompts import capture_config, capture_enabled


CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "catalog.json"
)


def test_capture_settings_take_precedence_over_legacy_settings():
    config = {"capture": {"enabled": False, "temperature": 0.2},
              "intelligence_contract": {"enabled": True, "temperature": 0.9}}
    assert capture_config(config) == config["capture"]
    assert capture_enabled(config) is False


def test_existing_deployment_settings_still_work():
    config = {"intelligence_contract": {"enabled": True, "temperature": 0.5}}
    assert capture_config(config) == config["intelligence_contract"]
    assert capture_enabled(config) is True


def test_empty_capture_settings_do_not_enable_legacy_config():
    assert capture_config({"capture": {}, "intelligence_contract": {"enabled": True}}) == {}
    assert capture_enabled({"capture": {}, "intelligence_contract": {"enabled": True}}) is False


class CaptureCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        capture_prompt_loader._catalog.clear()
        capture_prompt_loader._catalog.update(catalog)

    def test_explicit_trade_type(self) -> None:
        cfg = get_trade_type_config("buyDiscountedPaper")
        self.assertEqual(cfg["prompt_path"], "prompts/buyDiscountedPaper.txt")

    def test_default_fallback_for_mlt_loan(self) -> None:
        cfg = get_trade_type_config("mltLoan")
        self.assertEqual(cfg["prompt_path"], "prompts/mltLoan.txt")

    def test_perpetual_not_default(self) -> None:
        cfg = get_trade_type_config("mltLoanPerpetual")
        self.assertEqual(cfg["prompt_path"], "prompts/mltLoanPerpetual.txt")

    def test_iam_loan_view_entity(self) -> None:
        cfg = get_trade_type_config("iamLoan")
        self.assertEqual(cfg["view_entity"], "loanDeposit")
        self.assertEqual(cfg["menu_name"], "loanDeposit")

    def test_commercial_paper_view_entity(self) -> None:
        cfg = get_trade_type_config("buyDiscountedPaper")
        self.assertEqual(cfg["view_entity"], "commercialPaper")


if __name__ == "__main__":
    unittest.main()