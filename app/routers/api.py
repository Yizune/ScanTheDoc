from __future__ import annotations

import asyncio
import io
import logging
import re
import tempfile
import zipfile
from datetime import UTC
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.auth import PUBLIC_WORKSPACE_ID, CurrentUser
from app.config import Settings, get_settings
from app.database import get_session
from app.job_errors import job_failure_message
from app.models import Account, Document, DocumentStatus, JobStatus, ProcessingJob
from app.schemas import (
    CompareRequest,
    DocumentSelectionRequest,
    ExtractPagesRequest,
    MergeRequest,
)
from app.services.documents import (
    normalize_text,
    parse_page_selection,
    render_pdf_page,
    validate_upload,
)
from app.services.storage import DocumentStorage

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)
Session = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
UploadedFile = Annotated[UploadFile, File()]


def safe_filename(filename: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._ -]", "_", filename)


def create_document_archive(
    storage: DocumentStorage, documents: list[Document]
) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temporary:
        archive = Path(temporary.name)
    used_names: set[str] = set()
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for document in documents:
                filename = safe_filename(document.original_filename)
                path = Path(filename)
                number = 2
                while filename.casefold() in used_names:
                    filename = f"{path.stem} ({number}){path.suffix}"
                    number += 1
                used_names.add(filename.casefold())
                output.writestr(filename, storage.get(document.storage_key))
        return archive
    except Exception:
        archive.unlink(missing_ok=True)
        raise


def document_json(document: Document, include_text: bool = False) -> dict:
    result = {
        "id": document.id,
        "name": document.name,
        "original_filename": document.original_filename,
        "media_type": document.media_type,
        "size_bytes": document.size_bytes,
        "status": document.status,
        "page_count": document.page_count,
        "error_message": "Text extraction failed."
        if document.status == DocumentStatus.FAILED
        else None,
        "created_at": document.created_at.replace(tzinfo=UTC)
        if document.created_at.tzinfo is None
        else document.created_at,
        "processed_at": document.processed_at,
    }
    if include_text:
        result["extracted_text"] = normalize_text(document.extracted_text or "")
    return result


def job_json(job: ProcessingJob) -> dict:
    return {
        "id": job.id,
        "operation": job.operation,
        "status": job.status,
        "result_document_id": job.result_document_id,
        "result_data": job.result_data,
        "error_message": job_failure_message(job.operation)
        if job.status == JobStatus.FAILED
        else None,
    }


async def ensure_account(
    session: AsyncSession, user_id: str, settings: Settings
) -> Account:
    account = await session.get(Account, user_id)
    if account is None:
        account = Account(
            clerk_user_id=user_id, retention_days=settings.default_retention_days
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
    return account


async def owned_document(
    session: AsyncSession, user_id: str, document_id: str
) -> Document:
    document = await session.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == user_id)
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def redis_from_app(request: Request, settings: Settings) -> ArqRedis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        request.app.state.redis = redis
    return redis


def storage_from_app(request: Request, settings: Settings) -> DocumentStorage:
    storage = getattr(request.app.state, "storage", None)
    if storage is None:
        storage = DocumentStorage(settings)
        storage.initialize()
        request.app.state.storage = storage
    return storage


async def enforce_public_rate_limit(
    request: Request,
    user_id: str,
    settings: Settings,
) -> None:
    if user_id != PUBLIC_WORKSPACE_ID:
        return

    redis = await redis_from_app(request, settings)
    client_ip = request.client.host if request.client else "unknown"
    key = f"public-operations:{client_ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)
    if count > settings.public_operations_per_hour:
        raise HTTPException(
            status_code=429,
            detail="Public workspace limit reached. Try again later.",
        )


async def enforce_public_storage_limit(
    session: AsyncSession,
    user_id: str,
    incoming_size: int,
    settings: Settings,
) -> None:
    if user_id != PUBLIC_WORKSPACE_ID:
        return

    await session.execute(
        select(Account.clerk_user_id)
        .where(Account.clerk_user_id == user_id)
        .with_for_update()
    )
    used = await session.scalar(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
            Document.owner_id == user_id
        )
    )
    limit = settings.public_storage_mb * 1024 * 1024
    if int(used or 0) + incoming_size > limit:
        raise HTTPException(status_code=413, detail="The public workspace is full.")


