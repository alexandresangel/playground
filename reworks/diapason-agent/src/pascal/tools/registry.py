"""Request-scoped tool bindings and an identity-partitioned bounded schema cache."""

import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass

from pascal.config import AgentLimits
from pascal.ports import McpTransport
from pascal.tools.audience import audience_from_raw, is_chat_api_listed, is_tool_mentionable
from pascal.tools.context import McpCluster, McpServerContext, qualify_tool_name


@dataclass(frozen=True)
class BoundTool:
    info: dict
    raw: dict
    server: McpServerContext

    @property
    def name(self) -> str:
        return self.info["name"]

    @property
    def definition(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.info["description"],
                "parameters": self.info["input_schema"],
            },
        }

    @property
    def readonly(self) -> bool:
        return (self.raw.get("annotations") or {}).get("readOnlyHint") is True


@dataclass
class Catalogue:
    tools: list[BoundTool]
    servers: list[dict]

    def public(self) -> dict:
        return {"servers": self.servers, "tools": [tool.info for tool in self.tools]}


def server_slug(server: McpServerContext) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", server.label.lower()).strip("-") or server.server_id


class ToolRegistry:
    def __init__(self, transport: McpTransport, limits: AgentLimits, exclude: list[str]):
        self.transport, self.limits, self.exclude = transport, limits, exclude
        self.cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()
        # Fixed stripes deduplicate identical discovery without a growing lock map or
        # one global network lock. Different tenants never share cached schemas.
        self.locks = [asyncio.Lock() for _ in range(16)]

    def key(self, scope: str, server: McpServerContext) -> str:
        credential = (
            server.credential_fingerprint
            or hashlib.sha256(
                json.dumps(server.request_headers, sort_keys=True).encode()
            ).hexdigest()
        )
        return hashlib.sha256(
            json.dumps(
                [
                    scope,
                    server.server_id,
                    server.server_url,
                    credential,
                ]
            ).encode()
        ).hexdigest()

    async def _raw(self, scope: str, server: McpServerContext) -> list[dict]:
        key = self.key(scope, server)
        async with self.locks[int(key[:8], 16) % len(self.locks)]:
            cached = self.cache.get(key)
            if cached and cached[0] > time.monotonic():
                self.cache.move_to_end(key)
                return cached[1]
            rows, cursor = [], None
            seen = set()
            # Legacy servers usually return one page; cap even malicious pagination.
            for _ in range(20):
                result = await self.transport.request(
                    server,
                    "tools/list",
                    {"cursor": cursor} if cursor else {},
                )
                page = result.get("tools", [])
                if not isinstance(page, list) or len(rows) + len(page) > 500:
                    raise ValueError("invalid_tool_catalogue")
                rows.extend(page)
                cursor = result.get("nextCursor")
                if not cursor:
                    break
                if not isinstance(cursor, str) or cursor in seen:
                    raise ValueError("invalid_tool_cursor")
                seen.add(cursor)
            else:
                raise ValueError("tool_catalogue_page_limit")
            self.cache[key] = (time.monotonic() + self.limits.catalogue_ttl_seconds, rows)
            self.cache.move_to_end(key)
            while len(self.cache) > self.limits.catalogue_max_entries:
                self.cache.popitem(last=False)
            return rows

    async def discover(self, cluster: McpCluster, scope: str) -> Catalogue:
        async def one(server):
            tools = []
            public = dict(
                server_id=server.server_id,
                label=server.label,
                mention_prefix=server_slug(server),
                server_url=server.server_url,
                ok=True,
                error=None,
                tools=[],
            )
            try:
                for raw in await self._raw(scope, server):
                    if not isinstance(raw, dict):
                        continue
                    native = raw.get("name", "")
                    if not isinstance(native, str) or not re.fullmatch(r"[\w-]{1,64}", native):
                        continue
                    audience = audience_from_raw(raw)
                    if not is_chat_api_listed(audience):
                        continue
                    name = qualify_tool_name(server.server_id, native)
                    if len(name) > 64:
                        continue
                    schema = raw.get("inputSchema") or {"type": "object", "properties": {}}
                    if not isinstance(schema, dict):
                        continue
                    mention = (
                        native
                        if server.server_id == "default"
                        else f"{server_slug(server)}.{native}"
                    )
                    info = dict(
                        name=name,
                        native_name=native,
                        mcp_server=server.server_id,
                        mcp_label=server.label,
                        description=str(raw.get("description", "")),
                        input_schema=schema,
                        audience=audience,
                        mentionable=is_tool_mentionable(native, name, audience, self.exclude),
                        mention_token=mention,
                    )
                    tools.append(BoundTool(info, raw, server))
                public["tools"] = [tool.info for tool in tools]
            except Exception:
                public.update(ok=False, error="Tool catalogue unavailable")
            return tools, public

        results = await asyncio.gather(*(one(server) for server in cluster.servers))
        tools = [tool for group, _ in results for tool in group]
        # Colliding qualified names must never route to an arbitrary server.
        counts = {name: sum(t.name == name for t in tools) for name in {t.name for t in tools}}
        tools = [t for t in tools if counts[t.name] == 1]
        servers = [public for _, public in results]
        for server in servers:
            server["tools"] = [info for info in server["tools"] if counts[info["name"]] == 1]
        return Catalogue(tools, servers)
