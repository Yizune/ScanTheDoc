from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import uuid4

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import func, select

from app.auth import PUBLIC_WORKSPACE_ID
from app.config import get_settings
from app.database import SessionLocal, engine
from app.job_errors import job_failure_message
from app.models import Account, Document, DocumentStatus, JobStatus, ProcessingJob
from app.services.documents import (
    compare_pdf_documents,
    extract_document,
    extract_pdf_pages,
    merge_pdfs,
    split_pdf,
)
from app.services.storage import DocumentStorage

settings = get_settings()
logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    storage = DocumentStorage(settings)
    await asyncio.to_thread(storage.initialize)
    ctx["storage"] = storage


async def shutdown(ctx: dict) -> None:
    await engine.dispose()


async def run_job(ctx: dict, job_id: str) -> None:
    storage: DocumentStorage = ctx["storage"]
    async with SessionLocal() as session:
        job = await session.get(ProcessingJob, job_id)
        if job is None or job.status != JobStatus.QUEUED:
            return
        job.status = JobStatus.PROCESSING
        await session.commit()
        try:
            documents = list(
                (
                    await session.execute(
                        select(Document).where(Document.id.in_(job.source_document_ids))
                    )
                ).scalars()
            )
            ordered = {item.id: item for item in documents}
            sources = [ordered[item_id] for item_id in job.source_document_ids]
            if job.operation == "extract":
                await _extract(storage, sources[0])
            elif job.operation == "merge":
                await _merge(storage, sources, job, session)
            elif job.operation == "compare":
                original, compared = await asyncio.gather(
                    asyncio.to_thread(storage.get, sources[0].storage_key),
                    asyncio.to_thread(storage.get, sources[1].storage_key),
                )
                job.result_data = await asyncio.to_thread(
                    compare_pdf_documents,
                    original,
                    compared,
                    settings.tesseract_cmd,
                )
            elif job.operation == "extract_pages":
                await _extract_pages(storage, sources[0], job, session)
            elif job.operation == "split":
                await _split(storage, sources[0], job, session)
            else:
                raise ValueError("Unknown document operation")
            job.status = JobStatus.COMPLETED
        except Exception:
            error_message = job_failure_message(job.operation)
            logger.exception(
                "Document job failed: job_id=%s operation=%s", job.id, job.operation
            )
            job.status = JobStatus.FAILED
            job.error_message = error_message
            for document in documents if "documents" in locals() else []:
                if job.operation == "extract":
                    document.status = DocumentStatus.FAILED
                    document.error_message = error_message
        await session.commit()


async def _extract(storage: DocumentStorage, document: Document) -> None:
    document.status = DocumentStatus.PROCESSING
    data = await asyncio.to_thread(storage.get, document.storage_key)
    extracted = await asyncio.to_thread(
        extract_document, data, document.media_type, settings.tesseract_cmd
    )
    document.extracted_text = extracted.text
    document.page_count = extracted.page_count
    document.status = DocumentStatus.READY
    document.processed_at = datetime.now(UTC)
    document.error_message = None


async def _merge(
    storage: DocumentStorage,
    documents: list[Document],
    job: ProcessingJob,
    session,
) -> None:
    data = [
        await asyncio.to_thread(storage.get, item.storage_key) for item in documents
    ]
    merged = await asyncio.to_thread(merge_pdfs, data)
    name = (job.result_data or {}).get("name", "Merged document")
    extracted_text = "\n\n".join(
        item.extracted_text for item in documents if item.extracted_text
    )
    page_count = sum(item.page_count or 0 for item in documents)
    job.result_document_id = await _create_result(
        storage,
        merged,
        name,
        job,
        session,
        extracted_text,
        page_count,
    )


async def _extract_pages(
    storage: DocumentStorage,
    source: Document,
    job: ProcessingJob,
    session,
) -> None:
    options = job.result_data or {}
    pages = options.get("pages", [])
    data = await asyncio.to_thread(storage.get, source.storage_key)
    result = await asyncio.to_thread(extract_pdf_pages, data, pages)
    extracted = await asyncio.to_thread(
        extract_document, result, "application/pdf", settings.tesseract_cmd
    )
    job.result_document_id = await _create_result(
        storage,
        result,
        options.get("name", f"{source.name} pages"),
        job,
        session,
        extracted.text,
        extracted.page_count,
    )


async def _split(
    storage: DocumentStorage,
    source: Document,
    job: ProcessingJob,
    session,
) -> None:
    data = await asyncio.to_thread(storage.get, source.storage_key)
    parts = await asyncio.to_thread(split_pdf, data)
    result_ids = []

    for page_number, part in enumerate(parts, start=1):
        extracted = await asyncio.to_thread(
            extract_document, part, "application/pdf", settings.tesseract_cmd
        )
        result_ids.append(
            await _create_result(
                storage,
                part,
                f"{source.name} - page {page_number}",
                job,
                session,
                extracted.text,
                1,
            )
        )

    job.result_document_id = result_ids[0]
    job.result_data = {"result_document_ids": result_ids}


async def _create_result(
    storage: DocumentStorage,
    data: bytes,
    name: str,
    job: ProcessingJob,
    session,
    extracted_text: str,
    page_count: int | None,
) -> str:
    if job.owner_id == PUBLIC_WORKSPACE_ID:
        await session.execute(
            select(Account.clerk_user_id)
            .where(Account.clerk_user_id == job.owner_id)
            .with_for_update()
        )
        used = await session.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.owner_id == job.owner_id
            )
        )
        limit = settings.public_storage_mb * 1024 * 1024
        if int(used or 0) + len(data) > limit:
            raise ValueError("The public workspace is full")

    document_id = str(uuid4())
    document = Document(
        id=document_id,
        owner_id=job.owner_id,
        name=name[:255],
        original_filename=f"{name[:240]}.pdf",
        media_type="application/pdf",
        size_bytes=len(data),
        storage_key=f"{job.owner_id}/{document_id}/result.pdf",
        status=DocumentStatus.READY,
        extracted_text=extracted_text,
        page_count=page_count,
        processed_at=datetime.now(UTC),
    )
    session.add(document)
    await session.flush()
    await asyncio.to_thread(
        storage.put, document.storage_key, data, document.media_type
    )
    return document.id


async def cleanup_expired_documents(ctx: dict) -> None:
    storage: DocumentStorage = ctx["storage"]
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        accounts = list((await session.execute(select(Account))).scalars())
        for account in accounts:
            if account.clerk_user_id == PUBLIC_WORKSPACE_ID:
                continue

            cutoff = now - timedelta(days=account.retention_days)
            documents = list(
                (
                    await session.execute(
                        select(Document).where(
                            Document.owner_id == account.clerk_user_id,
                            Document.created_at < cutoff,
                        )
                    )
                ).scalars()
            )
            for document in documents:
                await asyncio.to_thread(storage.delete, document.storage_key)
                await session.delete(document)
        await session.commit()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions: ClassVar[list] = [run_job]
    cron_jobs: ClassVar[list] = [
        cron(cleanup_expired_documents, minute={0, 15, 30, 45})
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 300
