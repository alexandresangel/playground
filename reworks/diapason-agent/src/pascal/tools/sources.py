"""Extract citation sources from MCP tool results (doc ask_docs / search_docs shape)."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pascal.i18n import DEFAULT_LOCALE, normalize_locale

_URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
_DOC_INTERNAL_MARKER = "/doc-internal/"
DEFAULT_DOC_LINK_LABEL = "Documentation"
DOC_SOURCE_TOOL_NAMES = frozenset({"ask_docs", "search_docs"})
MAX_SNIPPET_LEN = 300
MAX_CONTENT_LEN = 800


def is_doc_source_tool(trace_entry: Dict[str, Any]) -> bool:
    """True only for documentation MCP tools (ask_docs / search_docs)."""
    qualified = str(trace_entry.get("tool") or trace_entry.get("name") or "").strip()
    if not qualified:
        return False
    base = qualified.split("__")[-1] if "__" in qualified else qualified
    return base in DOC_SOURCE_TOOL_NAMES


def canonical_source_key(url: str) -> str:
    """Dedupe key: full path (no query/fragment); distinct paths stay distinct."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        norm_path = (parsed.path or "/").rstrip("/") or "/"
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{norm_path}"
    path = (parsed.path or raw.split("?")[0].split("#")[0] or "/").rstrip("/") or "/"
    return path.lower()


def _hit_url(item: Dict[str, Any]) -> str:
    url = item.get("url") or item.get("href") or item.get("link")
    return str(url or "").strip()


def is_doc_internal_url(url: str) -> bool:
    return _DOC_INTERNAL_MARKER in str(url or "").lower()


def url_matches_doc_locale(url: str, locale: str) -> bool:
    """True if doc-internal URL contains /{locale}/ in the path (e.g. /fr_fr/)."""
    loc = normalize_locale(locale)
    path = (urlparse(url).path or "").lower()
    return f"/{loc}/" in path


