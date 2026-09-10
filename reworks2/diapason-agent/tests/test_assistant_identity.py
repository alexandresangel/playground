#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from settings import assistant_identity, assistant_identity_llm_block


def test_identity_block_empty() -> None:
    cfg = {"ui": {"assistant_name": "Pascal"}}
    assert assistant_identity(cfg) == ""
    assert assistant_identity_llm_block(cfg) == ""


def test_identity_block_present() -> None:
    cfg = {
        "ui": {
            "assistant_identity": "You are Pascal, named after Pascal Kravitzch.",
        }
    }
    block = assistant_identity_llm_block(cfg)
    assert "Assistant identity" in block
    assert "Pascal Kravitzch" in block
