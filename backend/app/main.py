from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_session, current_user
from app.core.config import get_settings
from app.database import Base, engine, get_db
from app.models import Conversation, Document, DocumentPage, Message, User

settings = get_settings()
password_hash = PasswordHash.recommended()
app = FastAPI(title="EduTool API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    document_id: int | None = None
    page_number: int | None = Field(default=None, ge=1)
    conversation_id: int | None = None

@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(engine)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/v1/config/status")
def config_status() -> dict[str, int | bool]:
    return {
        "llm_configured": bool(settings.openrouter_keys),
        "configured_key_count": len(settings.openrouter_keys),
    }

@app.post("/api/v1/auth/register", status_code=201)
def register(data: Credentials, response: Response, db: Session = Depends(get_db)) -> dict:
    username = data.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Username already exists")
    user = User(username=username, password_hash=password_hash.hash(data.password))
    db.add(user)
    db.commit()
    create_session(response, user)
    return {"id": user.id, "username": user.username}

@app.post("/api/v1/auth/login")
def login(data: Credentials, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == data.username.lower()))
    if not user or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    create_session(response, user)
    return {"id": user.id, "username": user.username}

@app.post("/api/v1/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie("edutool_session")

@app.get("/api/v1/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username}

@app.get("/api/v1/documents")
def documents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())).all()
    return [{"id": row.id, "title": row.title, "filename": row.filename, "page_count": row.page_count, "created_at": row.created_at} for row in rows]

@app.post("/api/v1/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if file.content_type != "application/pdf" or not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Only PDF files are supported in this release")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds the 25 MB limit")
    try:
        reader = PdfReader(BytesIO(content))
        texts = [(item.extract_text() or "").strip() for item in reader.pages]
    except Exception as exc:
        raise HTTPException(422, "The PDF could not be read") from exc
    document = Document(user_id=user.id, title=Path(file.filename).stem, filename=file.filename, page_count=len(texts))
    db.add(document)
    db.flush()
    db.add_all([DocumentPage(document_id=document.id, page_number=index, text=text) for index, text in enumerate(texts, 1)])
    Path(settings.upload_dir, f"{user.id}-{document.id}.pdf").write_bytes(content)
    db.commit()
    return {"id": document.id, "title": document.title, "filename": document.filename, "page_count": document.page_count}

@app.get("/api/v1/documents/{document_id}")
def document_detail(document_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    document = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user.id))
    if not document:
        raise HTTPException(404, "Document not found")
    pages = db.scalars(select(DocumentPage).where(DocumentPage.document_id == document.id).order_by(DocumentPage.page_number)).all()
    return {"id": document.id, "title": document.title, "filename": document.filename, "page_count": document.page_count, "pages": [{"page_number": item.page_number, "text": item.text} for item in pages]}

@app.get("/api/v1/conversations")
def conversations(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())).all()
    return [{"id": row.id, "title": row.title, "document_id": row.document_id, "updated_at": row.updated_at} for row in rows]

@app.get("/api/v1/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at)).all()
    return {"id": conversation.id, "title": conversation.title, "messages": [{"role": item.role, "content": item.content} for item in messages]}

@app.post("/api/v1/chat")
async def chat(data: ChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    document = None
    context = ""
    if data.document_id:
        document = db.scalar(select(Document).where(Document.id == data.document_id, Document.user_id == user.id))
        if not document:
            raise HTTPException(404, "Document not found")
        page_query = select(DocumentPage).where(DocumentPage.document_id == document.id)
        if data.page_number is not None:
            page_query = page_query.where(DocumentPage.page_number == data.page_number)
        pages = db.scalars(page_query.order_by(DocumentPage.page_number)).all()
        if data.page_number is not None and not pages:
            raise HTTPException(404, "Document page not found")
        context = "\n\n".join(f"[Page {item.page_number}] {item.text}" for item in pages)[:30000]
    conversation = db.scalar(select(Conversation).where(Conversation.id == data.conversation_id, Conversation.user_id == user.id)) if data.conversation_id else None
    if not conversation:
        conversation = Conversation(user_id=user.id, document_id=document.id if document else None, title=data.content[:80])
        db.add(conversation)
        db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content=data.content))
    if settings.openrouter_keys:
        scope = f"page {data.page_number}" if data.page_number is not None else "document"
        system = f"Use only the supplied {scope} material. If insufficient, say so. Never add facts outside the supplied material.\n\n{context}"
        provider_errors: list[str] = []
        async with httpx.AsyncClient(timeout=45) as client:
            provider = None
            for api_key in settings.openrouter_keys:
                try:
                    candidate = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={"model": settings.openrouter_model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": data.content}], "max_tokens": 1000},
                    )
                except httpx.RequestError as exc:
                    provider_errors.append(type(exc).__name__)
                    continue
                if candidate.is_success:
                    provider = candidate
                    break
                try:
                    message = candidate.json().get("error", {}).get("message", "Provider error")
                except Exception:
                    message = "Provider error"
                provider_errors.append(f"HTTP {candidate.status_code}: {message[:180]}")
                if candidate.status_code not in {401, 402, 403, 408, 429, 500, 502, 503, 504}:
                    raise HTTPException(502, "The AI provider rejected the request")
        if provider is None:
            detail = provider_errors[-1] if provider_errors else "No provider response"
            raise HTTPException(503, f"The AI provider is temporarily unavailable ({detail})")
        reply = provider.json()["choices"][0]["message"]["content"]
    else:
        reply = "AI is not configured yet. Add a new OpenRouter key to OPENROUTER_API_KEYS in backend/.env."
    db.add(Message(conversation_id=conversation.id, role="assistant", content=reply))
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"conversation_id": conversation.id, "reply": reply}