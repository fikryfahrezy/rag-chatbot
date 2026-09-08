# Proposal Implementasi

## Keputusan teknis

Mulai dengan modular monolith FastAPI. Ini memberi jalur tercepat untuk membuktikan authorization, ingestion, retrieval, dan pergantian provider. Pisahkan menjadi Go domain API + Python AI service hanya ketika ownership tim, beban, atau scaling menuntutnya; pemisahan prematur menambah network hop dan dua deployment tanpa memperbaiki keamanan.

Data transaksi dan dokumen memakai dua jalur berbeda:

1. **Data terstruktur/live**: intent → tool allow-list → query parameterized → policy scope → hasil ringkas → model jawaban.
2. **Dokumen**: parse/OCR → chunk → embed → vector + metadata → filter metadata berdasarkan audience → retrieve → model jawaban + citation.

Tidak ada kebutuhan untuk "melatih" model dengan PDF pada tahap awal. RAG lebih murah, mudah diperbarui, dapat menyertakan citation, dan memungkinkan dokumen dicabut. Fine-tuning baru relevan untuk gaya/format atau perilaku yang konsisten, bukan untuk menanam fakta yang sering berubah.

## Tahapan

### Fase 0 — PoC (repo ini)

- Persona demo sales, manager wilayah, admin, dan publik.
- Query aman untuk order, komisi, inventory.
- PDF text extraction, chunking, lexical retrieval, citation.
- Provider adapter demo, Ollama, OpenAI, Anthropic.
- Model terpisah per task melalui UI admin.

### Fase 1 — Pilot internal

- PostgreSQL + RLS, pgvector, OIDC/SSO, dan audit log.
- Background worker untuk ingestion/OCR dan status job.
- Hybrid retrieval serta reranker hanya bila evaluation menunjukkan manfaat.
- Streaming response dan conversation history terisolasi tenant.
- Golden test set termasuk percobaan akses order sales/wilayah lain.

### Fase 2 — Public launch

- Service/API publik terpisah atau database view khusus publik.
- WAF, per-IP/session rate limit, abuse monitoring, dan budget limit.
- Content moderation, prompt-injection defenses, serta cache untuk pertanyaan umum.
- Review legal/privacy untuk dokumen dan field yang dipublikasikan.

## Kontrak tool yang disarankan

Model hanya menghasilkan struktur tervalidasi seperti:

```json
{"tool":"get_order_status","arguments":{"order_no":"ORD-1001"}}
```

Backend menambahkan scope dari token identitas, bukan dari output model:

```sql
SELECT order_no, status, updated_at
FROM orders
WHERE order_no = :order_no
  AND sales_id = :authenticated_sales_id
LIMIT 1;
```

Manager memakai `region = :authenticated_region`. PostgreSQL RLS sebaiknya mengulang aturan ini agar bug aplikasi tidak langsung menjadi data leak.

## Model routing

Jangan memilih model hanya berdasarkan nama provider. Simpan konfigurasi per task beserta parameter dan fallback:

| Task | Kebutuhan | Default pilot |
|---|---|---|
| Database planner | structured output/tool calling | model kecil, temperature 0 |
| Database answer | Bahasa Indonesia + fidelity angka | model kecil/menengah |
| PDF answer | long context + citation discipline | model menengah |
| Embedding | multilingual semantic retrieval | Qwen3-Embedding-0.6B |
| Reranking (opsional) | relevance | tambah setelah evaluasi |

Provider fallback tidak boleh mengubah policy. Saat provider gagal, sistem lebih aman mengembalikan error atau jawaban template dari hasil tool daripada mengirim data ke provider lain tanpa persetujuan data residency.

## Definition of done pilot

- Tidak ada cross-sales/cross-region leak pada automated adversarial tests.
- Semua jawaban transaksi dapat ditelusuri ke query/tool invocation.
- Jawaban PDF menyertakan dokumen dan halaman; jawaban tanpa evidence menolak dengan jelas.
- p95 latency dan biaya per intent tercatat.
- Admin dapat mengganti model tanpa redeploy, dengan audit perubahan.
- Dokumen dapat dihapus dan hilang dari hasil retrieval sesuai SLA.
