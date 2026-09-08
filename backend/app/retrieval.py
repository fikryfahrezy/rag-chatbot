import re
from collections import Counter

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Document, DocumentChunk
from .policies import scope_documents
from .schemas import User


TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


def split_text(text: str, size: int = 1100, overlap: int = 150) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    return [clean[start:start + size] for start in range(0, len(clean), size - overlap)]


def ingest_pdf(session: Session, path: str, filename: str, visibility: str, region: str | None, user: User) -> Document:
    reader = PdfReader(path)
    doc = Document(filename=filename, visibility=visibility, region=region, uploaded_by=user.id)
    session.add(doc)
    session.flush()
    for page_no, page in enumerate(reader.pages, start=1):
        for chunk in split_text(page.extract_text() or ""):
            session.add(DocumentChunk(document_id=doc.id, page=page_no, content=chunk))
    session.commit()
    session.refresh(doc)
    return doc


def _score(query: str, content: str) -> float:
    query_terms = Counter(t.lower() for t in TOKEN_RE.findall(query) if len(t) > 2)
    doc_terms = Counter(t.lower() for t in TOKEN_RE.findall(content))
    return sum(min(count, doc_terms[term]) for term, count in query_terms.items())


def retrieve(session: Session, query: str, user: User, public_only: bool, limit: int = 5) -> list[tuple[DocumentChunk, Document]]:
    allowed_docs = scope_documents(select(Document.id), user, public_only)
    rows = session.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.id.in_(allowed_docs))
    ).all()
    ranked = sorted(rows, key=lambda row: _score(query, row[0].content), reverse=True)
    return [row for row in ranked if _score(query, row[0].content) > 0][:limit]

