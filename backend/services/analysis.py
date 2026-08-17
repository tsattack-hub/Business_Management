"""
사업 분석 오케스트레이션

기존 Streamlit app.py 가 화면에서 인라인으로 하던 판정·절차 구성 로직을
한 곳으로 모아 JSON 직렬화 가능한 구조로 돌려준다.

완료태스크(진행 상태)는 화면에서 계산하므로 여기서는 다루지 않는다.
절차 구조는 사업 조건·설계금액에만 의존한다.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from . import docgen, guidance
from .procedure import build_procedure, judge_contract_type, judge_procurement_track

STAGES: dict[str, str] = {
    "P1": "설계 — 규격서부터 계약의뢰까지",
    "P2": "입찰 · 계약",
    "P3": "착수 · 제작",
    "P4": "납품 · 설치",
    "P5": "준공 · 정산",
    "P6": "하자관리",
}


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _build_ctx(proj: dict[str, Any]) -> dict[str, Any]:
    """절차 활성화 조건 평가에 쓰는 컨텍스트."""
    ctx = dict(proj)
    ctx |= {
        "사업유형": "구매설치",
        "계약방법": "제한경쟁",
        "품목": ["CCTV"] if proj.get("CCTV설치") else [],
        "제작품목있음": True,
        "선금신청": True,
        "철거발생품있음": False,
        "계약변경발생": False,
        "납품기한연장신청": False,
        "산업안전보건관리비계상": proj.get("설치작업있음", False),
        "설치공사금액": _int(proj.get("설치분_노무")) + _int(proj.get("설치분_경비")),
        "설치기간": f"{_int(proj.get('이행기간'), 90)}일",
        "일상감사대상": _int(proj.get("추정가격")) > 100_000_000,
    }
    return ctx


def analyze(proj: dict[str, Any]) -> dict[str, Any]:
    """사업 한 건을 판정하고 절차·서류 구조를 돌려준다."""
    mat = _int(proj.get("물품분"))
    lab = _int(proj.get("설치분_노무"))
    exp = _int(proj.get("설치분_경비"))

    ct = judge_contract_type(mat, lab, exp)

    judgment = {
        "kind": ct.kind,
        "ratio": ct.ratio,
        "ratioPct": f"{ct.ratio * 100:.1f}%" if ct.ratio is not None else "—",
        "inScope": ct.in_scope,
        "boundary": ct.boundary,
        "notes": ct.notes,
        "citation": ct.citation,
        "status": ct.status,
    }

    # 공사계약·판정불가면 절차를 구성하지 않는다 (적용 범위 밖)
    if ct.kind == "판정불가" or not ct.in_scope:
        return {
            "judgment": judgment,
            "track": None,
            "stages": [],
            "templates": [],
            "totalTasks": 0,
        }

    year = _int(proj.get("연도"), dt.date.today().year)
    ctx = _build_ctx(proj)
    track = judge_procurement_track(ctx, dt.date(year, 1, 1))
    proc = build_procedure(ctx)
    tpls = docgen.load_templates()

    by_stage: dict[str, list] = {}
    for t in proc.tasks:
        by_stage.setdefault(t.stage_id, []).append(t)

    stages: list[dict[str, Any]] = []
    for sid, sname in STAGES.items():
        tasks = by_stage.get(sid, [])
        if not tasks:
            continue
        docs_here = [x for x in tpls.values() if x.stage == sid]
        cautions = guidance.stage_summary(tasks)
        stages.append({
            "id": sid,
            "name": sname,
            "cautions": [
                {"text": c.text, "source": c.source, "citation": c.citation}
                for c in cautions[:6]
            ],
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "deadline": t.deadline,
                    "period": t.period,
                    "documents": t.documents,
                }
                for t in tasks
            ],
            "docs": [
                {"id": d.id, "name": d.name, "fmt": d.fmt,
                 "note": d.note, "citation": d.citation}
                for d in docs_here
            ],
        })

    templates = [
        {"id": d.id, "name": d.name, "fmt": d.fmt, "stage": d.stage}
        for d in tpls.values()
    ]

    return {
        "judgment": judgment,
        "track": {
            "value": str(track.value),
            "note": track.note,
            "citation": track.citation,
            "status": track.status,
        },
        "stages": stages,
        "templates": templates,
        "totalTasks": len(proc.tasks),
    }
