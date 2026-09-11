"""Existing chart response helpers for Pascal."""

from __future__ import annotations
from typing import Any, Dict


def _sample_chart_spec() -> Dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Sample liquidity trend chart.",
        "data": {
            "values": [
                {"date": "2026-04-01", "value": 110},
                {"date": "2026-04-02", "value": 114},
                {"date": "2026-04-03", "value": 109},
                {"date": "2026-04-04", "value": 121},
                {"date": "2026-04-05", "value": 128},
            ]
        },
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "date", "type": "temporal", "title": "Date"},
            "y": {"field": "value", "type": "quantitative", "title": "Liquidity"},
            "tooltip": [
                {"field": "date", "type": "temporal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }


def _looks_like_chart_request(message: str) -> bool:
    text = message.lower()
    return any(
        token in text
        for token in ("chart", "plot", "trend", "graph", "visual", "visualization")
    )