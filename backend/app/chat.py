import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ModelSetting
from .operations import answer_operation, answer_public_catalog
from .providers import ModelGateway
from .retrieval import retrieve
from .schemas import ChatRequest, ChatResponse, Citation, User


SYSTEM = "Jawab dalam Bahasa Indonesia. Gunakan hanya konteks yang diberikan. Jika tidak ada jawabannya, katakan tidak ditemukan. Jangan mengarang."


def model_setting(session: Session, task: str) -> ModelSetting:
    return session.get(ModelSetting, task) or ModelSetting(task=task, provider="demo", model="fallback")


async def answer_chat(session: Session, request: ChatRequest, user: User) -> ChatResponse:
    if request.workspace == "operations":
        planner = model_setting(session, "database_planner")
        route_hint = None
        if planner.provider != "demo":
            completion = await ModelGateway(get_settings()).complete(
                planner.provider, planner.model,
                "Return only JSON. Choose one allowed tool; never produce SQL.",
                f'Classify this Indonesian request: {request.message}\n'
                'Return {"tool":"order|commission|inventory"}.',
            )
            try:
                candidate = json.loads(completion.text).get("tool")
                route_hint = candidate if candidate in {"order", "commission", "inventory"} else None
            except (json.JSONDecodeError, AttributeError):
                route_hint = None
        result = answer_operation(session, request.message, user, route_hint)
        setting = model_setting(session, "database_answer")
        if setting.provider == "demo":
            answer = result.answer
        else:
            completion = await ModelGateway(get_settings()).complete(
                setting.provider, setting.model, SYSTEM,
                f"Pertanyaan: {request.message}\nData terotorisasi: {result.answer}",
            )
            answer = completion.text
        return ChatResponse(answer=answer, citations=result.citations, provider=setting.provider, model=setting.model, route=result.route)

    public_only = request.workspace == "public"
    if public_only:
        catalog = answer_public_catalog(session, request.message)
        if catalog:
            setting = model_setting(session, "database_answer")
            return ChatResponse(
                answer=catalog.answer, citations=catalog.citations, provider="policy",
                model="public-projection", route=catalog.route,
            )
    chunks = retrieve(session, request.message, user, public_only)
    setting = model_setting(session, "pdf_answer")
    if not chunks:
        return ChatResponse(
            answer="Informasi tersebut tidak ditemukan pada dokumen yang boleh Anda akses.",
            provider=setting.provider, model=setting.model, route="pdf",
        )
    context = "\n\n".join(f"[{doc.filename}, hal. {chunk.page}] {chunk.content}" for chunk, doc in chunks)
    citations = [Citation(label=doc.filename, detail=f"halaman {chunk.page}") for chunk, doc in chunks]
    if setting.provider == "demo":
        answer = "Berikut bagian dokumen yang paling relevan:\n\n" + chunks[0][0].content
    else:
        completion = await ModelGateway(get_settings()).complete(
            setting.provider, setting.model, SYSTEM,
            f"Pertanyaan: {request.message}\n\nKonteks:\n{context}",
        )
        answer = completion.text
    return ChatResponse(answer=answer, citations=citations, provider=setting.provider, model=setting.model, route="pdf")
