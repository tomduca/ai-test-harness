"""API contracts the harness validates responses against.

Executable version of docs/contracts/qso-lookup-v0.2.md. Strict on purpose: unknown fields,
missing fields and wrong types all fail.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

ContractName = Literal["qso_lookup", "api_error", "health"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Qso(_Strict):
    date: dt.date
    band: str
    mode: str
    lotw_confirmed: bool  # value owned by LoTW: only its type is part of the contract
    call_logged: str


class QsoLookup(_Strict):
    call: str
    found: bool
    qsos: list[Qso]

    @model_validator(mode="after")
    def _not_found_means_no_qsos(self):
        if not self.found and self.qsos:
            raise ValueError("found is false but qsos is not empty")
        return self


class ApiError(_Strict):
    error: str
    message: str


class Health(_Strict):
    status: str
    last_sync: dt.datetime
    qso_count: int


CONTRACTS: dict[str, type[BaseModel]] = {
    "qso_lookup": QsoLookup,
    "api_error": ApiError,
    "health": Health,
}
