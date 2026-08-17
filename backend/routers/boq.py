"""
내역서 검증 API

  · inspect : xlsx 업로드 → 시트/열 자동 인식 결과 (사용자 열 매핑 UI 용)
  · check   : 선택한 시트·열 매핑으로 소계·합계 검산(AUD-030) + 수량 대조(AUD-014)

기존 Streamlit 페이지(extra/1_내역서_검증.py)를 그대로 옮겼다.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from ..services import boq, verify

router = APIRouter(prefix="/api/boq", tags=["boq"])


def _default_index(names: list[str], keyword: str) -> int | None:
    return next((i for i, n in enumerate(names) if keyword in n), None)


@router.post("/inspect")
async def inspect(file: UploadFile = File(...)):
    data = await file.read()
    try:
        sheets = boq.read_workbook(data)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"detail": f"파일을 읽지 못했습니다: {e}"})
    if not sheets:
        return JSONResponse(status_code=400, content={"detail": "읽을 수 있는 시트가 없습니다."})

    names = [s.name for s in sheets]
    return {
        "sheets": [
            {
                "name": s.name,
                "headerRow": s.header_row,
                "nRows": s.n_rows,
                "columns": [
                    {"index": c.index, "letter": c.letter, "header": c.header, "guess": c.guess}
                    for c in s.columns
                ],
            }
            for s in sheets
        ],
        "defaults": {
            "boqIndex": _default_index(names, "내역") or 0,
            "qtyIndex": _default_index(names, "수량"),
        },
    }


def _issue_dict(i: verify.Issue) -> dict[str, Any]:
    return {
        "kind": i.kind,
        "where": i.where,
        "label": i.label,
        "expected": i.expected,
        "actual": i.actual,
        "diff": i.diff,
        "message": i.message,
    }


@router.post("/check")
async def check(
    file: UploadFile = File(...),
    boq_sheet: int = Form(...),
    qty_sheet: int = Form(-1),
    boq_map: str = Form(...),
    qty_map: str = Form("{}"),
):
    data = await file.read()
    try:
        sheets = boq.read_workbook(data)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"detail": f"파일을 읽지 못했습니다: {e}"})

    if not (0 <= boq_sheet < len(sheets)):
        return JSONResponse(status_code=400, content={"detail": "내역서 시트 선택이 올바르지 않습니다."})

    bmap = _parse_map(boq_map)
    qmap = _parse_map(qty_map)
    bs = sheets[boq_sheet]
    qs = sheets[qty_sheet] if 0 <= qty_sheet < len(sheets) else None

    brep = verify.check_boq(data, bs.name, bmap, bs.header_row)
    qrep = verify.check_quantity(bs, bmap, qs, qmap) if qs is not None else None
    findings = verify.to_findings(brep, qrep)

    return {
        "boq": {
            "issues": [_issue_dict(i) for i in brep.issues],
            "detailRows": brep.detail_rows,
            "subtotalRows": brep.subtotal_rows,
            "checked": brep.checked,
            "notes": brep.notes,
        },
        "qty": None if qrep is None else {
            "issues": [_issue_dict(i) for i in qrep.issues],
            "matched": qrep.matched,
            "boqItems": qrep.boq_items,
            "qtyItems": qrep.qty_items,
        },
        "findings": [
            {
                "ruleId": f.rule_id,
                "name": f.name,
                "severity": f.severity,
                "passed": f.passed,
                "message": f.message,
                "citation": f.citation,
                "status": f.status,
                "detail": f.detail,
            }
            for f in findings
        ],
    }


def _parse_map(raw: str) -> dict[str, int | None]:
    """{'재료비': 4, '노무비': null, ...} 형태의 열 매핑을 파싱한다."""
    try:
        obj = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    out: dict[str, int | None] = {}
    for k, v in obj.items():
        out[k] = int(v) if isinstance(v, (int, float)) else None
    return out
