# API Reference

## Interactive Documentation

Once the backend is running, the full OpenAPI (Swagger UI) is available at:

```
https://<container-app-fqdn>/docs
```

ReDoc alternative:

```
https://<container-app-fqdn>/redoc
```

## Static Endpoint Table

All endpoints require `Authorization: Bearer <access_token>` except `/api/auth/register`, `/api/auth/login`, and `/api/health`.

Standard error envelope: `{ "detail": "...", "code": "..." }`

### Health

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | None | Returns `{"status":"ok"}` — used by liveness and readiness probes |

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Create account — `{ email, password, display_name? }` → 201 |
| POST | `/api/auth/login` | Obtain tokens — `{ email, password }` → `{ access_token, refresh_token }` + httpOnly refresh cookie |
| POST | `/api/auth/refresh` | Rotate refresh token → new access token |
| GET | `/api/auth/me` | Current user info |

### Notes

| Method | Path | Description |
|---|---|---|
| POST | `/api/notes` | Create note; triggers AI pipeline |
| GET | `/api/notes` | List notes — `?category=&tag=&date_from=&date_to=&q=&limit=50&offset=0` |
| GET | `/api/notes/{id}` | Get single note |
| PUT | `/api/notes/{id}` | Partial update (`NoteUpdate` schema) |
| DELETE | `/api/notes/{id}` | Delete note — 204 |

### Voice / Upload

| Method | Path | Description |
|---|---|---|
| POST | `/api/voice/upload` | Multipart audio → STT → NoteOut |
| WS | `/api/voice/stream?token=<jwt>` | Streaming STT — bidirectional; server emits `{ type, text, is_final }` |
| POST | `/api/upload` | Upload audio or image blob; returns SAS URL |

### Search

| Method | Path | Description |
|---|---|---|
| POST | `/api/search` | Hybrid semantic + keyword search — `{ query, category?, tags?, date_from?, date_to?, limit=20 }` |
| GET | `/api/search/similar/{note_id}` | Similar notes by cosine distance |

### AI / Insights

| Method | Path | Description |
|---|---|---|
| POST | `/api/ai/process/{note_id}` | Manually trigger AI pipeline (idempotent) |
| GET | `/api/ai/summary/daily?date=` | Daily summary |
| GET | `/api/ai/summary/weekly?week=` | Weekly summary |
| POST | `/api/ai/generate` | Generate content — `{ kind: 'song'\|'practice'\|'reflection', source_note_ids[] }` |
| GET | `/api/insights/patterns` | Detected themes and patterns |
| GET | `/api/insights/graph` | Graph data — `{ nodes, links }` |

### Tags

| Method | Path | Description |
|---|---|---|
| GET | `/api/tags` | List tags |
| POST | `/api/tags` | Create tag |

### Sync

| Method | Path | Description |
|---|---|---|
| POST | `/api/sync/push` | Push offline operations — `{ operations: SyncOp[] }` |
| GET | `/api/sync/pull?since={ISO8601}` | Pull server changes since timestamp |

### Export

| Method | Path | Description |
|---|---|---|
| GET | `/api/export` | Full data dump JSON + signed media URLs |

### Personal Dictionary (Phase 2)

| Method | Path | Description |
|---|---|---|
| GET | `/api/dictionary` | List vocabulary terms |
| POST | `/api/dictionary` | Add term (max 2000/user) |
| PUT | `/api/dictionary/{id}` | Update term |
| DELETE | `/api/dictionary/{id}` | Remove term |
| POST | `/api/dictionary/bulk` | Bulk import ≤ 500 terms |
| GET | `/api/dictionary/export` | Export terms as JSON |

### Shadow Reader (Phase 2)

| Method | Path | Description |
|---|---|---|
| GET | `/api/notes/{id}/shadow-reader` | Get questions and status |
| POST | `/api/notes/{id}/shadow-reader/answer` | Submit answer |
| POST | `/api/notes/{id}/shadow-reader/dismiss` | Dismiss prompt |
| PUT | `/api/users/me/shadow-reader/settings` | Update enabled / disabled categories |

## Rate Limits

100 requests per minute per authenticated user (per IP for unauthenticated requests). Exceeding returns HTTP 429 with `Retry-After` header.
