"""Planner output: a validated, closed vocabulary of test actions."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_test_harness.contracts import ContractName

# Subset of ARIA roles the planner may use. Kept small on purpose: fewer ways to be wrong.
Role = Literal[
    "link",
    "button",
    "heading",
    "navigation",
    "main",
    "banner",
    "contentinfo",
    "region",
    "status",
    "img",
    "list",
    "listitem",
    "table",
    "row",
    "cell",
    "columnheader",
    "textbox",
    "combobox",
    "option",
]

# Site-relative path: "/" alone, or "/" + non-slash, no whitespace anywhere ("//x" leaves the site).
SitePath = Annotated[
    str,
    Field(
        pattern=r"^/([^/\s]\S*)?$", description="Site-relative path, e.g. '/' or '/en/'"
    ),
]


class Scope(BaseModel):
    """Container that narrows a locator, e.g. the navigation landmark."""

    role: Role
    name: str | None = None


class Locator(BaseModel):
    """How to find an element. Use exactly one strategy; prefer role+name over text, label or css."""

    role: Role | None = Field(None, description="ARIA role, e.g. 'link' or 'heading'")
    name: str | None = Field(
        None, description="Accessible name; only valid together with role"
    )
    text: str | None = Field(None, description="Visible text of the element")
    label: str | None = Field(None, description="Label of a form control")
    css: str | None = Field(None, description="CSS selector. Last resort only")
    exact: bool = Field(
        False,
        description="Case-sensitive match. Matching always uses the whole name/text",
    )
    within: Scope | None = Field(
        None, description="Optional container to search inside"
    )

    @model_validator(mode="after")
    def _exactly_one_strategy(self):
        strategies = [s for s in (self.role, self.text, self.label, self.css) if s]
        if len(strategies) != 1:
            raise ValueError("use exactly one of: role, text, label, css")
        if self.name and not self.role:
            raise ValueError("'name' is only valid together with 'role'")
        return self


def _require_action(schema: dict) -> None:
    """Python code may omit `action` (it has a default), but the LLM must always send it:
    without the discriminator, the union cannot be resolved."""
    required = schema.setdefault("required", [])
    if "action" in schema.get("properties", {}) and "action" not in required:
        required.insert(0, "action")


class _Action(BaseModel):
    model_config = ConfigDict(json_schema_extra=_require_action)

    step: int = Field(
        ge=0, description="0-based index of the Gherkin step this action implements"
    )


# --- Browser actions ---------------------------------------------------------


class Goto(_Action):
    action: Literal["goto"] = "goto"
    path: SitePath


class Click(_Action):
    action: Literal["click"] = "click"
    locator: Locator


class Fill(_Action):
    action: Literal["fill"] = "fill"
    locator: Locator
    value: str = Field(description="Text to type. Leading/trailing spaces are kept")


class ExpectVisible(_Action):
    action: Literal["expect_visible"] = "expect_visible"
    locator: Locator


class ExpectHidden(_Action):
    """Passes when no matching element is visible (including when none exists)."""

    action: Literal["expect_hidden"] = "expect_hidden"
    locator: Locator


class ExpectText(_Action):
    action: Literal["expect_text"] = "expect_text"
    locator: Locator
    text: str


class ExpectUrlPath(_Action):
    action: Literal["expect_url_path"] = "expect_url_path"
    path: SitePath


class ExpectItems(_Action):
    """The elements matched by the locator have exactly these texts, in this order."""

    action: Literal["expect_items"] = "expect_items"
    locator: Locator
    items: list[str] = Field(min_length=1)


class ExpectNoConsoleErrors(_Action):
    action: Literal["expect_no_console_errors"] = "expect_no_console_errors"


class ExpectImagesLoaded(_Action):
    action: Literal["expect_images_loaded"] = "expect_images_loaded"


# --- API actions (they act on the LAST response from api_get) ----------------


class QueryParam(BaseModel):
    name: str
    value: str = Field(
        description="Sent as is (URL-encoded by the client), spaces included"
    )


class ApiGet(_Action):
    action: Literal["api_get"] = "api_get"
    path: SitePath
    params: list[QueryParam] = Field(default_factory=list)


class ExpectStatus(_Action):
    action: Literal["expect_status"] = "expect_status"
    status: int = Field(ge=100, le=599)


class ExpectContract(_Action):
    action: Literal["expect_contract"] = "expect_contract"
    contract: ContractName = Field(
        description="qso_lookup: 200 lookup body; api_error: 4xx body; health: /api/health body"
    )


JsonOp = Literal[
    "equals",
    "empty",
    "not_empty",
    "any_item_has",
    "all_items_have",
    "younger_than_hours",
]
ITEM_OPS = {"any_item_has", "all_items_have"}
OPS_WITH_VALUE = {"equals", "younger_than_hours"} | ITEM_OPS


class ExpectJson(_Action):
    """One assertion on the JSON body of the last API response."""

    action: Literal["expect_json"] = "expect_json"
    field: str = Field(
        description="Dot path in the body, e.g. 'found', 'qsos', 'last_sync'"
    )
    op: JsonOp = Field(
        description=(
            "equals: field == value; empty / not_empty: list or string length; "
            "any_item_has / all_items_have: items of the list `field` whose `item_field` "
            "equals value; younger_than_hours: ISO timestamp newer than `value` hours"
        )
    )
    value: str | int | float | bool | None = Field(
        None,
        description="Use real JSON types: true/false for booleans, numbers for numbers",
    )
    item_field: str | None = Field(
        None, description="Field of each list item (item ops only)"
    )

    @model_validator(mode="after")
    def _arguments_match_op(self):
        if self.op in OPS_WITH_VALUE and self.value is None:
            raise ValueError(f"op '{self.op}' needs a value")
        if self.op in ITEM_OPS and not self.item_field:
            raise ValueError(f"op '{self.op}' needs item_field")
        return self


Action = Annotated[
    Goto
    | Click
    | Fill
    | ExpectVisible
    | ExpectHidden
    | ExpectText
    | ExpectUrlPath
    | ExpectItems
    | ExpectNoConsoleErrors
    | ExpectImagesLoaded
    | ApiGet
    | ExpectStatus
    | ExpectContract
    | ExpectJson,
    Field(discriminator="action"),
]


class TestPlan(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    scenario_id: str
    actions: list[Action] = Field(min_length=1)
