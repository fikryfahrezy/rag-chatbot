import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import DEMO_USERS, current_user
from .chat import answer_chat
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import Document, DocumentChunk, ModelSetting
from .policies import require_internal, scope_documents
from .retrieval import ingest_pdf
from .schemas import ChatRequest, ChatResponse, DocumentOut, ModelSettingsPayload, User
from .seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().ensure_data_dirs()
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
    yield


app = FastAPI(title="Scoped RAG Chatbot PoC", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/users", response_model=list[User])
def users() -> list[User]:
    return list(DEMO_USERS.values())


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ChatResponse:
    if payload.workspace == "operations" and user.role == "public":
        raise HTTPException(status_code=403, detail="Public users cannot access operations")
    return await answer_chat(db, payload, user)


@app.get("/api/models")
def get_models(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_internal(user)
    rows = db.scalars(select(ModelSetting)).all()
    return {row.task: {"provider": row.provider, "model": row.model} for row in rows}


@app.put("/api/models")
def put_models(payload: ModelSettingsPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can change model settings")
    for task, choice in payload.model_dump().items():
        row = db.get(ModelSetting, task) or ModelSetting(task=task, provider="demo", model="fallback")
        row.provider = choice["provider"]
        row.model = choice["model"]
        db.add(row)
    db.commit()
    return payload.model_dump()


@app.get("/api/documents", response_model=list[DocumentOut])
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[DocumentOut]:
    stmt = scope_documents(select(Document), user)
    docs = db.scalars(stmt.order_by(Document.created_at.desc())).all()
    return [DocumentOut(
        id=doc.id, filename=doc.filename, visibility=doc.visibility, region=doc.region,
        chunks=db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc.id)) or 0,
    ) for doc in docs]


@app.post("/api/documents", response_model=DocumentOut)
def upload_document(
    file: UploadFile = File(...),
    visibility: str = Form("internal"),
    region: str | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    require_internal(user)
    if visibility not in {"public", "internal", "region"}:
        raise HTTPException(status_code=422, detail="Invalid visibility")
    if visibility == "region" and not region:
        raise HTTPException(status_code=422, detail="Region is required")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp.flush()
        if Path(tmp.name).stat().st_size > max_bytes:
            raise HTTPException(status_code=413, detail="File is too large")
        try:
            doc = ingest_pdf(db, tmp.name, file.filename or "document.pdf", visibility, region, user)
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail="PDF could not be parsed") from exc
    chunks = db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == doc.id)) or 0
    return DocumentOut(id=doc.id, filename=doc.filename, visibility=doc.visibility, region=doc.region, chunks=chunks)

