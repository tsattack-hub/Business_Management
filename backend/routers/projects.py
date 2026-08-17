"""
사업 절차관리 API

  · 사업 CRUD (projects/*.json)
  · 분석: 계약유형 판정 + 조달 트랙 + 단계별 절차/서류
  · 서류 틀 생성 (단건 / 전체 zip)
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..services import docgen, store
from ..services.analysis import analyze

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects():
    return {"projects": [{"id": pid, "name": name} for pid, name in store.list_projects()]}


@router.get("/blank")
def blank_project():
    return store.blank()


@router.get("/{pid}")
def get_project(pid: str):
    proj = store.load(pid)
    if not proj:
        return JSONResponse(status_code=404, content={"detail": "사업을 찾을 수 없습니다."})
    return proj


@router.post("")
def save_project(project: dict[str, Any] = Body(...)):
    if not project.get("사업명"):
        return JSONResponse(status_code=400, content={"detail": "사업명을 입력하세요."})
    pid = store.save(project)
    return {"id": pid}


@router.delete("/{pid}")
def delete_project(pid: str):
    store.delete(pid)
    return {"ok": True}


@router.post("/analyze")
def analyze_project(project: dict[str, Any] = Body(...)):
    return analyze(project)


# ---------------------------------------------------------------- 서류 생성
@router.post("/document/{doc_id}")
def render_document(doc_id: str, project: dict[str, Any] = Body(...)):
    out_root = store.out_dir(project)
    try:
        path = docgen.render(doc_id, project, out_root)
    except Exception as e:  # noqa: BLE001 - 사용자에게 사유 전달
        return JSONResponse(status_code=400, content={"detail": f"{doc_id} 생성 실패: {e}"})
    return _file_download(path)


@router.post("/documents-zip")
def render_all(project: dict[str, Any] = Body(...)):
    out_root = store.out_dir(project)
    tpls = docgen.load_templates()
    made: list[Path] = []
    failed: list[str] = []
    for d in tpls.values():
        try:
            made.append(docgen.render(d.id, project, out_root))
        except Exception as e:  # noqa: BLE001
            failed.append(f"{d.name}: {e}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in made:
            z.write(p, arcname=p.name)
    buf.seek(0)

    fname = f"{store.slug(project.get('사업명', '') or '무제')}_서류틀.zip"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}",
        "X-Made-Count": str(len(made)),
        "X-Failed": quote("; ".join(failed)) if failed else "",
    }
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


def _file_download(path: Path) -> FileResponse:
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
    )
