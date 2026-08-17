"""
조달청 사전규격 수집 API (구매규격서 초안 보조)

  · status  : 서버에 인증키(G2B_KEY)가 설정돼 있는지
  · search  : 사업명/키워드로 유사 사전규격 목록 조회 (파일 다운로드 없음)
  · extract : 사용자가 고른 공고의 규격서 파일을 받아 조항 후보를 추출

인증키는 서버 환경변수 G2B_KEY 에서만 읽는다. 프론트로 절대 보내지 않는다.
추출 조항은 모두 '수집'이며 사람이 검토한 뒤 초안에 넣어야 한다 (AUD-013).
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..services import harvest as H
from ..services import specgen
from ..services.g2b import G2BClient, G2BError, SpecNotice, classify, load_conf
from ..services.paths import HARVEST_DIR

router = APIRouter(prefix="/api/harvest", tags=["harvest"])


def _key() -> str:
    return os.environ.get("G2B_KEY", "").strip()


def _no_key() -> JSONResponse:
    return JSONResponse(status_code=400, content={
        "detail": "서버에 조달청 인증키(G2B_KEY)가 없습니다. "
                  "백엔드 실행 전 환경변수 G2B_KEY 를 설정하십시오."})


@router.get("/status")
def status():
    """인증키 설정 여부. 프론트가 검색 UI를 켤지 판단하는 용도."""
    return {"keyConfigured": bool(_key())}


@router.post("/search")
def search(
    keyword: str = Body(..., embed=True),
    business: str = Body("물품", embed=True),
    days: int = Body(90, embed=True),
    max_pages: int = Body(3, embed=True),
    limit: int = Body(60, embed=True),
):
    """사업명/키워드로 유사 사전규격을 조회한다. 파일은 받지 않는다."""
    key = _key()
    if not key:
        return _no_key()
    if not keyword.strip():
        return JSONResponse(status_code=400, content={"detail": "검색어를 입력하십시오."})

    conf = load_conf()
    client = G2BClient(key, conf)
    end = dt.date.today()
    begin = end - dt.timedelta(days=max(1, days))

    out: list[dict[str, Any]] = []
    try:
        for n in client.iter_notices(business, begin, end,
                                     keyword=keyword.strip(), max_pages=max_pages):
            out.append({
                "등록번호": n.등록번호,
                "사업명": n.사업명,
                "수요기관": n.수요기관,
                "공고기관": n.공고기관,
                "budget": n.budget,
                "공개일자": n.공개일자,
                "마감일자": n.마감일자,
                "품목군추정": classify(n, conf),
                "파일수": len(n.파일),
                "파일": [[nm, u] for nm, u in n.파일],
            })
            if len(out) >= limit:
                break
    except G2BError as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})

    return {"notices": out, "count": len(out),
            "기간": {"begin": begin.isoformat(), "end": end.isoformat()}}


@router.post("/extract")
def extract(
    notices: list[dict] = Body(..., embed=True),
    max_files: int = Body(8, embed=True),
):
    """고른 공고들의 규격서 파일을 받아 조항 후보를 추출한다 (느림 · throttle)."""
    key = _key()
    if not key:
        return _no_key()
    if not notices:
        return JSONResponse(status_code=400, content={"detail": "선택한 공고가 없습니다."})

    conf = load_conf()
    conf["collect"]["max_files_per_run"] = max(1, int(max_files))
    client = G2BClient(key, conf)

    rebuilt = [
        SpecNotice(
            등록번호=x.get("등록번호"),
            사업명=x.get("사업명"),
            수요기관=x.get("수요기관"),
            파일=[tuple(f) for f in x.get("파일", []) if len(f) == 2],
        )
        for x in notices
    ]

    try:
        res = H.harvest(rebuilt, conf, HARVEST_DIR, session=client.s)
    except Exception as e:  # noqa: BLE001 - 사용자에게 사유 전달
        return JSONResponse(status_code=400, content={"detail": f"수집 실패: {e}"})

    clauses = []
    for c in res.clauses:
        hits = specgen.scan_text(c.body)
        clauses.append({
            "제목": c.title,
            "절": c.section,
            "본문": c.body,
            "기관": c.source_org,
            "사전규격": c.source_notice,
            "파일": c.source_file,
            "브랜드경고": [
                {"term": h.term, "kind": h.kind, "line": h.line, "mitigated": h.mitigated}
                for h in hits
            ],
        })

    return {
        "clauses": clauses,
        "summary": res.summary,
        "failures": res.failures,
        "skipped": res.skipped,
    }
