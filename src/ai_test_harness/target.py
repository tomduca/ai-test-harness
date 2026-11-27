"""A target: everything the harness needs to know about one site under test."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_TARGETS_DIR = Path("targets")


class TargetError(ValueError):
    """Raised when a target cannot be found or its configuration is invalid."""


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    language: str = "English"
    planner_hints: list[str] = Field(default_factory=list)
    root: Path  # set by the loader: the target's folder

    @field_validator("base_url")
    @classmethod
    def _http_url_without_trailing_slash(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value.rstrip("/")

    @property
    def specs_dir(self) -> Path:
        return self.root / "specs"

    @property
    def plans_dir(self) -> Path:
        return self.root / "plans"

    @property
    def openapi_path(self) -> Path:
        return self.root / "openapi.yaml"


def available_targets(targets_dir: Path = DEFAULT_TARGETS_DIR) -> list[str]:
    return sorted(config.parent.name for config in targets_dir.glob("*/target.toml"))


def load_target(
    name: str | None = None, targets_dir: Path = DEFAULT_TARGETS_DIR
) -> Target:
    """Resolve the target: explicit name, then $HARNESS_TARGET, then the only one available."""
    available = available_targets(targets_dir)
    name = name or os.getenv("HARNESS_TARGET")
    if not name:
        if len(available) != 1:
            raise TargetError(
                f"choose a target with --target or HARNESS_TARGET; available: {available}"
            )
        name = available[0]

    root = targets_dir / name
    config = root / "target.toml"
    if not config.exists():
        raise TargetError(f"unknown target '{name}'; available: {available}")
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
        target = Target(**data, root=root)
    except (tomllib.TOMLDecodeError, ValidationError, TypeError) as exc:
        raise TargetError(f"{config}: invalid target configuration: {exc}") from exc
    if target.name != name:
        raise TargetError(
            f"{config}: name '{target.name}' must match its folder '{name}'"
        )
    return target
