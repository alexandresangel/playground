"""Read-only migration audit. Run from any directory with Python 3.12.

This verifies source provenance and the explicit preservation boundary. It neither
copies nor synchronizes projects and is not a runtime/integration dependency.
"""

import ast
import copy
import hashlib
import json
from pathlib import Path

REWORKS = Path(__file__).resolve().parent
ORIGINAL = REWORKS.parent
BASELINE = json.loads((REWORKS / "original-sha256.json").read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definitions(path, *, nested=False):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = ast.walk(tree) if nested else tree.body
    return {node.name: node for node in nodes if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}


def canonical(node):
    return ast.dump(node, include_attributes=False)


class PreservationNormalizer(ast.NodeTransformer):
    """Ignore only the explicit relocation names and content-free span/close additions."""
    names = {"capture_config": "intelligence_contract_config", "capture_enabled": "intelligence_contract_enabled",
        "init_capture_prompts": "init_ic_prompts", "refresh_capture_prompts": "refresh_ic_prompts",
        "capture_prompt_version": "ic_prompt_version", "capture_prompt_source": "ic_prompt_source",
        "capture_trade_types": "ic_trade_types", "capture_view_entity": "ic_view_entity",
        "capture_temperature": "ic_temperature", "LEGACY_BLOB_PREFIX": "IC_SKILL_PREFIX",
        "run_capture": "run_intelligence_contract", "router": "app",
        "build_azure_client": "_build_azure_client"}

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == "runtime":
            fields = {"config": "_CONFIG", "sessions": "_session_store", "auth": "_jwt_auth",
                      "tracer": "_otel_tracer", "base_dir": "_BASE_DIR", "azure_client": "_build_azure_client"}
            if node.attr in fields:
                return ast.Name(id=fields[node.attr], ctx=ast.Load())
        return self.generic_visit(node)

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if ast.unparse(node) == "_BASE_DIR / 'static'":
            return ast.Name(id="_STATIC_DIR", ctx=ast.Load())
        return node

    def visit_Name(self, node):
        node.id = self.names.get(node.id, node.id)
        return node

    def visit_FunctionDef(self, node):
        if node.args.args and node.args.args[0].arg == "runtime":
            node.args.args.pop(0)
        if node.name == "build_azure_client":
            node.args.args = []
            for item in ast.walk(node):
                if isinstance(item, ast.Name) and item.id == "config":
                    item.id = "_CONFIG"
        node.name = self.names.get(node.name, node.name)
        self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "record_usage":
            return None
        return self.generic_visit(node)

    def visit_With(self, node):
        self.generic_visit(node)
        if len(node.items) == 1 and isinstance(node.items[0].context_expr, ast.Call) and isinstance(node.items[0].context_expr.func, ast.Name) and node.items[0].context_expr.func.id == "ai_span":
            return node.body
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "runtime":
            node.args.pop(0)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "start_as_current_span":
            node.keywords = [k for k in node.keywords if k.arg not in ("record_exception", "set_status_on_exception")]
        return node

    def visit_Try(self, node):
        self.generic_visit(node)
        if not node.handlers and not node.orelse and len(node.finalbody) == 1 and isinstance(node.finalbody[0], ast.Expr):
            call = node.finalbody[0].value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "close" and ast.unparse(call.func.value) == "azure['client']":
                return node.body
        return node


def normalized(node):
    return canonical(PreservationNormalizer().visit(copy.deepcopy(node)))


class CaptureAdapterNormalizer(PreservationNormalizer):
    """Capture changes only the final telemetry call/span in the extraction route."""

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in ("_emit_chat_observability", "record_capture_result"):
            return None
        return super().visit_Expr(node)

    def visit_Constant(self, node):
        if node.value == "capture.completion":
            node.value = "chat.completion"
        return node


def routes(defs):
    found = {}
    for name, node in defs.items():
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and isinstance(dec.func.value, ast.Name) and dec.func.value.id in ("app", "router") and dec.func.attr in ("get", "post", "delete"):
                found[(dec.func.attr, ast.literal_eval(dec.args[0]))] = (name, normalized(dec), canonical(node.args))
    return found


def main():
    current_originals = {p.relative_to(ORIGINAL).as_posix(): digest(p) for p in ORIGINAL.rglob("*")
                         if p.is_file() and "reworks" not in p.relative_to(ORIGINAL).parts}
    assert current_originals == BASELINE, "An original file was changed, added or removed outside reworks"
    old_defs = definitions(ORIGINAL / "app.py")
    old_routes = routes(old_defs)
    immutable = ["auth_setup.py", "blob_client.py", "build_info.py", "i18n.py", "mcp_context.py", "mcp_rpc.py",
                 "session_store.py", "settings.py", "telemetry.py"]
    exact_functions = ["_build_azure_client", "_resolve_session_id", "_session_store_error", "mint_instance_token", "revoke_token",
                       "list_sessions_endpoint", "create_session_endpoint", "get_session_endpoint", "delete_session_endpoint",
                       "get_i18n", "deploy_health", "index"]
    exact_agent_functions = ["_prepare_chat_context", "_compose_llm_messages", "_temporal_context_block", "_sample_chart_spec",
        "_looks_like_chart_request", "_get_server_mcp_summary", "_get_mcp_summary", "_normalize_tool_schema",
        "_parse_tool_arguments", "_tool_trace_entry", "_mention_exclude_rules", "_mention_label_slug", "_mention_token_for_tool",
        "_tool_info_from_raw", "_list_tools_for_server", "_list_mcp_tools", "_get_server_tool_definitions",
        "_get_mcp_tool_definitions", "_filter_tool_definitions", "_resolve_mention_token_to_names", "_parse_tool_route", "_mcp_tool_timeout_s",
        "chat", "list_mcp_tools_endpoint", "_sse_line"]
    for project, package in (("capture", "capture"), ("diapason-agent", "pascal")):
        dest = REWORKS / project
        source = dest / "src" / package
        company = source / "company"
        company_files = immutable + (["prompt_loader.py", "source_extract.py", "tool_audience.py"] if package == "pascal" else [])
        for name in company_files:
            assert digest(company / name) == BASELINE[name], f"{project}/{name} differs"
        assert digest(dest / "VERSION") == BASELINE["VERSION"]
        for directory in ("dia_jwt", "locales"):
            expected = {k: v for k, v in BASELINE.items() if k.startswith(directory + "/")}
            actual = {p.relative_to(company).as_posix(): digest(p) for p in (company / directory).rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts}
            assert actual == expected, f"{project}/{directory} differs"
        if package == "pascal":
            for name in ("config.example.json", "system_prompt.md"):
                assert digest(dest / name) == BASELINE[name], name
            for directory in ("frontend", "static"):
                expected = {k: v for k, v in BASELINE.items() if k.startswith(directory + "/")}
                actual = {p.relative_to(dest).as_posix(): digest(p) for p in (dest / directory).rglob("*") if p.is_file()}
                assert actual == expected, f"{project}/{directory} differs"
        new_defs = {}
        for path in [source / "runtime.py", *sorted((source / "api").glob("*.py")), *sorted((source / "agent").glob("*.py"))]:
            new_defs.update(definitions(path, nested=True))
        new_defs["_build_azure_client"] = new_defs["build_azure_client"]
        new_routes = routes(new_defs)
        capture_paths = {"/api/skills/intelligence-contract", "/api/auth/tokens", "/api/auth/revoke"}
        expected_routes = old_routes if package == "pascal" else {k: v for k, v in old_routes.items() if k[1] in capture_paths}
        retained_routes = new_routes if package == "pascal" else {k: v for k, v in new_routes.items() if k[1] in capture_paths}
        assert retained_routes == expected_routes, f"{project}: changed retained route/dependency signatures"
        if package == "capture":
            assert set(new_routes) == set(expected_routes) | {("get", "/health"), ("get", "/api/health"), ("post", "/api/refresh-prompt")}
            assert not any((dest / name).exists() for name in ("frontend", "static", "system_prompt.md", "prompt_loader.py"))
        functions = exact_functions + exact_agent_functions if package == "pascal" else [
            "_build_azure_client", "_resolve_session_id", "_session_store_error", "mint_instance_token", "revoke_token"]
        for name in functions:
            assert normalized(new_defs[name]) == normalized(old_defs[name]), f"{project}: changed boundary {name}"
        schemas = definitions(source / "api/schemas.py")
        expected_schemas = {name for name, node in old_defs.items() if isinstance(node, ast.ClassDef)} if package == "pascal" else {"MintTokenBody", "RevokeTokenBody"}
        assert set(schemas) == expected_schemas
        for name, node in schemas.items():
            assert canonical(node) == canonical(old_defs[name]), f"{project}: changed schema {name}"
        for name in ["intelligence_contract_metadata"] + (["health", "refresh_prompt", "intelligence_contract_skill", "_build_response", "chat_stream"] if package == "pascal" else []):
            assert normalized(new_defs[name]) == normalized(old_defs[name]), f"{project}: changed adapter behavior {name}"
        if package == "capture":
            name = "intelligence_contract_skill"
            normalize_capture = lambda node: canonical(CaptureAdapterNormalizer().visit(copy.deepcopy(node)))
            assert normalize_capture(new_defs[name]) == normalize_capture(old_defs[name]), "Capture extraction adapter changed beyond telemetry"
        extraction = source / ("compat/capture" if package == "pascal" else "workflow")
        for new_path, old_path in [("prompts.py", "ic_prompt_loader.py"), ("extract_xml.py", "skills/intelligence_contract/extract_xml.py")]:
            old_helpers = definitions(ORIGINAL / old_path)
            for name, node in definitions(extraction / new_path).items():
                old_name = PreservationNormalizer.names.get(name, name)
                assert normalized(node) == normalized(old_helpers[old_name]), f"{project}: changed extraction/helper behavior {name}"
        assert not list(dest.glob("*.py")), f"{project}: Python remains in project root"
        assert not (dest / "workflow_support").exists()
        for path in source.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("skills"), path
    capture = REWORKS / "capture/src/capture"
    pascal = REWORKS / "diapason-agent/src/pascal"
    for name in ("__init__.py", "prompts.py", "extract_xml.py", "xml_fields.py", "graph.py"):
        standalone = (capture / "workflow" / name).read_text(encoding="utf-8")
        compat = (pascal / "compat/capture" / name).read_text(encoding="utf-8")
        compat = compat.replace("pascal.compat.capture", "capture.workflow").replace("pascal.observability", "capture.observability")
        assert standalone == compat, f"Compatibility workflow drift: {name}"
    assert digest(capture / "observability/ai.py") == digest(pascal / "observability/ai.py")
    assets = {k: v for k, v in BASELINE.items() if k.startswith("skills/intelligence_contract/config/") and not k.endswith(("README.md", "upload.sh"))}
    for name, value in assets.items():
        target = name.replace("skills/intelligence_contract/config/", "capture/config/")
        assert digest(REWORKS / target) == value, f"Prompt/catalog bytes changed: {name}"
    print(f"PASS: {len(BASELINE)} original files unchanged; company bytes and retained Pascal routes/helpers verified; {len(assets)} Capture assets byte-identical; src layouts verified.")


if __name__ == "__main__":
    main()
