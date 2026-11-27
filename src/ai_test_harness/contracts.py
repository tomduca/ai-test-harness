"""API contracts from a target's OpenAPI 3.1 document, checked with JSON Schema 2020-12."""

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

DOCUMENT_URI = "urn:target:openapi"


class ContractError(ValueError):
    """Raised when a contract is missing or a response does not match it."""


class ContractSet:
    """The schemas under components/schemas of one OpenAPI document."""

    def __init__(self, document: dict, source: str):
        self.source = source
        self.text = yaml.safe_dump(document, sort_keys=False)
        self._schemas = document.get("components", {}).get("schemas", {})
        # OpenAPI 3.1 schemas are JSON Schema 2020-12; internal $refs resolve against the document.
        resource = Resource.from_contents(document, default_specification=DRAFT202012)
        self._registry = Registry().with_resource(DOCUMENT_URI, resource)

    @classmethod
    def load(cls, path: Path) -> ContractSet:
        if not path.exists():
            raise ContractError(f"no contract document at {path}")
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))

    @property
    def names(self) -> list[str]:
        return sorted(self._schemas)

    def validate(self, name: str, body_text: str) -> None:
        if name not in self._schemas:
            raise ContractError(f"unknown contract '{name}'; available: {self.names}")
        try:
            body = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise ContractError(f"response is not JSON: {body_text[:200]!r}") from exc

        validator = Draft202012Validator(
            {"$ref": f"{DOCUMENT_URI}#/components/schemas/{name}"},
            registry=self._registry,
            format_checker=FormatChecker(),
        )
        errors = sorted(
            validator.iter_errors(body), key=lambda e: list(e.absolute_path)
        )
        if errors:
            details = "; ".join(
                f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
                for e in errors[:5]
            )
            raise ContractError(f"does not match contract '{name}': {details}")
