import re
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.api.chat import authorized_domain, resolve_domain
from app.api.errors import to_http_error
from app.core.auth import admin_user, current_user
from app.core.config import get_settings
from app.rag.registry import DEFAULT_DOMAIN, Domain
from app.services.documents import PUBLIC_ACCESS, list_documents
from app.services.ingestion import SUPPORTED, delete_document, ingest_file
from app.services.users import User

router = APIRouter(prefix="/api", tags=["documents"])

settings = get_settings()

GROUP_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def parse_access(access: str) -> list[str]:
    """'hr-managers, legal' -> ['hr-managers', 'legal']; empty -> everyone."""
    groups = sorted({g.strip().lower() for g in access.split(",") if g.strip()})
    if not groups:
        return PUBLIC_ACCESS
    invalid = [g for g in groups if not GROUP_PATTERN.match(g)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid group name: {', '.join(invalid)}")
    return groups


async def run_ingest(domain: Domain, file: UploadFile, access: str):
    groups = parse_access(access)
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Supported: {', '.join(sorted(SUPPORTED))}")
    upload_dir = Path(settings.upload_dir) / domain.name
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / filename
    dest.write_bytes(await file.read())
    try:
        chunks = ingest_file(dest, domain.name, domain.namespace, groups)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise to_http_error(exc, "Indexing") from exc
    return {"message": "Document indexed", "domain": domain.name, "file": filename,
            "chunks": chunks, "access": groups}


@router.post("/ingest/{domain}")
async def ingest(domain: str, file: UploadFile = File(...), access: str = Form(default=""),
                 _: User = Depends(admin_user)):
    """Admins only. `access`: comma-separated groups allowed to retrieve it; empty = everyone."""
    return await run_ingest(resolve_domain(domain), file, access)


@router.post("/ingest", include_in_schema=False)
async def ingest_default(file: UploadFile = File(...), access: str = Form(default=""),
                         _: User = Depends(admin_user)):
    """Backward-compatible alias for the default domain."""
    return await run_ingest(resolve_domain(DEFAULT_DOMAIN), file, access)


@router.get("/documents/{domain}")
def documents(domain: str, user: User = Depends(current_user)):
    """The documents this user may retrieve: restricted files stay invisible to the others."""
    d = authorized_domain(domain, user)
    return {"domain": d.name, "documents": list_documents(d.name, user.access_groups)}


@router.delete("/documents/{domain}/{filename}")
def remove_document(domain: str, filename: str, _: User = Depends(admin_user)):
    d = resolve_domain(domain)
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid file name")
    try:
        delete_document(d.name, filename, d.namespace)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Document not found: {filename}")
    except Exception as exc:
        raise to_http_error(exc, "Deleting document") from exc
    return {"deleted": True, "domain": d.name, "file": filename}
