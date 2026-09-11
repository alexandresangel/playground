#!/usr/bin/env python3
"""Regenerate grafana-agent-mcp-{dev,test,prod}.json (same panels, env baked in)."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ENVS = {
    "dev": "diapasondevstor",
    "test": "diapasonteststor",
    "prod": "diapasonprodstor",
}

# Parse chat done lines (logfmt-ish). Works for both old and new formats.
CHAT_PARSE = (
    r"| regexp `"
    r"customer=(?P<customer>\S+) "
    r"user=(?P<user>\S+) "
    r"session=(?P<session>\S+) "
    r"tokens_in=(?P<tokens_in>\S*) "
    r"tokens_out=(?P<tokens_out>\S*) "
    r"cost_usd=(?P<cost_usd>\S*) "
    r"tools=(?P<tools>\S*) "
    r"skills=(?P<skills>\S*)"
    r"`"
)


def build(env: str, blob: str) -> dict:
    agent = f"diapason-agent-{env}"
    mcp = f"diapason-mcp-{env}"
    chats_base = (
        f'{{service_name="{agent}"}} |= `chat done` '
        f'|~ `customer=${{customer_id}}` |~ `user=${{user_id}}`'
    )
    chats_parsed = f"{chats_base} {CHAT_PARSE}"
    # Put tools first so each request is readable in a logs panel (works on current Loki data).
    chats_display = (
        f"{chats_parsed} "
        f'| line_format '
        f'`tools={{{{.tools}}}} skills={{{{.skills}}}} '
        f'customer={{{{.customer}}}} user={{{{.user}}}} '
        f'tokens_in={{{{.tokens_in}}}} tokens_out={{{{.tokens_out}}}} '
        f'cost_usd={{{{.cost_usd}}}} session={{{{.session}}}}`'
    )
    # Only lines with a numeric cost (skip empty cost_usd= from older builds).
    cost_q = (
        f"sum by (customer) (sum_over_time("
        f"{chats_base} "
        f"| regexp `customer=(?P<customer>\\S+).*cost_usd=(?P<cost>[0-9]+\\.[0-9]+|[1-9][0-9]*)` "
        f"| unwrap cost [$__interval]))"
    )
    tools_from_chats = (
        f"sum by (tools) (count_over_time("
        f"{chats_parsed} | tools != `` | tools != `\"\"` [$__range]))"
    )
    mcp_ok = (
        f'sum by (tool) (count_over_time({{service_name="{mcp}"}} '
        f'|= `tool ` |= ` ok ` | regexp `tool (?P<tool>\\S+) ok` [$__range]))'
    )
    mcp_fail = (
        f'sum(count_over_time({{service_name="{mcp}"}} '
        f'|= `tool ` |= `failed` [$__range])) or vector(0)'
    )
    # Keep TraceQL simple: =~ on int attrs returns nothing; customer/user filter via Loki.
    tempo_traceql = f'{{resource.service.name="{agent}" && name="chat.completion"}}'

    def loki(expr: str, ref: str = "A", legend: str = "", *, instant: bool = False) -> dict:
        t: dict = {
            "datasource": {"type": "loki", "uid": "loki"},
            "editorMode": "code",
            "expr": expr,
            "queryType": "instant" if instant else "range",
            "refId": ref,
        }
        if legend:
            t["legendFormat"] = legend
        return t

    panels: list[dict] = [
        {
            "id": 1,
            "type": "text",
            "title": "How to use",
            "gridPos": {"h": 3, "w": 24, "x": 0, "y": 0},
            "options": {
                "mode": "markdown",
                "content": (
                    f"**{env}** — `{agent}` / `{mcp}` / blob `{blob}`.\n\n"
                    "Chats table columns come from Loki `chat done` lines (tools per request). "
                    "Tempo panel lists `chat.completion` spans — open a TraceID to see agent↔MCP. "
                    f"Transcript: `https://{blob}.blob.core.windows.net/chat-sessions/{{scope}}/{{id}}.json`."
                ),
            },
        },
        {
            "id": 2,
            "type": "logs",
            "title": "Chats (tools first — then tokens / cost)",
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 3},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [
                {
                    **loki(chats_display),
                    "direction": "backward",
                    "maxLines": 100,
                }
            ],
            "options": {
                "showTime": True,
                "wrapLogMessage": True,
                "enableLogDetails": True,
                "showCommonLabels": False,
                "prettifyLogMessage": False,
            },
        },
        {
            "id": 3,
            "type": "timeseries",
            "title": "Chat volume",
            "gridPos": {"h": 8, "w": 8, "x": 0, "y": 15},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [
                loki(
                    f"sum(count_over_time({chats_base} [$__interval]))",
                    legend="chats",
                )
            ],
        },
        {
            "id": 4,
            "type": "timeseries",
            "title": "Estimated cost USD",
            "gridPos": {"h": 8, "w": 8, "x": 8, "y": 15},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [loki(cost_q, legend="{{customer}}")],
            "fieldConfig": {
                "defaults": {"unit": "currencyUSD", "custom": {"fillOpacity": 20}},
                "overrides": [],
            },
        },
        {
            "id": 5,
            "type": "bargauge",
            "title": "Tools used on chats (from chat done)",
            "gridPos": {"h": 8, "w": 8, "x": 16, "y": 15},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [loki(tools_from_chats, instant=True)],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                "displayMode": "gradient",
                "orientation": "horizontal",
            },
            "fieldConfig": {
                "defaults": {"min": 0, "color": {"mode": "palette-classic"}},
                "overrides": [],
            },
        },
        {
            "id": 6,
            "type": "bargauge",
            "title": "MCP tool spans (ok)",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 23},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [loki(mcp_ok, instant=True)],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"]},
                "displayMode": "gradient",
                "orientation": "horizontal",
            },
        },
        {
            "id": 7,
            "type": "stat",
            "title": "MCP tool failures",
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 23},
            "datasource": {"type": "loki", "uid": "loki"},
            "targets": [loki(mcp_fail, instant=True)],
            "options": {
                "reduceOptions": {"calcs": ["lastNotNull"]},
                "colorMode": "value",
                "graphMode": "none",
            },
            "fieldConfig": {
                "defaults": {
                    "mappings": [
                        {
                            "type": "special",
                            "options": {
                                "match": "null",
                                "result": {"text": "0", "index": 0},
                            },
                        }
                    ],
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"color": "green", "value": None},
                            {"color": "red", "value": 1},
                        ],
                    },
                },
                "overrides": [],
            },
        },
        {
            "id": 8,
            "type": "traces",
            "title": "chat.completion traces (open TraceID → MCP children)",
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 31},
            "datasource": {"type": "tempo", "uid": "tempo"},
            "targets": [
                {
                    "datasource": {"type": "tempo", "uid": "tempo"},
                    "queryType": "traceql",
                    "refId": "A",
                    "limit": 50,
                    "tableType": "traces",
                    "filters": [],
                    "query": tempo_traceql,
                }
            ],
        },
        {
            "id": 9,
            "type": "text",
            "title": "Service graph note",
            "gridPos": {"h": 3, "w": 24, "x": 0, "y": 43},
            "options": {
                "mode": "markdown",
                "content": (
                    "Tempo **service graph** needs the Tempo metrics-generator (often off in PoC). "
                    f"Use a TraceID from the panel above to see `{agent}` → `{mcp}` spans in one trace. "
                    "After redeploy, identity attrs are strings so TraceQL filters can use "
                    "`span.diapason.customer_id=~\"…\"` if needed."
                ),
            },
        },
    ]
    return {
        "annotations": {"list": []},
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 1,
        "id": None,
        "links": [],
        "panels": panels,
        "schemaVersion": 39,
        "tags": ["diapason", "agent", "mcp", env],
        "templating": {
            "list": [
                {
                    "name": "customer_id",
                    "type": "textbox",
                    "label": "customer_id",
                    "current": {"text": ".*", "value": ".*"},
                    "options": [{"text": ".*", "value": ".*", "selected": True}],
                    "query": ".*",
                },
                {
                    "name": "user_id",
                    "type": "textbox",
                    "label": "user_id",
                    "current": {"text": ".*", "value": ".*"},
                    "options": [{"text": ".*", "value": ".*", "selected": True}],
                    "query": ".*",
                },
            ]
        },
        "time": {"from": "now-6h", "to": "now"},
        "timezone": "browser",
        "title": f"Diapason Agent+MCP — {env}",
        "uid": f"diapason-agent-mcp-{env}",
        "version": 2,
    }


def main() -> None:
    for env, blob in ENVS.items():
        path = OUT / f"grafana-agent-mcp-{env}.json"
        path.write_text(json.dumps(build(env, blob), indent=2) + "\n", encoding="utf-8")
        print(path.name)


if __name__ == "__main__":
    main()
