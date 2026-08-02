"""
주의사항 수집

절차 템플릿의 '주의'·'비고'와, 태스크에 연결된 검증룰의 지적사례를 모아
"이 단계에서 조심할 것" 목록을 만든다.

룰 엔진을 돌려 판정하는 게 아니라, 읽을 수 있는 문장으로 보여주는 게 목적이다.
"""
from __future__ import annotations

from dataclasses import dataclass

from .procedure import Task
from .rules import citation_of, load_rules, rule_index


@dataclass
class Caution:
    text: str
    source: str = ""        # 룰 id 또는 '절차'
    citation: str = ""
    strong: bool = False    # 지적 사례가 실제로 있었던 것


def _clean(s: str) -> str:
    return s.replace("★", "").strip()


def cautions_for(task: Task) -> list[Caution]:
    out: list[Caution] = []

    if task.caution:
        for line in task.caution.split("\n"):
            line = _clean(line)
            if line:
                out.append(Caution(line, "절차", task.citation, strong=True))

    if task.note:
        for line in task.note.split("\n"):
            line = _clean(line).lstrip("· ")
            if line and len(line) > 8:
                out.append(Caution(line, "절차", task.citation))

    idx = rule_index(load_rules())
    for rid in task.audits:
        r = idx.get(rid)
        if not r:
            continue
        name = r.get("명칭", rid)
        case = r.get("지적사례")
        if case:
            body = " ".join(str(case).split())
            out.append(Caution(f"{name} — {body}", rid, citation_of(r), strong=True))
        else:
            hint = r.get("주의") or r.get("지적위험") or ""
            body = " ".join(str(hint).split()) if hint else ""
            out.append(Caution(f"{name}{' — ' + body if body else ''}",
                               rid, citation_of(r), strong=bool(body)))

    # 같은 문장 중복 제거
    seen, uniq = set(), []
    for c in out:
        k = c.text[:60]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def stage_summary(tasks: list[Task]) -> list[Caution]:
    """단계 전체에서 '실제 지적 사례가 있었던' 것만 추린다."""
    out: list[Caution] = []
    for t in tasks:
        for c in cautions_for(t):
            if c.strong:
                out.append(c)
    seen, uniq = set(), []
    for c in out:
        if c.text[:60] in seen:
            continue
        seen.add(c.text[:60])
        uniq.append(c)
    return uniq
