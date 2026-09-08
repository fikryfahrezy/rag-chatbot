import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ModelSetting
from .operations import answer_operation, answer_public_catalog
from .providers import ModelGateway
from .retrieval import retrieve
from .schemas import ChatRequest, ChatResponse, Citation, User


SYSTEM = "Jawab dalam Bahasa Indonesia. Gunakan hanya konteks yang diberikan. Jika tidak ada jawabannya, katakan tidak ditemukan. Jangan mengarang."


@dataclass
class PreparedChat:
    provider: str
    model: str
    route: str
    citations: list[Citation]
    system: str = ""
    prompt: str = ""
    direct_answer: str | None = None


def model_setting(session: Session, task: str) -> ModelSetting:
    return session.get(ModelSetting, task) or ModelSetting(
        task=task, provider="ollama", model="qwen3.5:4b-q4_K_M",
    )


async def prepare_chat(session: Session, request: ChatRequest, user: User) -> PreparedChat:
    if request.workspace == "operations":
        planner = model_setting(session, "database_planner")
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
        return PreparedChat(
            provider=setting.provider,
            model=setting.model,
            route=result.route,
            citations=result.citations,
            system=SYSTEM,
            prompt=f"Pertanyaan: {request.message}\nData terotorisasi: {result.answer}",
        )

    if request.workspace == "public":
        catalog = answer_public_catalog(session, request.message)
        if catalog:
            return PreparedChat(
                direct_answer=catalog.answer, citations=catalog.citations, provider="policy",
                model="public-projection", route=catalog.route,
            )
        return PreparedChat(
            direct_answer="Informasi tersebut tidak tersedia pada data publik.", citations=[],
            provider="policy", model="public-projection", route="public_catalog",
        )

    chunks = retrieve(session, request.message, user)
    setting = model_setting(session, "pdf_answer")
    if not chunks:
        return PreparedChat(
            direct_answer="Informasi tersebut tidak ditemukan pada dokumen yang boleh Anda akses.", citations=[],
            provider=setting.provider, model=setting.model, route="pdf",
        )
    context = "\n\n".join(f"[{doc.filename}, hal. {chunk.page}] {chunk.content}" for chunk, doc in chunks)
    citations = [Citation(label=doc.filename, detail=f"halaman {chunk.page}") for chunk, doc in chunks]
    return PreparedChat(
        provider=setting.provider,
        model=setting.model,
        route="pdf",
        citations=citations,
        system=SYSTEM,
        prompt=f"Pertanyaan: {request.message}\n\nKonteks:\n{context}",
    )


async def answer_chat(session: Session, request: ChatRequest, user: User) -> ChatResponse:
    prepared = await prepare_chat(session, request, user)
    if prepared.direct_answer is not None:
        answer = prepared.direct_answer
    else:
        completion = await ModelGateway(get_settings()).complete(
            prepared.provider, prepared.model, prepared.system, prepared.prompt,
        )
        answer = completion.text
    return ChatResponse(
        answer=answer,
        citations=prepared.citations,
        provider=prepared.provider,
        model=prepared.model,
        route=prepared.route,
    )


async def stream_prepared_chat(prepared: PreparedChat) -> AsyncIterator[dict]:
    if prepared.direct_answer is not None:
        yield {"type": "delta", "delta": prepared.direct_answer}
    else:
        async for delta in ModelGateway(get_settings()).stream(
            prepared.provider, prepared.model, prepared.system, prepared.prompt,
        ):
            yield {"type": "delta", "delta": delta}
    yield {
        "type": "done",
        "citations": [citation.model_dump() for citation in prepared.citations],
        "provider": prepared.provider,
        "model": prepared.model,
        "route": prepared.route,
    }
