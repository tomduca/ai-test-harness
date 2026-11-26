"""Planner output: a validated, closed vocabulary of test actions."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

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
    "img",
    "list",
    "listitem",
    "table",
    "row",
    "cell",
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
    exact: bool = Field(False, description="Exact, case-sensitive match of name/text")
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


class _Action(BaseModel):
    step: int = Field(
        ge=0, description="0-based index of the Gherkin step this action implements"
    )


class Goto(_Action):
    action: Literal["goto"] = "goto"
    path: SitePath


class Click(_Action):
    action: Literal["click"] = "click"
    locator: Locator


class ExpectVisible(_Action):
    action: Literal["expect_visible"] = "expect_visible"
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


Action = Annotated[
    Goto
    | Click
    | ExpectVisible
    | ExpectText
    | ExpectUrlPath
    | ExpectItems
    | ExpectNoConsoleErrors
    | ExpectImagesLoaded,
    Field(discriminator="action"),
]


class TestPlan(BaseModel):
    __test__ = False  # not a pytest test class, despite the name

    scenario_id: str
    actions: list[Action] = Field(min_length=1)
