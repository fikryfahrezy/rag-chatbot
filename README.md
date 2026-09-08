# Scoped RAG Chatbot PoC

Proof of concept untuk tiga kelompok pengguna:

- **Internal sales/manager** — tanya status order, komisi, dan stok dengan pembatasan row-level per sales dan wilayah.
- **Publik** — hanya melihat proyeksi data yang aman (contoh: tersedia/tidak tersedia tanpa jumlah stok) dan PDF berlabel `public`.
- **Knowledge base** — unggah PDF, ekstrak teks, cari potongan relevan, lalu jawab dengan sumber dan halaman.

PoC memakai **Vue 3 + Vite + TypeScript** dan **FastAPI + SQLAlchemy**. Python dipilih untuk backend PoC karena ekosistem document ingestion dan model provider lebih matang. Bila sistem tumbuh, Go cocok ditambahkan sebagai API gateway/domain service, sementara Python tetap menjadi AI orchestration service.

## Prinsip keamanan

LLM bukan lapisan authorization. Identitas dan scope diterapkan pada query backend sebelum hasil masuk ke prompt:

| Peran | Order & komisi | Stok | Dokumen |
|---|---|---|---|
| Sales | Data sendiri | Wilayah sendiri | public, internal, wilayah sendiri |
| Manager | Semua sales di wilayah sendiri | Wilayah sendiri | public, internal, wilayah sendiri |
| Admin | Semua | Semua | Semua |
| Public | Tidak ada | Hanya label ketersediaan | Hanya berlabel public |

Endpoint demo memakai header `X-Demo-User`. Production wajib menggantinya dengan OIDC/JWT tervalidasi dan mengambil `user_id`, `role`, serta `region` dari claim—bukan dari input chat.

## Arsitektur

```text
Vue UI
  ├─ persona demo + workspace
  ├─ chat + citations
  ├─ PDF upload + visibility
  └─ model settings (admin)
           │
       FastAPI
  ┌────────┴─────────┐
  │                  │
Operations       PDF knowledge
  │                  │
allow-listed      parse + chunk
tool router       scoped retrieval
  │                  │
RBAC/RLS policy   visibility policy
  └────────┬─────────┘
      Model gateway
 demo / Ollama / OpenAI / Anthropic
```

Model dapat diatur terpisah dari UI admin:

- `database_planner` memilih salah satu tool `order`, `commission`, atau `inventory`; model tidak boleh membuat SQL bebas.
- `database_answer` merangkai jawaban dari hasil query yang sudah difilter.
- `pdf_answer` menjawab hanya dari potongan PDF yang diizinkan.

Mode `demo` bersifat deterministik dan langsung berjalan tanpa model atau API key. Adapter provider berada di `backend/app/providers.py`; kunci API hanya dibaca backend. Adapter OpenAI memakai Responses API dengan penyimpanan response dinonaktifkan (`store: false`).

## Menjalankan lokal

Persyaratan: Python 3.13.15, Node.js 22.23.2, npm, dan uv 0.12.9.

Versi dependency langsung dikunci secara exact di `pyproject.toml` dan `package.json`. Seluruh dependency transitif dikunci melalui `backend/uv.lock` dan `frontend/package-lock.json`; gunakan `uv sync --frozen` dan `npm ci` agar install gagal bila manifest dan lockfile tidak sinkron.

```bash
cp .env.example .env
make install
```

Terminal pertama:

```bash
make backend
```

Terminal kedua:

```bash
make frontend
```

Buka `http://localhost:5173`. Pilih persona di kanan atas untuk menguji isolasi. Contoh:

- Sebagai `Ayu`: `Status order ORD-1002?` harus tidak ditemukan.
- Sebagai `Manager Jakarta`: `Berapa komisi bulan ini?` hanya menjumlahkan Jakarta.
- Sebagai `Public visitor`: pertanyaan stok hanya mengembalikan tersedia/tidak tersedia.
- Sebagai user internal: upload PDF, pilih audience, lalu tanyakan isinya di workspace dokumen.

Alternatif Docker:

```bash
docker compose up --build
```

Image aplikasi menggunakan Debian Bookworm dengan tag versi eksplisit: `python:3.13.15-slim-bookworm`, `node:22.23.2-bookworm-slim`, dan `nginx:1.28.0-bookworm` (stable branch), tanpa image Alpine.

Frontend tersedia di `http://localhost:5173`, backend/OpenAPI di `http://localhost:8000/docs`.

## Menggunakan model sungguhan

Untuk lokal, install Ollama dan pull model yang diinginkan, misalnya chat model Qwen. Login sebagai `Admin`, buka **Pengaturan model**, pilih `ollama`, lalu isi nama model yang tersedia di Ollama.

Untuk API, isi `OPENAI_API_KEY` atau `ANTHROPIC_API_KEY` di `.env`, lalu pilih provider dan model dari UI. Jangan pernah menaruh API key di environment frontend (`VITE_*`).

Rekomendasi awal untuk deployment lokal tetap:

- chat/tool use: Qwen3.5 4B Q4; gunakan 9B bila hardware memadai;
- embedding: Qwen3-Embedding-0.6B atau BGE-M3;
- OCR scanned PDF: OCRmyPDF + Tesseract sebelum ingestion;
- production vector store: pgvector (bila sudah memakai PostgreSQL) atau Qdrant.

PoC sengaja memakai lexical retrieval agar ringan dan dapat didemokan offline. Interface retrieval terisolasi di `retrieval.py`, sehingga tahap berikutnya adalah menggantinya dengan hybrid dense + keyword retrieval tanpa mengubah kontrak API/UI.

## Pengujian

```bash
make test
```

Test backend memverifikasi dua batas terpenting: sales tidak dapat membaca order sales lain dan manager tidak dapat membaca komisi wilayah lain.

## Batas PoC sebelum production

- Gunakan PostgreSQL dan Row-Level Security sebagai defense-in-depth; akun database AI harus read-only.
- Tambahkan OIDC/SSO, audit log, rate limiting, prompt-injection filtering, dan approval untuk aksi tulis.
- Scan upload (malware), validasi MIME, simpan object storage, dan jalankan OCR asynchronous.
- Tambahkan conversation persistence dengan tenant ID, deletion/retention policy, dan redaction PII.
- Buat evaluation set per intent dan role; ukur retrieval recall, groundedness, kebocoran lintas tenant, latency, dan biaya.
- Model planner hanya memilih tool/schema tervalidasi. Jangan mengeksekusi SQL mentah buatan model.

Lihat [PROPOSAL.md](./PROPOSAL.md) untuk tahapan implementasi setelah PoC.
