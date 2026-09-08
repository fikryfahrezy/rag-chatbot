# Scoped RAG Chatbot PoC

A proof of concept for three user groups:

- **Internal sales representatives and managers** — ask about order status, commissions, and inventory with row-level restrictions for each sales representative and region.
- **Public users** — access only an approved database projection, such as product availability without exact stock counts.
- **Knowledge-base users** — upload PDFs, extract their text, retrieve relevant passages, and answer questions with document and page citations.

The PoC uses **Vue 3 + Vite + TypeScript** for the frontend and **FastAPI + SQLAlchemy** for the backend. Python was selected for the PoC because its document-ingestion, retrieval, and model-provider ecosystem is more mature. If the system grows, Go can be introduced as an API gateway or domain service while Python remains responsible for AI orchestration.

## Security principles

The LLM is not an authorization layer. Identity and access scope are applied to backend queries before any result enters a prompt:

| Role | Orders and commissions | Inventory | Documents |
|---|---|---|---|
| Sales | Own records only | Own region | No document workspace access |
| Manager | All sales records in own region | Own region | No document workspace access |
| Admin | All records | All regions | All documents |
| Public | No access | Availability label only | No document workspace access |

The demo endpoint uses the `X-Demo-User` header. Production deployments must replace it with validated OIDC/JWT authentication and obtain `user_id`, `role`, and `region` from verified claims—not from chat input.

## Architecture

```text
Vue UI
  ├─ user selector (group is derived from the user profile)
  ├─ admin-only experience selector across all groups
  ├─ streaming chat and citations
  ├─ PDF upload and visibility
  └─ model settings (admin)
           │
       FastAPI
  ┌────────┴─────────┐
  │                  │
Operations       PDF knowledge
  │                  │
allow-listed      parse and chunk
tool router       scoped retrieval
  │                  │
RBAC/RLS policy   visibility policy
  └────────┬─────────┘
      Model gateway
 Ollama / OpenAI / Anthropic
```

Models are registered in the database from the admin UI and can then be assigned independently:

- `database_planner` selects one of the allow-listed `order`, `commission`, or `inventory` tools. It cannot generate arbitrary SQL.
- `database_answer` turns an already-authorized query result into a user-facing answer.
- `pdf_answer` answers only from retrieved PDF passages that the current user is permitted to access.

The registry stores a display name, provider, and provider-specific model ID or Ollama tag. It never stores API keys; credentials remain in the backend environment. When registering a model, the backend discovers available choices from the selected provider: installed Ollama models from `/api/tags`, account-accessible OpenAI models from `/v1/models`, or account-accessible Anthropic models from `/v1/models`. The selected model is validated against the provider again before it is saved. Provider adapters are located in `backend/app/providers.py`, and API keys are read only by the backend. The OpenAI adapter uses the Responses API with response storage disabled through `store: false`.

Chat answers stream end-to-end through `POST /api/chat/stream`. Provider-specific Ollama NDJSON and OpenAI/Anthropic server-sent events are normalized into NDJSON events for the Vue client. Database planning remains a short buffered step because its result must be validated before an authorized database query can run.

## Group-based experiences

All three groups use the same chat layout. The operator selects only a user; the application derives Group A, B, or C from that user's backend profile. The selected group then determines the data source and authorization policy rather than opening a different menu. The Administrator is an `All Groups` identity and can switch the current experience from the header:

| Group | Experience | Backend source |
|---|---|---|
| A | Order status, commissions, and inventory | Scoped operational database queries |
| B | Public-safe operational information | Public database projection only |
| C | Internal PDF knowledge | Visibility- and region-scoped document retrieval |

Group A includes neutral user profiles such as `Sales 1 — Jakarta` and `Sales Manager — Jakarta` so ownership and regional boundaries can be tested without personal-name aliases. Group B never queries the PDF store; an unavailable public database answer is returned as unavailable instead of falling back to documents. Group C provides employee users for regional document checks, and uploaded PDFs can be internal to Group C or limited to a region selected from the available user regions. The backend validates this selection and rejects unknown region values. The `All Groups` Administrator can use every experience, upload PDFs in the Group C experience, and configure models. The backend remains authoritative and rejects cross-group requests from non-admin users.

## Open-weight model recommendations

The application does not require one model for every task. Model size should be selected using the end user's available memory, processor, and acceptable latency.

### Recommended hardware profiles

| End-user hardware | Recommended Ollama model | Download size | Suitable for | Important limitation |
|---|---|---:|---|---|
| 8 GB RAM, CPU-only | `qwen3.5:2b-q4_K_M` | ~1.9 GB | Basic demos and short database answers | Less reliable for complex PDF questions and structured output |
| 12–16 GB RAM | `qwen3.5:4b-q4_K_M` | ~3.4 GB | Recommended baseline for Indonesian chat, database answers, and ordinary PDF Q&A | Keep retrieved context around 4K–8K tokens |
| 16–24 GB RAM with a modern CPU or Apple Silicon | `qwen3.5:9b-q4_K_M` | ~6.6 GB | Better reasoning, citation quality, and difficult PDF questions | Slow on older laptop CPUs; 24 GB provides safer runtime headroom |
| 20 GB RAM with an older mobile CPU, such as an i5-8265U | `qwen3.5:4b-q4_K_M` | ~3.4 GB | Best balance for a single-user PoC | A 9B model fits in RAM but is usually not worth the latency |

