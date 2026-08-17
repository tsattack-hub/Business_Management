"""
구매규격서 생성 API

  · item-groups : 품목군 목록 + 규격 입력항목 + 필수확인 (선택·입력 UI 용)
  · draft       : 품목군·규격 수치로 규격서 초안을 조립해 JSON 미리보기 반환
                  (조항 본문 · 채워야 할 빈칸 · 특정회사 규격 경고 포함)
  · document    : 위 초안을 .hwpx 파일로 만들어 내려받기

규정값은 코드에 없다. 조항·품목군·브랜드 목록은 docs/spec_clauses.yaml 에 있다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, JSONResponse

from ..services import specgen, store

router = APIRouter(prefix="/api/specgen", tags=["specgen"])


# ---------------------------------------------------------------- 직렬화
def _field_dict(f: dict) -> dict[str, Any]:
    return {
        "key": f.get("key"),
        "unit": f.get("단위", ""),
        "hint": f.get("힌트", ""),
        "required": bool(f.get("필수", False)),
    }


def _clause_dict(c: specgen.Clause) -> dict[str, Any]:
    return {
        "id": c.id,
        "title": c.title,
        "source": c.source,
        "note": c.note,
        "body": c.body,
        "audits": c.audits,
    }


def _hit_dict(h: specgen.BrandHit) -> dict[str, Any]:
    return {
        "term": h.term,
        "kind": h.kind,
        "where": h.where,
        "line": h.line,
        "mitigated": h.mitigated,
    }


def _draft_dict(draft: specgen.SpecDraft) -> dict[str, Any]:
    return {
        "itemGroup": draft.item_group,
        "sections": [
            {"num": num, "name": name, "clauses": [_clause_dict(c) for c in clauses]}
            for num, name, clauses in draft.sections
        ],
        "blanks": [{"where": where, "field": field} for where, field in draft.blanks],
        "brandHits": [_hit_dict(h) for h in draft.brand_hits],
        "mustCheck": draft.must_check,
        "sourceCounts": draft.source_counts,
        "clauseCount": draft.clause_count,
        "text": specgen.to_text(draft),
    }


# ---------------------------------------------------------------- 엔드포인트
@router.get("/item-groups")
def item_groups():
    """품목군 목록. 각 품목군의 규격 입력항목과 필수확인 사항을 함께 준다."""
    return {
        "groups": [
            {
                "id": g.id,
                "name": g.name,
                "specFields": [_field_dict(f) for f in g.spec_fields],
                "mustCheck": g.must_check,
            }
            for g in specgen.item_groups()
        ]
    }


@router.post("/draft")
def build_draft(
    group_id: str = Body(..., embed=True),
    project: dict[str, Any] = Body(..., embed=True),
    spec_values: dict[str, str] = Body(default={}, embed=True),
):
    """품목군·규격 수치로 초안을 조립해 미리보기 JSON을 반환한다."""
    try:
        draft = specgen.build_draft(group_id, project, spec_values)
    except Exception as e:  # noqa: BLE001 - 사용자에게 사유 전달
        return JSONResponse(status_code=400, content={"detail": f"초안 생성 실패: {e}"})
    return _draft_dict(draft)


@router.post("/document")
def render_document(
    group_id: str = Body(..., embed=True),
    project: dict[str, Any] = Body(..., embed=True),
    spec_values: dict[str, str] = Body(default={}, embed=True),
):
    """초안을 .hwpx 파일로 만들어 내려받는다."""
    out_root = store.out_dir(project)
    try:
        draft = specgen.build_draft(group_id, project, spec_values)
        path = specgen.render(draft, project, out_root)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"detail": f"규격서 생성 실패: {e}"})
    return _file_download(path)


def _file_download(path: Path) -> FileResponse:
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
