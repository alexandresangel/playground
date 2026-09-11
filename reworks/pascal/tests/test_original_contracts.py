"""Optional migration-source audit; normal functional tests are self-contained."""

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from pascal.api import schemas

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT.parent / "diapason-agent-main"


def original_tree():
    if not ORIGINAL.is_dir():
        pytest.skip("Original source is available only in the migration workspace")
    return ast.parse((ORIGINAL / "app.py").read_text(encoding="utf-8"))


def test_original_request_response_schemas():
    original = original_tree()
    nodes = [node for node in original.body if isinstance(node, ast.ClassDef) and any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases)]
    ns = dict(BaseModel=BaseModel, Field=Field, Any=Any, Dict=Dict, List=List, Optional=Optional)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "original schemas", "exec"), ns)
    for node in nodes:
        assert getattr(schemas, node.name).model_json_schema() == ns[node.name].model_json_schema()


def test_original_routes_are_retained(service):
    original = original_tree()
    expected = set()
    for node in original.body:
        for decorator in getattr(node, "decorator_list", []):
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr in ("get", "post", "delete"):
                expected.add((decorator.func.attr, decorator.args[0].value))
    # OpenAPI handles flattened and included routers across supported FastAPI versions.
    actual = {(method, path) for path, value in service.app.openapi()["paths"].items() for method in value}
    assert expected - {("get", "/health")} <= actual


def test_company_modules_and_frontend_are_unchanged():
    original_tree()
    common = ROOT / "src/pascal/commun"
    for file in common.rglob("*.py"):
        old = ORIGINAL / file.relative_to(common)
        # Existing migration copies differ only in line endings/final newlines.
        assert file.read_text(encoding="utf-8").rstrip() == old.read_text(encoding="utf-8").rstrip(), file
    for directory in ("frontend", "static"):
        for file in (ORIGINAL / directory).rglob("*"):
            if file.is_file():
                assert (ROOT / file.relative_to(ORIGINAL)).read_bytes() == file.read_bytes()
    assert (ROOT / "system_prompt.md").read_bytes() == (ORIGINAL / "system_prompt.md").read_bytes()
    assert (ROOT / "deploy/infra.tf").read_bytes() == (ORIGINAL / "deploy/infra.tf").read_bytes()
