import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfReader, PdfWriter
from starlette.requests import Request

from app.config import Settings
from app.models import ProcessingJob
from app.routers.api import enforce_public_rate_limit, enqueue_processing_job
from app.services.documents import (
    merge_pdfs,
    parse_page_selection,
    split_pdf,
    validate_upload,
)
from app.services.storage import DocumentStorage


class FakeRedis:
    def __init__(self):
        self.count = 0
        self.expiry = None

    async def incr(self, key):
        self.count += 1
        return self.count

    async def expire(self, key, seconds):
        self.expiry = seconds


class FailingRedis(FakeRedis):
    async def enqueue_job(self, *args, **kwargs):
        raise ConnectionError("Redis is unavailable")


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.statements = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, statement):
        self.statements += 1


def make_request(redis):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/documents",
            "headers": [],
            "client": ("203.0.113.10", 5000),
            "server": ("testserver", 80),
            "scheme": "http",
            "app": SimpleNamespace(state=SimpleNamespace(redis=redis)),
        }
    )


def make_pdf(page_count):
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=300, height=400)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_page_selection_accepts_pages_and_ranges():
    assert parse_page_selection("1, 3-5, 3", 6) == [1, 3, 4, 5]


def test_page_selection_rejects_pages_outside_the_pdf():
    with pytest.raises(ValueError, match="outside this 3-page PDF"):
        parse_page_selection("4", 3)


def test_upload_validation_uses_the_file_contents():
    image_data = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(image_data, format="PNG")

    assert validate_upload(b"%PDF-1.7\n", "text/plain") == "application/pdf"
    assert validate_upload(image_data.getvalue(), "text/plain") == "image/png"

    with pytest.raises(ValueError, match="valid PDF and image"):
        validate_upload(b"not a document", "application/pdf")


def test_pdf_merge_and_split_keep_the_expected_pages():
    merged = merge_pdfs([make_pdf(1), make_pdf(2)])
    assert len(PdfReader(io.BytesIO(merged)).pages) == 3

    parts = split_pdf(merged)
    assert len(parts) == 3
    assert all(len(PdfReader(io.BytesIO(part)).pages) == 1 for part in parts)


def test_local_storage_can_put_get_and_delete(tmp_path):
    settings = Settings(_env_file=None, local_storage_path=str(tmp_path))
    storage = DocumentStorage(settings)
    storage.initialize()

    storage.put("public/example.txt", b"hello", "text/plain")
    assert storage.get("public/example.txt") == b"hello"

    storage.delete("public/example.txt")
    assert not (tmp_path / "public" / "example.txt").exists()


def test_local_storage_rejects_paths_outside_its_folder(tmp_path):
    storage = DocumentStorage(
        Settings(_env_file=None, local_storage_path=str(tmp_path))
    )

    with pytest.raises(ValueError, match="Invalid storage key"):
        storage.put("../outside.txt", b"no", "text/plain")


def test_public_workspace_rate_limit():
    redis = FakeRedis()
    request = make_request(redis)
    settings = Settings(_env_file=None, public_operations_per_hour=2)

    asyncio.run(enforce_public_rate_limit(request, "public", settings))
    asyncio.run(enforce_public_rate_limit(request, "public", settings))

    with pytest.raises(HTTPException) as error:
        asyncio.run(enforce_public_rate_limit(request, "public", settings))

    assert error.value.status_code == 429
    assert redis.expiry == 3600


def test_signed_in_users_do_not_use_the_public_rate_limit():
    redis = FakeRedis()
    request = make_request(redis)
    settings = Settings(_env_file=None, public_operations_per_hour=1)

    asyncio.run(enforce_public_rate_limit(request, "user_123", settings))

    assert redis.count == 0


def test_failed_queue_request_removes_the_database_job():
    request = make_request(FailingRedis())
    settings = Settings(_env_file=None)
    session = FakeSession()
    job = ProcessingJob(
        id="job-123",
        owner_id="public",
        operation="extract",
        source_document_ids=["document-123"],
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(enqueue_processing_job(request, settings, session, job))

    assert error.value.status_code == 503
    assert session.rollbacks == 1
    assert session.statements == 1
    assert session.commits == 1
