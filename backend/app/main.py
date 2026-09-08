import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import DEMO_REGIONS, DEMO_USERS, current_user
from .chat import answer_chat, prepare_chat, stream_prepared_chat
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import Document, DocumentChunk, ModelSetting, RegisteredModel
from .policies import require_internal, require_knowledge_access, scope_documents
from .providers import ModelGateway
from .retrieval import ingest_pdf
from .schemas import (
    ChatRequest, ChatResponse, DocumentOut, ModelSettingsPayload,
    RegisteredModelCreate, RegisteredModelOut, User,
)
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
    group_workspace = {"A": "operations", "B": "public", "C": "knowledge"}
    if user.role != "admin" and payload.workspace != group_workspace.get(user.group):
        raise HTTPException(status_code=403, detail=f"Group {user.group} cannot access this data source")
    return await answer_chat(db, payload, user)


@app.post("/api/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    group_workspace = {"A": "operations", "B": "public", "C": "knowledge"}
    if user.role != "admin" and payload.workspace != group_workspace.get(user.group):
        raise HTTPException(status_code=403, detail=f"Group {user.group} cannot access this data source")
    async def events():
        try:
            yield json.dumps({"type": "status", "status": "Preparing authorized data…"}) + "\n"
            prepared = await prepare_chat(db, payload, user)
            yield json.dumps({"type": "status", "status": "Generating answer…"}) + "\n"
            async for event in stream_prepared_chat(prepared):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception:
            yield json.dumps({"type": "error", "error": "Model provider streaming failed"}) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/models")
def get_models(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_internal(user)
    rows = db.scalars(select(ModelSetting)).all()
    return {row.task: {"provider": row.provider, "model": row.model} for row in rows}


@app.put("/api/models")
def put_models(payload: ModelSettingsPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can change model settings")
    choices = payload.model_dump()
    for choice in choices.values():
        registered = db.scalar(select(RegisteredModel.id).where(
            RegisteredModel.provider == choice["provider"], RegisteredModel.model == choice["model"],
        ))
        if not registered:
            raise HTTPException(status_code=422, detail=f"Model {choice['provider']}/{choice['model']} is not registered")
    for task, choice in choices.items():
        row = db.get(ModelSetting, task) or ModelSetting(
            task=task, provider="ollama", model="qwen3.5:4b-q4_K_M",
        )
        row.provider = choice["provider"]
        row.model = choice["model"]
        db.add(row)
    db.commit()
    return payload.model_dump()


@app.get("/api/registered-models", response_model=list[RegisteredModelOut])
def registered_models(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[RegisteredModel]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage registered models")
    return list(db.scalars(select(RegisteredModel).order_by(RegisteredModel.name)).all())


@app.get("/api/provider-models/{provider}")
async def provider_models(provider: str, user: User = Depends(current_user)) -> dict[str, list[str] | str]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can discover provider models")
    if provider not in {"ollama", "openai", "anthropic"}:
        raise HTTPException(status_code=404, detail="Unsupported provider")
    try:
        models = await ModelGateway(get_settings()).list_models(provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch models from {provider}") from exc
    return {"provider": provider, "models": models}


@app.post("/api/registered-models", response_model=RegisteredModelOut, status_code=201)
async def register_model(
    payload: RegisteredModelCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> RegisteredModel:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage registered models")
    try:
        available_models = await ModelGateway(get_settings()).list_models(payload.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch models from {payload.provider}") from exc
    if payload.model not in available_models:
        raise HTTPException(status_code=422, detail="Model is not available from the selected provider")
    registered = RegisteredModel(**payload.model_dump())
    db.add(registered)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Model name or provider/model is already registered") from exc
    db.refresh(registered)
    return registered


@app.delete("/api/registered-models/{model_id}")
def delete_registered_model(
    model_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage registered models")
    registered = db.get(RegisteredModel, model_id)
    if not registered:
        raise HTTPException(status_code=404, detail="Registered model not found")
    in_use = db.scalar(select(ModelSetting.task).where(
        ModelSetting.provider == registered.provider, ModelSetting.model == registered.model,
    ))
    if in_use:
        raise HTTPException(status_code=409, detail=f"Model is currently assigned to {in_use}")
    db.delete(registered)
    db.commit()
    return {"deleted": model_id}


@app.get("/api/documents", response_model=list[DocumentOut])
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[DocumentOut]:
    require_knowledge_access(user)
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
    require_knowledge_access(user)
    if visibility not in {"internal", "region"}:
        raise HTTPException(status_code=422, detail="Invalid visibility")
    if visibility == "region" and not region:
        raise HTTPException(status_code=422, detail="Region is required")
    if visibility == "region" and region not in DEMO_REGIONS:
        raise HTTPException(status_code=422, detail="Invalid region")
    if visibility == "internal":
        region = None
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
