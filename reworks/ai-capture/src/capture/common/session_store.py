"""Chat sessions in Azure Blob (DefaultAzureCredential, then AzureCliCredential fallback)."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# --- helpers ---


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_key(scope: str, session_id: str) -> str:
    return f"{scope}/{session_id}.json"


def _deleted_session_key(scope: str, session_id: str) -> str:
    return f"{scope}/deleted/{session_id}.json"


def _new_record(scope: str, title: str = "", session_id: Optional[str] = None) -> Dict[str, Any]:
    parts = scope.split("/")
    sid = session_id or str(uuid.uuid4())
    t = _now()
    return {
        "session_id": sid,
        "scope": scope,
        "instance": parts[0] if len(parts) > 0 else "",
        "customer_id": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else parts[1] if len(parts) > 1 else "",
        "user_id": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else parts[2] if len(parts) > 2 else "",
        "title": title,
        "created_at": t,
        "updated_at": t,
        "turns": [],
    }


def _record_matches_scope(record: Dict[str, Any], scope: str, session_id: str) -> bool:
    return record.get("session_id") == session_id and record.get("scope") == scope


def _normalize_tool_trace(tool_trace: Optional[List[Any]]) -> List[Dict[str, Any]]:
    if not tool_trace:
        return []
    out: List[Dict[str, Any]] = []
    for item in tool_trace:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        args = item.get("arguments")
        if not isinstance(args, dict):
            args = {}
        entry: Dict[str, Any] = {
            "name": name.strip(),
            "tool": str(item.get("tool", name)).strip() or name.strip(),
            "arguments": args,
        }
        mcp_server = item.get("mcp_server")
        if isinstance(mcp_server, str) and mcp_server.strip():
            entry["mcp_server"] = mcp_server.strip()
        mcp_label = item.get("mcp_label")
        if isinstance(mcp_label, str) and mcp_label.strip():
            entry["mcp_label"] = mcp_label.strip()
        duration_ms = item.get("duration_ms")
        if isinstance(duration_ms, (int, float)):
            entry["duration_ms"] = int(duration_ms)
        out.append(entry)
    return out


def _normalize_sources(sources: Optional[List[Any]]) -> List[Dict[str, str]]:
    if not sources:
        return []
    from source_extract import canonical_source_key

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "") or "").strip()
        if not url:
            continue
        key = canonical_source_key(url)
        if not key or key in seen:
            continue
        seen.add(key)
        entry: Dict[str, str] = {"url": url}
        title = str(item.get("title", "") or "").strip()
        if title:
            entry["title"] = title
        link_text = str(item.get("link_text", "") or "").strip()
        if link_text:
            entry["link_text"] = link_text
        snippet = str(item.get("snippet", "") or "").strip()
        if snippet:
            entry["snippet"] = snippet
        content = str(item.get("content", "") or "").strip()
        if content:
            entry["content"] = content
        tool = str(item.get("tool", "") or "").strip()
        if tool:
            entry["tool"] = tool
        mcp_server = str(item.get("mcp_server", "") or "").strip()
        if mcp_server:
            entry["mcp_server"] = mcp_server
        out.append(entry)
    return out


def _normalize_skill_run(skill_run: Optional[Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(skill_run, dict):
        return None
    skill = skill_run.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        return None
    out: Dict[str, Any] = {"skill": skill.strip()}
    for key in ("trade_type", "view_entity", "menu_name", "pdf_filename"):
        val = skill_run.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    if isinstance(skill_run.get("success"), bool):
        out["success"] = skill_run["success"]
    warnings = skill_run.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(w) for w in warnings if w]
    artifacts = skill_run.get("artifacts")
    if isinstance(artifacts, dict) and artifacts:
        out["artifacts"] = artifacts
    timings = skill_run.get("timings_ms")
    if isinstance(timings, dict) and timings:
        out["timings_ms"] = timings
    return out


def _normalize_usage(usage: Optional[Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(usage, dict):
        return None
    out: Dict[str, Any] = {}
    for key in ("input", "output", "total"):
        val = usage.get(key)
        if isinstance(val, (int, float)):
            out[key] = int(val)
    cost = usage.get("cost_usd")
    if isinstance(cost, (int, float)):
        out["cost_usd"] = float(cost)
    return out or None


def turns_for_client(turns: Any) -> List[Dict[str, Any]]:
    if not isinstance(turns, list):
        return []
    out: List[Dict[str, Any]] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        cleaned = dict(turn)
        cleaned.pop("skill_run", None)
        out.append(cleaned)
    return out


def _add_turns(
    record: Dict[str, Any],
    user: str,
    assistant: str,
    max_turns: int,
    tool_trace: Optional[List[Any]] = None,
    sources: Optional[List[Any]] = None,
    skill_run: Optional[Any] = None,
    usage: Optional[Any] = None,
) -> None:
    turns = record.setdefault("turns", [])
    if not isinstance(turns, list):
        turns = []
        record["turns"] = turns
    turns.append({"role": "user", "content": user, "at": _now()})
    assistant_turn: Dict[str, Any] = {"role": "assistant", "content": assistant, "at": _now()}
    normalized_trace = _normalize_tool_trace(tool_trace)
    if normalized_trace:
        assistant_turn["tool_trace"] = normalized_trace
    normalized_sources = _normalize_sources(sources)
    if normalized_sources:
        assistant_turn["sources"] = normalized_sources
    normalized_skill_run = _normalize_skill_run(skill_run)
    if normalized_skill_run:
        assistant_turn["skill_run"] = normalized_skill_run
    normalized_usage = _normalize_usage(usage)
    if normalized_usage:
        assistant_turn["usage"] = normalized_usage
    turns.append(assistant_turn)
    cap = max_turns * 2
    if len(turns) > cap:
        record["turns"] = turns[-cap:]
    record["updated_at"] = _now()
    if not record.get("title") and user.strip():
        record["title"] = user.strip()[:80]


def _llm_turns(turns: Any, max_turns: int) -> List[Dict[str, str]]:
    if not isinstance(turns, list):
        return []
    out: List[Dict[str, str]] = []
    for t in turns:
        if isinstance(t, dict) and t.get("role") in ("user", "assistant") and isinstance(t.get("content"), str):
            out.append({"role": t["role"], "content": t["content"]})
    return out[-max_turns * 2 :]


def _has_assistant_response(turns: Any) -> bool:
    if not isinstance(turns, list):
        return False
    return any(
        isinstance(t, dict) and t.get("role") == "assistant" and isinstance(t.get("content"), str)
        for t in turns
    )


def _summary(record: Dict[str, Any]) -> Dict[str, Any]:
    turns = record.get("turns", [])
    return {
        "session_id": record.get("session_id", ""),
        "title": record.get("title", ""),
        "created_at": record.get("created_at", ""),
        "updated_at": record.get("updated_at", ""),
        "has_response": _has_assistant_response(turns),
    }


def _encode(record: Dict[str, Any]) -> bytes:
    return json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")


def _decode(raw: bytes) -> Dict[str, Any]:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid session json")
    if not isinstance(data.get("turns"), list):
        data["turns"] = []
    return data


from blob_client import connect_blob

class BlobSessionStore:
    backend = "blob"

    def __init__(self, account_name: str, container: str, max_turns: int = 30) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError, ResourceModifiedError, ResourceNotFoundError
        if not account_name.strip():
            raise ValueError("storage.account_name is required in config.json")

        self._account_name = account_name.strip()
        self._container_name = container
        self._max_turns = max(1, max_turns)
        self._lock = threading.Lock()
        self._MatchConditions = MatchConditions
        self._HttpResponseError = HttpResponseError
        self._ResourceModifiedError = ResourceModifiedError
        self._ResourceNotFoundError = ResourceNotFoundError

        _client, self._container, self._credential_source = connect_blob(
            self._account_name, self._container_name
        )
        try:
            self._container.create_container()
        except Exception:
            pass

    def _blob(self, key: str):
        return self._container.get_blob_client(key)

    def _reraise_blob_error(self, exc: Exception, operation: str) -> None:
        if isinstance(exc, self._HttpResponseError):
            raise RuntimeError(
                f"Azure Blob {operation} failed on {self._account_name}/{self._container_name}: "
                f"{exc}. "
                "Grant Storage Blob Data Contributor on this container; local dev: `az login` "
                "(see agent/README.md)."
            ) from exc
        raise exc

    def _load(self, key: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            d = self._blob(key).download_blob()
            return _decode(d.readall()), (d.properties.etag if d.properties else None)
        except self._ResourceNotFoundError:
            return None, None

    def _save(self, key: str, record: Dict[str, Any], etag: Optional[str] = None) -> None:
        kw: Dict[str, Any] = {"overwrite": True}
        if etag:
            kw["etag"] = etag
            kw["match_condition"] = self._MatchConditions.IfNotModified
        self._blob(key).upload_blob(_encode(record), **kw)

    def _update(self, key: str, fn, *, create: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        for i in range(5):
            record, etag = self._load(key)
            if record is None:
                if create is None:
                    raise KeyError(key)
                self._blob(key).upload_blob(_encode(create), overwrite=False)
                return create
            updated = fn(record)
            try:
                self._save(key, updated, etag=etag)
                return updated
            except self._ResourceModifiedError:
                time.sleep(0.05 * (i + 1))
        raise RuntimeError(f"blob conflict: {key}")

    def create_session(self, scope: str, title: str = "") -> Dict[str, Any]:
        record = _new_record(scope, title)
        key = _session_key(scope, str(record["session_id"]))
        try:
            with self._lock:
                self._blob(key).upload_blob(_encode(record), overwrite=False)
        except Exception as exc:
            self._reraise_blob_error(exc, "write")
        return record

    def get_session(self, session_id: str, scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if scope is None:
            return None
        data, _ = self._load(_session_key(scope, session_id))
        if not data or not _record_matches_scope(data, scope, session_id):
            return None
        return data

    def list_sessions(self, scope: str) -> List[Dict[str, Any]]:
        prefix = f"{scope}/"
        archived_prefix = f"{scope}/deleted/"
        out: List[Dict[str, Any]] = []
        try:
            for item in self._container.list_blobs(name_starts_with=prefix):
                if not item.name.endswith(".json"):
                    continue
                if item.name.startswith(archived_prefix):
                    continue
                data, _ = self._load(item.name)
                if data:
                    out.append(_summary(data))
        except Exception as exc:
            self._reraise_blob_error(exc, "list")
        out.sort(key=lambda e: str(e.get("updated_at", "")), reverse=True)
        return out

    def resolve_session_id(self, scope: str, session_id: Optional[str]) -> str:
        if session_id:
            if self.get_session(session_id, scope) is None:
                raise KeyError(session_id)
            return session_id
        return str(self.create_session(scope)["session_id"])

    def get_turns(self, session_id: str, scope: str) -> List[Dict[str, str]]:
        data, _ = self._load(_session_key(scope, session_id))
        return _llm_turns(data.get("turns") if data else [], self._max_turns)

    def append_turn(
        self,
        session_id: str,
        scope: str,
        user: str,
        assistant: str,
        tool_trace: Optional[List[Any]] = None,
        sources: Optional[List[Any]] = None,
        skill_run: Optional[Any] = None,
        usage: Optional[Any] = None,
    ) -> None:
        key = _session_key(scope, session_id)
        create = _new_record(scope, session_id=session_id)

        def fn(record: Dict[str, Any]) -> Dict[str, Any]:
            _add_turns(
                record,
                user,
                assistant,
                self._max_turns,
                tool_trace=tool_trace,
                sources=sources,
                skill_run=skill_run,
                usage=usage,
            )
            return record

        with self._lock:
            self._update(key, fn, create=create)

    def delete_session(self, session_id: str, scope: str) -> bool:
        """Soft-delete: move session blob under deleted/ (not a hard delete)."""
        key = _session_key(scope, session_id)
        data, _ = self._load(key)
        if not data or not _record_matches_scope(data, scope, session_id):
            return False
        data["deleted_at"] = _now()
        dest_key = _deleted_session_key(scope, session_id)
        with self._lock:
            try:
                self._blob(dest_key).upload_blob(_encode(data), overwrite=True)
                self._blob(key).delete_blob()
            except self._ResourceNotFoundError:
                return False
            except Exception as exc:
                self._reraise_blob_error(exc, "archive delete")
        return True


SessionStore = BlobSessionStore
ChatSessionStore = BlobSessionStore


def create_session_store(config: dict) -> SessionStore:
    sessions = config.get("sessions") if isinstance(config.get("sessions"), dict) else {}
    try:
        turns = max(1, int(sessions.get("max_turns", 30)))
    except (TypeError, ValueError):
        turns = 30

    storage = config.get("storage") if isinstance(config.get("storage"), dict) else {}
    account = str(storage.get("account_name", "") or "").strip()
    container = str(storage.get("chat_container", "") or "").strip() or "chat-sessions"
    if not account:
        raise RuntimeError(
            "storage.account_name is required in config.json "
            "(DefaultAzureCredential, else AzureCliCredential + az login)."
        )
    return BlobSessionStore(account, container, turns)
