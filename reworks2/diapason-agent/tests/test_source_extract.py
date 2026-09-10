#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from source_extract import (
    DEFAULT_DOC_LINK_LABEL,
    canonical_source_key,
    extract_sources_from_tool_result,
    filter_hits_by_doc_locale,
    is_doc_source_tool,
    merge_source_lists,
)

_TRACE = {"tool": "ask_docs", "mcp_server": "docs"}
_TRACE_BALANCE = {"tool": "Balance", "mcp_server": "default"}
_BASE = "https://doc.diapason-treasury.com/doc-internal/7.3.0/mydiapason"


def test_is_doc_source_tool() -> None:
    assert is_doc_source_tool({"tool": "ask_docs"})
    assert is_doc_source_tool({"tool": "docs__search_docs"})
    assert not is_doc_source_tool({"tool": "Balance"})
    assert not is_doc_source_tool({"tool": "getValueStatement"})


def test_non_doc_tool_does_not_emit_sources() -> None:
    result = {
        "sources": [{"url": "https://host/doc-internal/page1", "title": "Doc"}],
        "content": [
            {
                "type": "text",
                "text": "See https://host/doc-internal/page2 for details.",
            }
        ],
    }
    out = extract_sources_from_tool_result(result, _TRACE_BALANCE)
    assert out == []


def test_ask_docs_sources_array() -> None:
    result = {
        "sources": [
            {
                "title": "Cash positioning",
                "link_text": "Cash positioning",
                "url": "https://host/doc-internal/page1",
                "content": "x" * 500,
                "snippet": "Short preview text.",
            }
        ]
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1
    assert out[0]["url"] == "https://host/doc-internal/page1"
    assert out[0]["title"] == "Cash positioning"
    assert out[0]["snippet"] == "Short preview text."


def test_search_docs_no_link_text() -> None:
    result = {
        "sources": [
            {
                "title": "Bank statements",
                "url": "https://host/doc-internal/page2",
                "snippet": "Hit snippet.",
                "score": 0.9,
            }
        ]
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1
    assert out[0]["title"] == "Bank statements"


def test_missing_title_uses_documentation_label() -> None:
    result = {
        "sources": [{"url": "https://host/doc-internal/unknown"}],
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1
    assert out[0]["title"] == DEFAULT_DOC_LINK_LABEL


def test_sources_inside_mcp_content_json() -> None:
    import json

    payload = {
        "sources": [
            {
                "title": "From JSON blob",
                "url": "https://host/doc-internal/blob",
                "snippet": "blob snippet",
            }
        ]
    }
    result = {
        "content": [{"type": "text", "text": json.dumps(payload)}],
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1
    assert out[0]["title"] == "From JSON blob"


def test_dedupe_by_url() -> None:
    url = "https://host/doc-internal/dup"
    result = {
        "sources": [
            {"title": "A", "url": url},
            {"title": "B", "url": url},
        ]
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1


def test_dedupe_same_page_query_and_fragment() -> None:
    base = "https://host/doc-internal/entity"
    result = {
        "sources": [
            {"title": "T", "url": f"{base}?chunk=0", "snippet": "a"},
            {"title": "T", "url": f"{base}?chunk=1", "snippet": "b"},
            {"title": "T", "url": f"{base}#section", "snippet": "c"},
            {"title": "T", "url": f"{base}/", "snippet": "d"},
        ]
    }
    out = extract_sources_from_tool_result(result, _TRACE)
    assert len(out) == 1
    assert canonical_source_key(f"{base}?x") == canonical_source_key(f"{base}#y")


def test_merge_source_lists_across_batches() -> None:
    a = [{"url": "https://h/doc", "title": "Doc"}]
    b = [{"url": "https://h/doc?i=2", "title": "Doc"}]
    merged = merge_source_lists(a, b)
    assert len(merged) == 1


def test_locale_filter_keeps_fr_and_distinct_paths() -> None:
    urls = [
        f"{_BASE}/en_us/confluence/topics/157319200.html",
        f"{_BASE}/fr_fr/confluence/topics/157319200.html",
        f"{_BASE}/en_us/mydiapason/confluence/topics/157319200.html",
        f"{_BASE}/fr_fr/confluence/topics/157319200_2.html",
        f"{_BASE}/fr_fr/mydiapason/confluence/topics/157319200.html",
    ]
    result = {"sources": [{"title": "T", "url": u, "snippet": "x"} for u in urls]}
    out = extract_sources_from_tool_result(result, _TRACE, locale="fr_fr")
    out_urls = {s["url"] for s in out}
    assert out_urls == {
        f"{_BASE}/fr_fr/confluence/topics/157319200.html",
        f"{_BASE}/fr_fr/confluence/topics/157319200_2.html",
    }
    assert len(out) == 2


def test_locale_filter_en_us() -> None:
    urls = [
        f"{_BASE}/en_us/confluence/topics/157319200.html",
        f"{_BASE}/fr_fr/confluence/topics/157319200.html",
    ]
    hits = [{"url": u} for u in urls]
    filtered = filter_hits_by_doc_locale(hits, "en_us")
    assert len(filtered) == 1
    assert "/en_us/" in filtered[0]["url"]
