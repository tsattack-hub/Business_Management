"""
구매규격서 초안 생성 · 검증

품목군을 고르면 조항 라이브러리에서 해당 조항을 골라 규격서를 조립한다.
사업 정보로 채울 수 있는 곳은 채우고, 사람이 정해야 하는 수치는 비워 둔다.

조립 직후 특정회사 규격을 스캔한다. 생성기와 검증기를 붙여 둔 이유는,
다른 기관 규격서에서 가져온 조항에 상표·모델이 딸려 오기 때문이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .docgen import FILL_MARK, build_context, subst
from .paths import DOCS_DIR

CLAUSE_PATH = DOCS_DIR / "spec_clauses.yaml"

BLANK = re.compile(r"\[\[\s*(.+?)\s*\]\]")

SECTION_TITLE = {
    1: "일반사항",
    2: "특기시방",
    3: "제출물",
    4: "검사 및 검수",
    5: "하자보수",
    6: "기타",
}


@dataclass
class ItemGroup:
    id: str
    name: str
    clause_ids: list[str]
    spec_fields: list[dict]
    must_check: list[str]


@dataclass
class Clause:
    id: str
    section: int
    title: str
    body: str
    source: str = "표준"
    note: str = ""
    audits: list[str] = field(default_factory=list)
    condition: str = ""


@dataclass
class BrandHit:
    term: str
    kind: str            # 상표 / 패턴
    where: str           # 조항 제목
    line: str
    mitigated: bool      # '동등 이상' 문구가 같은 줄에 있는가


@dataclass
class SpecDraft:
    item_group: str
    sections: list[tuple[int, str, list[Clause]]]
    blanks: list[tuple[str, str]]        # (조항 제목, 채워야 할 내용)
    brand_hits: list[BrandHit]
    must_check: list[str]
    source_counts: dict[str, int]

    @property
    def clause_count(self) -> int:
        return sum(len(c) for _, _, c in self.sections)


# ---------------------------------------------------------------- 로딩
def load_library() -> dict[str, Any]:
    return yaml.safe_load(CLAUSE_PATH.read_text(encoding="utf-8")) or {}


def item_groups() -> list[ItemGroup]:
    lib = load_library()
    return [
        ItemGroup(
            id=g["id"], name=g.get("명칭", g["id"]),
            clause_ids=g.get("조항", []) or [],
            spec_fields=g.get("규격항목", []) or [],
            must_check=g.get("필수확인", []) or [],
        )
        for g in lib.get("품목군", [])
    ]


def _to_clause(d: dict) -> Clause:
    return Clause(
        id=d["id"], section=int(d.get("절", 6)), title=d.get("제목", d["id"]),
        body=d.get("본문", ""), source=d.get("출처", "표준"),
        note=d.get("비고", ""), audits=d.get("검증룰", []) or [],
        condition=d.get("조건", ""),
    )


# ---------------------------------------------------------------- 조립
def build_draft(group_id: str, project: dict[str, Any],
                spec_values: dict[str, str] | None = None) -> SpecDraft:
    lib = load_library()
    groups = {g.id: g for g in item_groups()}
    group = groups.get(group_id) or groups["GENERAL"]
    spec_values = spec_values or {}

    ctx = build_context(project)
    # 사용자가 입력한 규격 수치를 치환자로 추가
    for k, v in spec_values.items():
        if str(v).strip():
            ctx[k] = str(v).strip()

    common = [_to_clause(c) for c in lib.get("공통조항", [])]
    by_item = {c["id"]: _to_clause(c) for c in lib.get("품목조항", [])}
    picked = [by_item[cid] for cid in group.clause_ids if cid in by_item]

    clauses: list[Clause] = []
    for c in common + picked:
        if c.condition and not project.get(c.condition):
            continue
        body = subst(c.body, ctx)
        # 사용자가 입력한 규격 수치를 [[키]] 자리에 넣는다.
        # 값이 없는 항목은 빈칸으로 남겨 사람이 채우게 한다.
        body = BLANK.sub(
            lambda m: str(spec_values.get(m.group(1), "")).strip() or m.group(0),
            body,
        )
        c.body = body
        clauses.append(c)

    # 절별로 묶기
    sections: list[tuple[int, str, list[Clause]]] = []
    for num in sorted({c.section for c in clauses}):
        group_clauses = [c for c in clauses if c.section == num]
        sections.append((num, SECTION_TITLE.get(num, f"{num}절"), group_clauses))

    blanks = [(c.title, m.group(1)) for c in clauses for m in BLANK.finditer(c.body)]
    hits = scan_brands(clauses, lib)
    counts: dict[str, int] = {}
    for c in clauses:
        counts[c.source] = counts.get(c.source, 0) + 1

    return SpecDraft(
        item_group=group.name, sections=sections, blanks=blanks,
        brand_hits=hits, must_check=group.must_check, source_counts=counts,
    )


# ---------------------------------------------------------------- 브랜드 스캔
# 기술 표준·규격 약어. 모델번호처럼 보이지만 상표가 아니다.
_STANDARD = re.compile(
    r"^(IEEE|ISO|IEC|KS[A-Z]?|ITU|ONVIF|RFC|ANSI|NEMA|UL|EN|JIS|ASTM|KOLAS"
    r"|IP\d{2}|H\.?26\d|POE|RAID|SNMP|SATA|SAS|USB|HDMI|VGA|RS\d*|TCP|UDP"
    r"|LED|UPS|NVR|DVR|VMS|CCTV|PTZ|KVA|SFP|LAN|WAN|VLAN|QOS|NTP|LDAP)",
    re.I,
)

_HANGUL = re.compile(r"[가-힣]")


def _standalone(term: str, line: str) -> bool:
    """
    상표어가 다른 낱말 안에 박혀 있는 경우를 걸러낸다.
    '모델'의 '델', '보쉬한' 같은 오탐 방지.
    """
    for m in re.finditer(re.escape(term), line, re.I):
        before = line[m.start() - 1] if m.start() > 0 else " "
        after = line[m.end()] if m.end() < len(line) else " "
        if _HANGUL.search(term):
            if not _HANGUL.match(before) and not _HANGUL.match(after):
                return True
        else:
            if not before.isalnum() and not after.isalnum():
                return True
    return False


def scan_brands(clauses: list[Clause], lib: dict | None = None) -> list[BrandHit]:
    lib = lib or load_library()
    conf = lib.get("브랜드탐지", {})
    brands = conf.get("상표", []) or []
    patterns = conf.get("패턴", []) or []
    softeners = conf.get("완화문구", []) or []

    hits: list[BrandHit] = []
    for c in clauses:
        for raw in c.body.split("\n"):
            line = raw.strip()
            if not line:
                continue
            mitigated = any(s in line for s in softeners)

            for b in brands:
                if b.lower() in line.lower() and _standalone(b, line):
                    hits.append(BrandHit(b, "상표", c.title, line, mitigated))

            for p in patterns:
                try:
                    rx = re.compile(p["regex"])
                except re.error:
                    continue
                for m in rx.finditer(line):
                    token = m.group(0).strip()
                    if _STANDARD.match(token):
                        continue
                    if BLANK.search(line):      # 아직 안 채운 빈칸 줄은 판단 보류
                        continue
                    hits.append(BrandHit(token, p.get("설명", "패턴"),
                                         c.title, line, mitigated))

    seen, uniq = set(), []
    for h in hits:
        k = (h.term, h.where)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
    return uniq


def scan_text(text: str) -> list[BrandHit]:
    """사용자가 손으로 고친 규격서 본문을 다시 스캔할 때."""
    return scan_brands([Clause(id="-", section=0, title="본문", body=text)])


# ---------------------------------------------------------------- 문서 출력
def to_plan(draft: SpecDraft, project: dict[str, Any]) -> dict:
    ctx = build_context(project)
    blocks: list[dict] = [
        {"type": "paragraph",
         "text": f"품목군: {draft.item_group}   ·   작성일: {ctx['오늘']}"},
        {"type": "paragraph",
         "text": "「  」로 표시된 곳은 사업 담당자가 판단해 채워야 하는 항목입니다."},
    ]
    for num, name, clauses in draft.sections:
        blocks.append({"type": "heading", "level": 1, "text": f"{num}. {name}"})
        for i, c in enumerate(clauses, 1):
            blocks.append({"type": "heading", "level": 2, "text": f"{num}.{i} {c.title}"})
            for line in c.body.split("\n"):
                if line.strip():
                    blocks.append({
                        "type": "paragraph",
                        "text": BLANK.sub(lambda m: f"「 {m.group(1)} 」", line),
                    })
    return {
        "schemaVersion": "hwpx.document_plan.v1",
        "title": "구매규격서",
        "metadata": {
            "사업명": ctx["사업명"],
            "주관부서": ctx["부서"],
            "작성일": ctx["오늘"],
            "품목군": draft.item_group,
        },
        "blocks": blocks,
    }


def render(draft: SpecDraft, project: dict[str, Any], out_dir: Path) -> Path:
    from hwpx_automation.office.authoring import create_document_from_plan

    doc = create_document_from_plan(to_plan(draft, project))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "구매규격서(초안).hwpx"
    doc.save_to_path(str(path))
    return path


def to_text(draft: SpecDraft) -> str:
    out: list[str] = []
    for num, name, clauses in draft.sections:
        out.append(f"\n{num}. {name}")
        for i, c in enumerate(clauses, 1):
            out.append(f"\n  {num}.{i} {c.title}")
            for line in c.body.split("\n"):
                if line.strip():
                    out.append("      " + BLANK.sub(lambda m: f"「 {m.group(1)} 」", line))
    return "\n".join(out)
