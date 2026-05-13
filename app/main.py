from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.citation_cleaner import PDFCleaningError, clean_pdf_bytes

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _safe_download_name(filename: str) -> str:
    stem = Path(filename or "document.pdf").stem
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    if not sanitized:
        sanitized = "document"
    return f"{sanitized[:80]}-cleaned.pdf"


def _render_home(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "max_upload_mb": settings.max_upload_mb,
            "error": error,
        },
    )


def _validate_pdf_upload(upload: UploadFile, pdf_bytes: bytes) -> None:
    filename = upload.filename or ""
    content_type = upload.content_type or ""
    accepted_types = {"application/pdf", "application/x-pdf"}

    if not filename.lower().endswith(".pdf"):
        raise PDFCleaningError("Please upload a file with a .pdf extension.")

    if content_type and content_type not in accepted_types:
        raise PDFCleaningError("The uploaded file does not look like a PDF.")

    max_size_bytes = settings.max_upload_mb * 1024 * 1024
    if len(pdf_bytes) > max_size_bytes:
        raise PDFCleaningError(
            f"PDFs larger than {settings.max_upload_mb} MB are not accepted."
        )

    if not pdf_bytes.startswith(b"%PDF"):
        raise PDFCleaningError("The uploaded file is missing a valid PDF signature.")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return _render_home(request)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process")
async def process_pdf(request: Request, file: UploadFile = File(...)) -> Response:
    try:
        pdf_bytes = await file.read()
        _validate_pdf_upload(file, pdf_bytes)
        cleaned_bytes = clean_pdf_bytes(pdf_bytes)
    except PDFCleaningError as exc:
        return _render_home(request, str(exc))
    finally:
        await file.close()

    headers = {
        "Content-Disposition": f'attachment; filename="{_safe_download_name(file.filename or "document.pdf")}"'
    }
    return Response(content=cleaned_bytes, media_type="application/pdf", headers=headers)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
