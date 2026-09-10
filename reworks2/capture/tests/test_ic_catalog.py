#!/usr/bin/env python3

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture.workflow.prompts as capture_prompts  # noqa: E402
from capture.workflow.prompts import get_trade_type_config  # noqa: E402


CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "catalog.json"
)


class IcCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        capture_prompts._catalog.clear()
        capture_prompts._catalog.update(catalog)

    def test_explicit_trade_type(self) -> None:
        cfg = get_trade_type_config("buyDiscountedPaper")
        self.assertEqual(cfg["prompt_blob"], "prompts/buyDiscountedPaper.txt")

    def test_default_fallback_for_mlt_loan(self) -> None:
        cfg = get_trade_type_config("mltLoan")
        self.assertEqual(cfg["prompt_blob"], "prompts/mltLoan.txt")

    def test_perpetual_not_default(self) -> None:
        cfg = get_trade_type_config("mltLoanPerpetual")
        self.assertEqual(cfg["prompt_blob"], "prompts/mltLoanPerpetual.txt")

    def test_iam_loan_view_entity(self) -> None:
        cfg = get_trade_type_config("iamLoan")
        self.assertEqual(cfg["view_entity"], "loanDeposit")
        self.assertEqual(cfg["menu_name"], "loanDeposit")

    def test_commercial_paper_view_entity(self) -> None:
        cfg = get_trade_type_config("buyDiscountedPaper")
        self.assertEqual(cfg["view_entity"], "commercialPaper")


if __name__ == "__main__":
    unittest.main()
