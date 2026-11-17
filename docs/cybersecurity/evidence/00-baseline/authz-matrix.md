| Método | Endpoint | Rol | HTTP |
|---|---|---|---|
| GET | `/telemetry/report` | anonymous | 200 |
| GET | `/telemetry/report` | user | 200 |
| GET | `/telemetry/report` | manager | 200 |
| GET | `/inventory/products` | anonymous | 401 |
| GET | `/inventory/products` | user | 200 |
| GET | `/inventory/products` | manager | 200 |
| GET | `/agent/memory` | anonymous | 401 |
| GET | `/agent/memory` | user | 200 |
| GET | `/agent/memory` | manager | 200 |
| POST | `/knowledge/query` | user | 200 |
| POST | `/knowledge/query` | manager | 200 |
| POST | `/api/users` | anonymous | 201 |
| POST | `/chat/sessions` | user | 201 |
| POST | `/chat/sessions` | manager | 201 |