async def enqueue_processing_job(
    request: Request,
    settings: Settings,
    session: AsyncSession,
    job: ProcessingJob,
) -> None:
    try:
        redis = await redis_from_app(request, settings)
        queued = await redis.enqueue_job("run_job", job.id, _job_id=job.id)
        if queued is None:
            raise RuntimeError("The job was not queued")
    except Exception as error:
        await session.rollback()
        try:
            await session.execute(
                delete(ProcessingJob).where(ProcessingJob.id == job.id)
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Could not remove job after queue failure: job_id=%s", job.id
            )
        raise HTTPException(
            status_code=503,
            detail="Processing is temporarily unavailable. Try again.",
        ) from error


@router.post("/documents", status_code=202)
async def upload_document(
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
    file: UploadedFile,
):
    await enforce_public_rate_limit(request, user_id, settings)
    await ensure_account(session, user_id, settings)
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Files are limited to {settings.max_upload_mb} MB",
        )
    try:
        media_type = validate_upload(
            data, file.content_type or "application/octet-stream"
        )
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error

    await enforce_public_storage_limit(session, user_id, len(data), settings)

    document_id = str(uuid4())
    filename = Path(file.filename or "document").name[:255]
    suffix = Path(filename).suffix.lower()[:12]
    storage_key = f"{user_id}/{document_id}/source{suffix}"
    storage = storage_from_app(request, settings)
    document = Document(
        id=document_id,
        owner_id=user_id,
        name=Path(filename).stem[:255] or "Untitled document",
        original_filename=filename,
        media_type=media_type,
        size_bytes=len(data),
        storage_key=storage_key,
    )
    job = ProcessingJob(
        owner_id=user_id, operation="extract", source_document_ids=[document_id]
    )
    stored = False
    try:
        await asyncio.to_thread(storage.put, storage_key, data, media_type)
        stored = True
        session.add_all([document, job])
        await session.commit()
        await enqueue_processing_job(request, settings, session, job)
    except HTTPException:
        if stored:
            await asyncio.to_thread(storage.delete, storage_key)
        await session.execute(delete(Document).where(Document.id == document_id))
        await session.commit()
        raise
    except Exception as error:
        await session.rollback()
        if stored:
            await asyncio.to_thread(storage.delete, storage_key)
        raise HTTPException(
            status_code=503, detail="Upload failed. Try again."
        ) from error
    return {"document": document_json(document), "job": job_json(job)}


