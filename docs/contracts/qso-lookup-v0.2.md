# QSO lookup API — contract v0.2

## GET /api/qso?call={callsign}[&band={band}]

- `call`: required. Case-insensitive; surrounding whitespace is ignored.
- `band`: optional, e.g. `20m`, `2m`.
- Portable stations: looking up a base call (`KE4TT`) or a portable form (`V4/KE4TT`,
  `LU1MAW/M`) returns the QSOs logged under any of those forms.

### 200 OK

| Field | Type | Notes |
|---|---|---|
| `call` | string | The normalized callsign that was looked up (uppercase, trimmed) |
| `found` | boolean | `false` when no QSO matches the lookup, including the band filter |
| `qsos` | array | Empty when `found` is `false` |
| `qsos[].date` | string | `YYYY-MM-DD`. No time is exposed (privacy) |
| `qsos[].band` | string | e.g. `10m`, `2m` |
| `qsos[].mode` | string | e.g. `SSB`, `FT8`, `FM` |
| `qsos[].lotw_confirmed` | boolean | Value owned by LoTW; only its type is part of the contract |
| `qsos[].call_logged` | string | How the QSO was logged (may differ from `call`, see portables) |

No other fields are allowed.

### 400 Bad Request

`{"error": "invalid_callsign", "message": "..."}`

## GET /api/health

`{"status": "ok", "last_sync": "<ISO-8601 UTC>", "qso_count": <int>}`

## Changelog

- **v0.2**: added `call_logged` (portable normalization); `found: false` when a band filter
  matches nothing; case and whitespace normalization made explicit.
- **v0.1**: initial contract.