def filter_hits_by_doc_locale(
    hits: List[Dict[str, Any]], locale: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Keep doc-internal hits for the user locale; drop other locales.
  Non-doc URLs are kept. Falls back to en_us doc hits if none match.
    """
    if not hits:
        return hits
    loc = normalize_locale(locale or DEFAULT_LOCALE)
    doc_hits = [h for h in hits if is_doc_internal_url(_hit_url(h))]
    other_hits = [h for h in hits if not is_doc_internal_url(_hit_url(h))]
    if not doc_hits:
        return hits

    matched = [h for h in doc_hits if url_matches_doc_locale(_hit_url(h), loc)]
    if not matched and loc != DEFAULT_LOCALE:
        matched = [
            h for h in doc_hits if url_matches_doc_locale(_hit_url(h), DEFAULT_LOCALE)
        ]

    return other_hits + matched


def merge_source_lists(
    existing: List[Dict[str, str]],
    new_items: List[Dict[str, str]],
    *,
    locale: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Append sources, one entry per canonical URL (keep first)."""
    combined = filter_hits_by_doc_locale(
        [{**item} for item in existing] + [{**item} for item in new_items],
        locale,
    )
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in combined:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = canonical_source_key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({k: str(v) for k, v in item.items() if v is not None and k})
    return out


def _trim(text: str, limit: int) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _link_label(item: Dict[str, Any]) -> str:
    for key in ("link_text", "title", "name", "label"):
        v = str(item.get(key) or "").strip()
        if v:
            return v
    return DEFAULT_DOC_LINK_LABEL


def _excerpt(item: Dict[str, Any]) -> str:
    snippet = str(item.get("snippet") or "").strip()
    if snippet:
        return _trim(snippet, MAX_SNIPPET_LEN)
    content = str(item.get("content") or "").strip()
    if content:
        return _trim(content, MAX_SNIPPET_LEN)
    return ""


def _source_entry_from_hit(
    item: Dict[str, Any], trace_entry: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    u = _hit_url(item)
    if not u or not _URL_RE.match(u):
        return None
    entry: Dict[str, str] = {
        "url": u,
        "title": _link_label(item),
        "tool": str(trace_entry.get("tool") or trace_entry.get("name") or ""),
        "mcp_server": str(trace_entry.get("mcp_server") or ""),
    }
    link_text = str(item.get("link_text") or "").strip()
    if link_text and link_text != entry["title"]:
        entry["link_text"] = link_text
    excerpt = _excerpt(item)
    if excerpt:
        entry["snippet"] = excerpt
    raw_content = str(item.get("content") or "").strip()
    if raw_content:
        entry["content"] = _trim(raw_content, MAX_CONTENT_LEN)
    return entry


def _try_parse_json_blob(text: str) -> Any:
    raw = text.strip()
    if not raw or raw[0] not in "{[":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _sources_list_from_node(node: Any) -> List[Dict[str, Any]]:
    if not isinstance(node, dict):
        return []
    for key in ("sources", "results", "hits"):
        batch = node.get(key)
        if isinstance(batch, list):
            return [s for s in batch if isinstance(s, dict)]
    return []


def _collect_explicit_source_hits(tool_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []

    def add_batch(batch: List[Dict[str, Any]]) -> None:
        hits.extend(batch)

    add_batch(_sources_list_from_node(tool_result))

    content = tool_result.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                parsed = _try_parse_json_blob(text)
                if isinstance(parsed, dict):
                    add_batch(_sources_list_from_node(parsed))
                elif isinstance(parsed, list):
                    for el in parsed:
                        if isinstance(el, dict):
                            add_batch(_sources_list_from_node(el))
                            if el.get("url") or el.get("href"):
                                add_batch([el])

    structured = tool_result.get("structuredContent")
    if isinstance(structured, dict):
        add_batch(_sources_list_from_node(structured))

    return hits


def _walk_fallback(
    node: Any,
    trace_entry: Dict[str, Any],
    out: List[Dict[str, str]],
    seen: set[str],
) -> None:
    def add(url: str, title: str = "") -> None:
        u = str(url or "").strip()
        if not u or not _URL_RE.match(u):
            return
        key = canonical_source_key(u)
        if not key or key in seen:
            return
        seen.add(key)
        item: Dict[str, Any] = {"url": u}
        if title.strip():
            item["title"] = title.strip()
        entry = _source_entry_from_hit(item, trace_entry)
        if entry:
            out.append(entry)

    if isinstance(node, dict):
        possible_url = node.get("url") or node.get("href") or node.get("link")
        if isinstance(possible_url, str):
            add(possible_url, _link_label(node))
        for v in node.values():
            _walk_fallback(v, trace_entry, out, seen)
    elif isinstance(node, list):
        for v in node:
            _walk_fallback(v, trace_entry, out, seen)
    elif isinstance(node, str):
        for m in _URL_RE.findall(node):
            add(m)


def extract_sources_from_tool_result(
    tool_result: Dict[str, Any],
    trace_entry: Dict[str, Any],
    *,
    locale: Optional[str] = None,
) -> List[Dict[str, str]]:
    if not is_doc_source_tool(trace_entry):
        return []
    raw_hits = _collect_explicit_source_hits(tool_result)
    if raw_hits:
        filtered = filter_hits_by_doc_locale(raw_hits, locale)
        out: List[Dict[str, str]] = []
        seen: set[str] = set()
        for item in filtered:
            entry = _source_entry_from_hit(item, trace_entry)
            if not entry:
                continue
            key = canonical_source_key(entry["url"])
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(entry)
        return out

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    _walk_fallback(tool_result, trace_entry, out, seen)
    if locale and out:
        as_hits = [{"url": s["url"], **s} for s in out]
        filtered = filter_hits_by_doc_locale(as_hits, locale)
        allowed = {canonical_source_key(_hit_url(h)) for h in filtered}
        out = [s for s in out if canonical_source_key(s["url"]) in allowed]
    return out


def dedupe_source_list(
    sources: List[Dict[str, str]], *, locale: Optional[str] = None
) -> List[Dict[str, str]]:
    return merge_source_lists([], sources, locale=locale)