@router.get("/documents")
async def list_documents(
    user_id: CurrentUser,
    session: Session,
    q: str = Query(default="", max_length=200),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
):
    filters = [Document.owner_id == user_id]
    if status:
        filters.append(Document.status == status)
    if q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(Document.name.ilike(pattern), Document.extracted_text.ilike(pattern))
        )
    total = await session.scalar(select(func.count(Document.id)).where(*filters)) or 0
    documents = list(
        (
            await session.execute(
                select(Document)
                .where(*filters)
                .order_by(Document.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return {"items": [document_json(item) for item in documents], "total": total}


@router.get("/documents/{document_id}")
async def document_details(document_id: str, user_id: CurrentUser, session: Session):
    return document_json(
        await owned_document(session, user_id, document_id), include_text=True
    )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    document = await owned_document(session, user_id, document_id)
    storage = storage_from_app(request, settings)
    data = await asyncio.to_thread(storage.get, document.storage_key)
    filename = safe_filename(document.original_filename)
    return StreamingResponse(
        io.BytesIO(data),
        media_type=document.media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/documents/download")
async def download_documents(
    payload: DocumentSelectionRequest,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    documents = list(
        (
            await session.execute(
                select(Document).where(
                    Document.id.in_(payload.document_ids),
                    Document.owner_id == user_id,
                )
            )
        ).scalars()
    )
    if len(documents) != len(set(payload.document_ids)):
        raise HTTPException(
            status_code=404, detail="One or more documents were not found"
        )
    by_id = {document.id: document for document in documents}
    ordered = [by_id[document_id] for document_id in payload.document_ids]
    storage = storage_from_app(request, settings)
    archive = await asyncio.to_thread(create_document_archive, storage, ordered)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="ScanTheDoc documents.zip",
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    document = await owned_document(session, user_id, document_id)
    storage = storage_from_app(request, settings)
    await asyncio.to_thread(storage.delete, document.storage_key)
    await session.delete(document)
    await session.commit()
    return Response(status_code=204)


async def queue_tool_job(
    operation: str,
    document_ids: list[str],
    user_id: str,
    session: AsyncSession,
    request: Request,
    settings: Settings,
    result_data: dict | None = None,
) -> dict:
    documents = list(
        (
            await session.execute(
                select(Document).where(
                    Document.id.in_(document_ids), Document.owner_id == user_id
                )
            )
        ).scalars()
    )
    if len(documents) != len(set(document_ids)):
        raise HTTPException(
            status_code=404, detail="One or more documents were not found"
        )
    if any(item.status != DocumentStatus.READY for item in documents):
        raise HTTPException(
            status_code=409, detail="All documents must finish processing first"
        )
    if operation in {"merge", "compare", "extract_pages", "split"} and any(
        item.media_type != "application/pdf" for item in documents
    ):
        raise HTTPException(
            status_code=422, detail="This operation only supports PDF documents"
        )
    await enforce_public_rate_limit(request, user_id, settings)
    job = ProcessingJob(
        owner_id=user_id,
        operation=operation,
        source_document_ids=document_ids,
        result_data=result_data,
    )
    session.add(job)
    await session.commit()
    await enqueue_processing_job(request, settings, session, job)
    return job_json(job)


@router.post("/tools/merge", status_code=202)
async def merge_documents(
    payload: MergeRequest,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    return await queue_tool_job(
        "merge",
        payload.document_ids,
        user_id,
        session,
        request,
        settings,
        {"name": payload.name.strip()},
    )


@router.post("/tools/compare", status_code=202)
async def compare_documents(
    payload: CompareRequest,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    return await queue_tool_job(
        "compare", payload.document_ids, user_id, session, request, settings
    )


@router.get("/documents/{document_id}/pages/{page_number}/preview")
async def preview_document_page(
    document_id: str,
    page_number: int,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    document = await owned_document(session, user_id, document_id)
    if document.media_type != "application/pdf":
        raise HTTPException(
            status_code=422, detail="This operation only supports PDF documents"
        )
    storage = storage_from_app(request, settings)
    data = await asyncio.to_thread(storage.get, document.storage_key)
    try:
        preview = await asyncio.to_thread(render_pdf_page, data, page_number)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=preview,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/documents/{document_id}/extract-pages", status_code=202)
async def extract_pages(
    document_id: str,
    payload: ExtractPagesRequest,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    document = await owned_document(session, user_id, document_id)
    if document.page_count is None:
        raise HTTPException(status_code=409, detail="Page count is not available yet")
    try:
        pages = parse_page_selection(payload.pages, document.page_count)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return await queue_tool_job(
        "extract_pages",
        [document_id],
        user_id,
        session,
        request,
        settings,
        {"name": payload.name.strip(), "pages": pages},
    )


@router.post("/documents/{document_id}/split", status_code=202)
async def split_document(
    document_id: str,
    request: Request,
    user_id: CurrentUser,
    session: Session,
    settings: AppSettings,
):
    document = await owned_document(session, user_id, document_id)
    if document.page_count is None:
        raise HTTPException(status_code=409, detail="Page count is not available yet")
    if document.page_count < 2:
        raise HTTPException(status_code=422, detail="This PDF has only one page")
    return await queue_tool_job(
        "split", [document_id], user_id, session, request, settings
    )


@router.get("/jobs/{job_id}")
async def job_details(job_id: str, user_id: CurrentUser, session: Session):
    job = await session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.owner_id == user_id
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_json(job)