The download sizes come from the [official Ollama Qwen3.5 model listing](https://ollama.com/library/qwen3.5/tags). Actual runtime memory is higher and grows with context length. Do not configure the advertised maximum context by default on consumer hardware.

Qwen3.5 is recommended because its open weights use the Apache 2.0 license and the family supports multilingual instruction following and tool-oriented workflows. See the official [Qwen3.5 4B](https://huggingface.co/Qwen/Qwen3.5-4B) and [Qwen3.5 9B](https://huggingface.co/Qwen/Qwen3.5-9B) model cards.

### Recommended task assignment

For most end users with 12–20 GB RAM:

| Task | Provider and model | Reason |
|---|---|---|
| Database planning | `ollama / qwen3.5:4b-q4_K_M` | Local intent selection without sending operational questions to a hosted provider |
| Database answer | `ollama / qwen3.5:4b-q4_K_M` | Good balance of Indonesian quality and local resource use |
| PDF answer | `ollama / qwen3.5:4b-q4_K_M` | Practical default for ordinary internal documents |
| Embedding, after semantic retrieval is implemented | `qwen3-embedding:0.6b` | Dedicated multilingual retrieval model with a small footprint |
| Scanned-PDF OCR | OCRmyPDF with Tesseract | OCR is a document-processing task, not a chat-model task |

On a machine with a modern CPU or Apple Silicon and at least 16–24 GB of available memory, use `qwen3.5:9b-q4_K_M` for `pdf_answer` when answer quality is more important than latency. Avoid keeping both 4B and 9B generation models loaded simultaneously on memory-constrained machines.

The recommended embedding model, `qwen3-embedding:0.6b`, is approximately 639 MB and supports more than 100 languages. See the official [Qwen model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) and [Ollama model listing](https://ollama.com/library/qwen3-embedding/tags).

### Install the recommended models

Baseline installation:

```bash
ollama pull qwen3.5:4b-q4_K_M
```

Optional higher-quality generation model:

```bash
ollama pull qwen3.5:9b-q4_K_M
```

Embedding model for the planned semantic-retrieval upgrade:

```bash
ollama pull qwen3-embedding:0.6b
```

Verify installed and currently loaded models:

```bash
ollama list
ollama ps
```

The current PoC uses lightweight lexical retrieval, so the embedding model is not required yet.

## Running locally

Requirements: Python 3.13.15, Node.js 22.23.2, npm 10.9.8, and uv 0.12.9.

Direct dependency versions are pinned exactly in `pyproject.toml` and `package.json`. Transitive dependencies are locked in `backend/uv.lock` and `frontend/package-lock.json`. Use `uv sync --frozen` and `npm ci` so installation fails when a manifest and its lockfile do not match.

```bash
cp .env.example .env
make install
```

Start the backend in the first terminal:

```bash
make backend
```

Start the frontend in a second terminal:

```bash
make frontend
```

Open `http://localhost:5173` and select a user in the upper-right corner. Its group and authorization scope are applied automatically:

- In Group A as `Sales 1 — Jakarta`, asking `Status order ORD-1002?` must return “not found.”
- In Group A as `Sales Manager — Jakarta`, asking `Berapa komisi bulan ini?` must include only Jakarta.
- In Group B, an inventory question must return only available/unavailable labels.
- In Group C, upload a PDF, select its audience, and ask about it in the same chat interface.

Alternatively, use Docker:

```bash
docker compose up --build
```

The application images use explicitly versioned Debian Bookworm bases: `python:3.13.15-slim-bookworm`, `node:22.23.2-bookworm-slim`, and the stable `nginx:1.28.0-bookworm` image. No Alpine base image is used.

The frontend is available at `http://localhost:5173`, and the backend API documentation is available at `http://localhost:8000/docs`.

Container health checks run every 10 seconds. The backend is marked healthy only when `GET /api/health` succeeds, and the frontend starts after that condition is met. Nginx also exposes `GET /healthz` for external load balancers or uptime monitors.

## Configuring model providers

For local inference, install Ollama and pull one of the models listed above. Select the `All Groups · Administrator` user, open **Model settings**, register the Ollama model using its exact installed tag, then select that registered model for each applicable task.

For hosted inference, set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`, register the provider/model pair from the admin UI, and assign it to a task. Never expose API keys through frontend environment variables such as `VITE_*` or store them in the model registry.

The PoC intentionally uses lexical retrieval so it remains lightweight and can be demonstrated offline. The retrieval interface is isolated in `retrieval.py`; it can later be replaced with hybrid dense and keyword retrieval without changing the API or UI contract.

For production retrieval, use pgvector when PostgreSQL is already present, or Qdrant as a dedicated vector database. Add a reranker only when retrieval evaluations demonstrate that it materially improves results.

## Testing

```bash
make test
```

Backend tests verify the two most important access boundaries: a sales representative cannot read another representative's orders, and a regional manager cannot read another region's commissions.

## Before production

- Use PostgreSQL Row-Level Security as defense in depth, and give AI-facing database accounts read-only access.
- Add OIDC/SSO, audit logging, rate limiting, prompt-injection defenses, and explicit approval for write operations.
- Scan uploaded files for malware, validate MIME types, store files in object storage, and run OCR asynchronously.
- Persist conversations with tenant isolation, retention and deletion policies, and PII redaction.
- Build evaluation sets for each intent and role. Measure retrieval recall, groundedness, cross-tenant leakage, latency, and cost.
- Allow the model planner to select only validated tools and schemas. Never execute arbitrary SQL generated by a model.

See [PROPOSAL.md](./PROPOSAL.md) for the implementation phases beyond this PoC.
