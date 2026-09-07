"""Small deterministic commands; ordinary unknown @mentions remain ordinary text."""

import re

from pascal.tools.registry import BoundTool, Catalogue


class RouteError(ValueError):
    pass


def route(message: str, catalogue: Catalogue) -> tuple[str, list[BoundTool], str | None]:
    stripped = message.strip()
    if stripped == "/help":
        return message, [], "Use /tools to list tools, /docs <question>, or @tool <question>."
    if stripped == "/tools":
        names = [
            f"@{tool.info['mention_token']}" for tool in catalogue.tools if tool.info["mentionable"]
        ]
        return message, [], "Available tools: " + (", ".join(names) or "none available")
    if stripped.startswith("/docs ") or stripped == "/docs":
        message = "@docs " + stripped[5:].strip()
    matches = list(re.finditer(r"(?<!\S)@([\w.-]+)", message))
    selected, spans = set(), []
    for match in matches:
        token = match[1].rstrip(".").lower()
        servers = [
            s
            for s in catalogue.servers
            if token
            in {
                s["server_id"].lower(),
                s["mention_prefix"].lower(),
                "diapason" if s["server_id"] == "default" else s["server_id"].lower(),
            }
        ]
        if len(servers) > 1:
            raise RouteError("Ambiguous MCP server mention")
        if servers:
            if not servers[0]["ok"]:
                raise RouteError("Requested MCP server is unavailable")
            group = [t for t in catalogue.tools if t.server.server_id == servers[0]["server_id"]]
        else:
            group = [
                t
                for t in catalogue.tools
                if t.info["mentionable"]
                and token
                in {
                    t.name.lower(),
                    t.info["native_name"].lower(),
                    t.info["mention_token"].lower(),
                }
            ]
            if len(group) > 1:
                raise RouteError("Ambiguous tool mention; use the server-qualified name")
        if group or servers:
            selected.update(t.name for t in group)
            spans.append(match.span())
    for start, end in reversed(spans):
        message = message[:start] + message[end:]
    if spans and not selected:
        raise RouteError("Requested scope has no available tools")
    return message.strip(), [t for t in catalogue.tools if not spans or t.name in selected], None
