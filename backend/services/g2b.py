"""
조달청 나라장터 사전규격정보서비스 클라이언트

설계 전제
  응답 필드명이 확정되지 않았다. 그래서 이 모듈은 필드명을 하드코딩하지 않고
  docs/g2b_api.yaml 의 candidates 에서 실제 존재하는 것을 골라 쓴다.
  못 찾은 필드는 None 으로 두고 raw 를 함께 보관해 나중에 복구할 수 있게 한다.

  최초 1회 probe() 로 실제 필드명을 확인하고 yaml 을 고치는 것이 정상 절차다.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests
import yaml

from .paths import DOCS_DIR

CONF_PATH = DOCS_DIR / "g2b_api.yaml"


class G2BError(RuntimeError):
    pass


def load_conf() -> dict[str, Any]:
    return yaml.safe_load(CONF_PATH.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------- 레코드
@dataclass
class SpecNotice:
    등록번호: str | None = None
    사업명: str | None = None
    공개일자: str | None = None
    마감일자: str | None = None
    수요기관: str | None = None
    공고기관: str | None = None
    배정예산: str | None = None
    규격내용: str | None = None
    의견수: str | None = None
    납품기한: str | None = None
    담당자: str | None = None
    파일: list[tuple[str, str]] = field(default_factory=list)   # (파일명, URL)
    raw: dict = field(default_factory=dict)

    @property
    def budget(self) -> int | None:
        try:
            return int(float(str(self.배정예산).replace(",", "")))
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------- 필드 해석
def _pick(rec: dict, candidates: list[str]) -> Any:
    for c in candidates:
        if c in rec and rec[c] not in (None, "", "null"):
            return rec[c]
    return None


def _pick_multi(rec: dict, candidates: list[str], limit: int) -> list[Any]:
    """specDocFileUrl1, ...Url2 처럼 번호가 붙은 필드를 모은다."""
    out: list[Any] = []
    for c in candidates:
        stem = c.rstrip("0123456789") or c
        for i in range(1, limit + 1):
            for name in (f"{stem}{i}", f"{stem}_{i}"):
                v = rec.get(name)
                if v not in (None, "", "null"):
                    out.append(v)
        if out:
            break
    return out


def parse_record(rec: dict, conf: dict) -> SpecNotice:
    f = conf["fields"]
    n = SpecNotice(raw=rec)
    for key in ("등록번호", "사업명", "공개일자", "마감일자", "수요기관",
                "공고기관", "배정예산", "규격내용", "의견수", "납품기한", "담당자"):
        spec = f.get(key)
        if spec:
            setattr(n, key, _pick(rec, spec["candidates"]))

    urls = _pick_multi(rec, f["규격서파일"]["candidates"], f["규격서파일"].get("다중최대", 10))
    names = _pick_multi(rec, f["규격서파일명"]["candidates"], f["규격서파일명"].get("다중최대", 10))
    for i, u in enumerate(urls):
        nm = str(names[i]) if i < len(names) else _guess_name(str(u), i)
        n.파일.append((nm, str(u)))
    return n


def _guess_name(url: str, i: int) -> str:
    tail = url.split("/")[-1].split("?")[0]
    return tail if "." in tail else f"첨부{i+1}"


# ---------------------------------------------------------------- 클라이언트
class G2BClient:
    def __init__(self, service_key: str, conf: dict | None = None,
                 session: requests.Session | None = None):
        if not service_key:
            raise G2BError("인증키가 없습니다. 공공데이터포털에서 활용신청 후 발급받으십시오.")
        self.key = service_key
        self.conf = conf or load_conf()
        self.api = self.conf["api"]
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = self.conf["collect"]["user_agent"]
        self.unknown_keys: set[str] = set()

    # ---------------- 저수준 호출
    def _get(self, operation: str, extra: dict[str, Any]) -> dict:
        p = self.api["params"]
        d = self.api["defaults"]
        params = {
            p["key"]: self.key,
            p["type"]: d["type"],
            p["rows"]: d["rows"],
            p["page"]: 1,
        }
        params.update(extra)
        url = f"{self.api['base']}/{operation}"
        r = self.s.get(url, params=params, timeout=30)
        if r.status_code != 200:
            raise G2BError(f"HTTP {r.status_code} — {r.text[:300]}")
        try:
            data = r.json()
        except json.JSONDecodeError:
            raise G2BError(
                "JSON이 아닌 응답입니다. 대개 인증키 문제입니다.\n"
                f"응답 앞부분: {r.text[:400]}")
        self._check_error(data)
        return data

    @staticmethod
    def _check_error(data: dict) -> None:
        hdr = (data.get("response", {}) or {}).get("header", {}) or {}
        code = str(hdr.get("resultCode", "")).strip()
        msg = hdr.get("resultMsg", "")
        if code and code not in ("00", "0", "NORMAL SERVICE."):
            hint = ""
            if "SERVICE_KEY" in str(msg).upper() or code in ("30", "31"):
                hint = ("\n → 인증키를 확인하십시오. 활용신청 승인 직후에는 "
                        "1시간 정도 반영이 걸릴 수 있습니다.")
            elif code in ("22", "336"):
                hint = "\n → 일일 트래픽 초과입니다. 내일 다시 시도하거나 증량 신청하십시오."
            raise G2BError(f"API 오류 {code}: {msg}{hint}")

    @staticmethod
    def _items(data: dict) -> list[dict]:
        body = (data.get("response", {}) or {}).get("body", {}) or {}
        items = body.get("items")
        if items is None:
            return []
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items or []

    @staticmethod
    def _total(data: dict) -> int:
        body = (data.get("response", {}) or {}).get("body", {}) or {}
        try:
            return int(body.get("totalCount", 0))
        except (TypeError, ValueError):
            return 0

    # ---------------- probe
    def probe(self, business: str = "물품", days: int = 7) -> dict[str, Any]:
        """
        실제 응답의 필드명을 확인한다. 최초 1회 반드시 실행할 것.
        반환: {'total':n, 'keys':[...], '매핑결과':{...}, '미매핑키':[...], 'sample':{...}}
        """
        op = self.api["operations"][business]
        end = dt.date.today()
        begin = end - dt.timedelta(days=days)
        p = self.api["params"]
        data = self._get(op, {
            p["begin"]: begin.strftime("%Y%m%d") + "0000",
            p["end"]: end.strftime("%Y%m%d") + "2359",
            p["inquiry_div"]: self.api["defaults"]["inquiry_div"],
            p["rows"]: 5,
        })
        items = self._items(data)
        if not items:
            return {"total": self._total(data), "keys": [], "미매핑키": [],
                    "매핑결과": {}, "sample": {},
                    "note": "해당 기간에 자료가 없습니다. days 를 늘려 다시 시도하십시오."}

        sample = items[0]
        keys = sorted(sample.keys())
        f = self.conf["fields"]
        mapped: dict[str, str | None] = {}
        used: set[str] = set()
        for name, spec in f.items():
            hit = next((c for c in spec["candidates"] if c in sample), None)
            mapped[name] = hit
            if hit:
                used.add(hit)
        # 번호 붙은 파일 필드도 사용된 것으로 처리
        for k in keys:
            base = k.rstrip("0123456789")
            if any(base == c.rstrip("0123456789")
                   for spec in f.values() for c in spec["candidates"]):
                used.add(k)
        return {
            "total": self._total(data),
            "keys": keys,
            "매핑결과": mapped,
            "미매핑키": [k for k in keys if k not in used],
            "sample": sample,
        }

    # ---------------- 목록 조회
    def iter_notices(self, business: str, begin: dt.date, end: dt.date,
                     keyword: str | None = None,
                     max_pages: int = 50) -> Iterator[SpecNotice]:
        """기간을 max_range_days 로 쪼개어 전 페이지를 순회한다."""
        p = self.api["params"]
        step = int(self.api.get("max_range_days", 31))
        throttle = float(self.api.get("throttle_sec", 0.7))
        op = (self.api["search_operations"][business] if keyword
              else self.api["operations"][business])

        cur = begin
        while cur <= end:
            chunk_end = min(cur + dt.timedelta(days=step - 1), end)
            page = 1
            while page <= max_pages:
                extra = {
                    p["begin"]: cur.strftime("%Y%m%d") + "0000",
                    p["end"]: chunk_end.strftime("%Y%m%d") + "2359",
                    p["inquiry_div"]: self.api["defaults"]["inquiry_div"],
                    p["page"]: page,
                }
                if keyword:
                    extra[p["keyword"]] = keyword
                data = self._get(op, extra)
                items = self._items(data)
                if not items:
                    break
                for rec in items:
                    yield parse_record(rec, self.conf)
                if len(items) < int(self.api["defaults"]["rows"]):
                    break
                page += 1
                time.sleep(throttle)
            cur = chunk_end + dt.timedelta(days=1)
            time.sleep(throttle)


# ---------------------------------------------------------------- 필터
def classify(notice: SpecNotice, conf: dict) -> str | None:
    """사업명으로 품목군을 추정한다. 해당 없으면 None."""
    name = f"{notice.사업명 or ''} {notice.규격내용 or ''}"
    for group, words in (conf["filters"]["키워드"] or {}).items():
        if any(w.lower() in name.lower() for w in words):
            return group
    return None


def is_spec_file(filename: str, conf: dict) -> bool:
    f = conf["filters"]
    low = filename.lower()
    if not any(low.endswith(e) for e in f["허용확장자"]):
        return False
    if any(x.lower() in low for x in f["제외_파일명패턴"]):
        return False
    return any(x.lower() in low for x in f["규격서_파일명패턴"])


def preferred_org(notice: SpecNotice, conf: dict) -> bool:
    prefs = conf["filters"].get("선호기관") or []
    if not prefs:
        return True
    org = f"{notice.수요기관 or ''} {notice.공고기관 or ''}"
    return any(p in org for p in prefs)
