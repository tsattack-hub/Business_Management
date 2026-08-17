"""
사업 저장 · 불러오기

projects/{사업id}.json 한 파일에 사업 정보와 진행 상태를 담는다.
DB를 쓰지 않는 이유 — 외부망 단독 실행이라 백업이 파일 복사로 끝나는 편이 낫다.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .paths import OUT_DIR, PROJ_DIR, ROOT  # noqa: F401


def slug(name: str) -> str:
    s = unicodedata.normalize("NFC", name or "무제").strip()
    s = re.sub(r"[\\/:*?\"<>|]", "", s)
    s = re.sub(r"\s+", "_", s)
    return s[:60] or "무제"


def _encode(o: Any):
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError(type(o))


def _decode_dates(d: dict) -> dict:
    for k, v in list(d.items()):
        if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            try:
                d[k] = dt.date.fromisoformat(v)
            except ValueError:
                pass
    return d


def list_projects() -> list[tuple[str, str]]:
    """[(사업id, 사업명)] — 최근 수정 순."""
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(PROJ_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append((p.stem, d.get("사업명") or p.stem))
        except Exception:
            continue
    return out


def load(pid: str) -> dict[str, Any]:
    p = PROJ_DIR / f"{pid}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    d["완료태스크"] = set(d.get("완료태스크", []))
    return _decode_dates(d)


def save(project: dict[str, Any]) -> str:
    PROJ_DIR.mkdir(parents=True, exist_ok=True)
    d = dict(project)
    d["완료태스크"] = sorted(d.get("완료태스크", set()))
    d["수정일"] = dt.date.today().isoformat()
    pid = slug(d.get("사업명", ""))
    (PROJ_DIR / f"{pid}.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2, default=_encode), encoding="utf-8")
    return pid


def delete(pid: str) -> None:
    (PROJ_DIR / f"{pid}.json").unlink(missing_ok=True)


def out_dir(project: dict[str, Any]) -> Path:
    return OUT_DIR / slug(project.get("사업명", ""))


def blank() -> dict[str, Any]:
    y = dt.date.today().year
    return {
        "사업명": "", "연도": y, "공항": "", "부서": "", "담당자": "",
        "추정가격": 0, "이행기간": 90, "목표준공일": dt.date(y, 12, 20),
        "물품분": 0, "설치분_노무": 0, "설치분_경비": 0,
        "중기간경쟁제품": False, "고시금액": 230_000_000,
        "설치작업있음": True, "CCTV설치": False, "시설물신축_증개축": False,
        "정보통신제품도입": False, "정보화사업": False, "소프트웨어포함": False,
        "방송장비": False, "관급자재있음": False, "예비품있음": True,
        "낙찰방법": "계약이행능력심사",
        "완료태스크": set(),
    }
