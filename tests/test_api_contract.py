"""Contract test for the public ``/api/v1`` API.

The generated OpenAPI schema is reduced to what clients depend on (routes,
parameters, status codes, and each model's fields, types, and required flags)
and compared with the committed snapshot. Cosmetic details that vary between
FastAPI and Pydantic versions (titles, descriptions, formats) are left out.

After an intentional API change, regenerate the snapshot with::

    UPDATE_API_SNAPSHOT=1 pytest tests/test_api_contract.py

and review the diff: in ``/api/v1`` only additions are allowed (see docs/API.md).
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from ipmg.web.app import create_app
from ipmg.web.db import Database
from ipmg.web.schemas import WEBSOCKET_EVENT_MODELS

SNAPSHOT = Path(__file__).parent / "snapshots" / "api_v1_contract.json"
HTTP_METHODS = ("get", "put", "post", "delete", "patch")


def _type(schema: Dict[str, Any]) -> str:
    """A compact, version-independent description of a JSON schema's type."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " | ".join(sorted(_type(option) for option in schema[key]))
    if "const" in schema:
        return f"const {schema['const']!r}"
    if "enum" in schema:
        return "enum " + ", ".join(repr(value) for value in schema["enum"])
    kind = schema.get("type", "any")
    if kind == "array":
        return f"array[{_type(schema.get('items', {}))}]"
    if kind == "object" and isinstance(schema.get("additionalProperties"), dict):
        return f"object[{_type(schema['additionalProperties'])}]"
    return str(kind)


def _operation(operation: Dict[str, Any]) -> Dict[str, Any]:
    contract: Dict[str, Any] = {
        "parameters": {
            param["name"]: {
                "in": param["in"],
                "required": param.get("required", False),
                "type": _type(param.get("schema", {})),
            }
            for param in operation.get("parameters", [])
        },
        "responses": {},
        "security": sorted(name for entry in operation.get("security", []) for name in entry),
    }
    body = operation.get("requestBody")
    if body:
        contract["requestBody"] = {
            media: _type(content.get("schema", {})) for media, content in body["content"].items()
        }
    for code, response in operation["responses"].items():
        content = response.get("content", {})
        contract["responses"][code] = {
            media: _type(item.get("schema", {})) for media, item in content.items()
        }
    return contract


def _model(schema: Dict[str, Any]) -> Dict[str, Any]:
    if "properties" not in schema:
        return {"type": _type(schema)}
    return {
        "required": sorted(schema.get("required", [])),
        "properties": {name: _type(prop) for name, prop in schema["properties"].items()},
    }


def contract(openapi: Dict[str, Any]) -> Dict[str, Any]:
    paths = {
        f"{method.upper()} {path}": _operation(item[method])
        for path, item in openapi["paths"].items()
        for method in HTTP_METHODS
        if method in item
    }
    models = {name: _model(schema) for name, schema in openapi["components"]["schemas"].items()}
    security = {
        name: {"type": scheme.get("type"), "scheme": scheme.get("scheme")}
        for name, scheme in openapi["components"].get("securitySchemes", {}).items()
    }
    return {
        "paths": dict(sorted(paths.items())),
        "schemas": dict(sorted(models.items())),
        "securitySchemes": security,
    }


@pytest.fixture()
def openapi(tmp_path) -> Dict[str, Any]:
    app = create_app(Database(tmp_path / "contract.db"), token="test-token")
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_api_matches_committed_snapshot(openapi):
    current = contract(openapi)
    if os.environ.get("UPDATE_API_SNAPSHOT"):
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert current == expected, (
        "The /api/v1 contract changed. If this is intentional, and only adds to the "
        "API, run 'UPDATE_API_SNAPSHOT=1 pytest tests/test_api_contract.py' and "
        "commit the updated snapshot."
    )


def test_every_json_route_has_a_typed_response(openapi):
    untyped = []
    for path, item in openapi["paths"].items():
        for method in HTTP_METHODS:
            if method not in item:
                continue
            for code, response in item[method]["responses"].items():
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if schema is not None and not schema:
                    untyped.append(f"{method.upper()} {path} {code}")
    assert untyped == []


def test_every_error_response_uses_the_error_model(openapi):
    for item in openapi["paths"].values():
        for method in HTTP_METHODS:
            for code, response in item.get(method, {}).get("responses", {}).items():
                if int(code) >= 400:
                    schema = response["content"]["application/json"]["schema"]
                    assert schema == {"$ref": "#/components/schemas/ErrorResponse"}


def test_websocket_events_are_published(openapi):
    schemas = openapi["components"]["schemas"]
    assert "WebSocketEvent" in schemas
    for model in WEBSOCKET_EVENT_MODELS:
        assert model.__name__ in schemas
