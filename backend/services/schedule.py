"""
일정 역산 엔진

목표 준공일에서 거꾸로 각 단계의 최늦 착수일을 구한다.
근무일(business) 단위 노드는 주말·공휴일을 건너뛴다.
병렬 노드는 앵커 시점에서 각자 역산하고, 가장 이른 날짜가 임계경로가 된다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .rules import citation_of, evaluate, load_rules, rule_index

from .paths import DATA_DIR


# ---------------------------------------------------------------- 공휴일
@dataclass
class Calendar:
    holidays: dict[dt.date, str] = field(default_factory=dict)
    unverified: list[str] = field(default_factory=list)

    def is_workday(self, d: dt.date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def minus_business_days(self, end: dt.date, n: int) -> dt.date:
        """end 이전의 n번째 근무일. end 당일은 세지 않는다."""
        d, left = end, n
        guard = 0
        while left > 0:
            d -= dt.timedelta(days=1)
            guard += 1
            if guard > 4000:
                break
            if self.is_workday(d):
                left -= 1
        return d

    def count_business_days(self, start: dt.date, end: dt.date) -> int:
        if start > end:
            return -self.count_business_days(end, start)
        n, d = 0, start
        while d < end:
            d += dt.timedelta(days=1)
            if self.is_workday(d):
                n += 1
        return n


def load_calendar(path: Path | None = None) -> Calendar:
    p = path or (DATA_DIR / "holidays.yaml")
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cal = Calendar()
    for h in doc.get("holidays", []):
        raw = h.get("date")
        d = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
        cal.holidays[d] = h.get("name", "")
        if not h.get("verified", False):
            cal.unverified.append(f"{d.isoformat()} {h.get('name','')}")
    return cal


# ---------------------------------------------------------------- 역산
@dataclass
class Step:
    id: str
    task: str
    label: str
    days: float
    unit: str
    start: dt.date
    end: dt.date
    parallel: bool = False
    citation: str = ""
    status: str = "confirmed"
    note: str = ""

    @property
    def unit_label(self) -> str:
        return "근무일" if self.unit == "business" else "일"


@dataclass
class Schedule:
    steps: list[Step]
    target: dt.date
    start: dt.date              # 임계경로상 최초 착수일
    feasible: bool
    slack_days: int
    warnings: list[str] = field(default_factory=list)
    unverified_holidays: list[str] = field(default_factory=list)

    @property
    def total_calendar_days(self) -> int:
        return (self.target - self.start).days


def _load_chain() -> list[dict]:
    doc = yaml.safe_load((DATA_DIR / "schedule_chain.yaml").read_text(encoding="utf-8")) or {}
    return doc.get("chain", [])


def backward_schedule(target: dt.date, ctx: dict[str, Any],
                      today: dt.date | None = None,
                      calendar: Calendar | None = None) -> Schedule:
    cal = calendar or load_calendar()
    today = today or dt.date.today()
    rules = load_rules()
    idx = rule_index(rules)

    chain = _load_chain()
    steps: list[Step] = []
    warnings: list[str] = []

    cursor = target
    pending_parallel: list[dict] = []

    def resolve_days(node: dict) -> tuple[float | None, str]:
        if node.get("days") is not None:
            return float(node["days"]), ""
        key = node.get("input")
        if key:
            val = ctx.get(key)
            if val in (None, 0):
                return None, f"'{key}' 값이 없어 일정에 반영하지 못했습니다."
            return float(val), ""
        return None, "소요일수가 정의되지 않았습니다."

    def apply(node: dict, end: dt.date) -> tuple[Step | None, str]:
        days, err = resolve_days(node)
        lt_id = node.get("lt")
        lt = idx.get(lt_id, {}) if lt_id else {}
        if days is None:
            return None, err
        if node.get("unit") == "business":
            start = cal.minus_business_days(end, int(days))
        else:
            start = end - dt.timedelta(days=int(days))
        return Step(
            id=node.get("id", ""), task=node.get("task", ""),
            label=node.get("label", ""), days=days, unit=node.get("unit", "calendar"),
            start=start, end=end, parallel=bool(node.get("parallel")),
            citation=citation_of(lt) if lt else "",
            status=lt.get("status", "confirmed") if lt else "confirmed",
            note=str(node.get("note") or (lt.get("비고", "") if lt else "")),
        ), ""

    for node in chain:
        cond = node.get("activate_if")
        if cond is not None and not evaluate(cond, ctx):
            continue

        if node.get("parallel"):
            pending_parallel.append(node)
            continue

        # 병렬 그룹이 쌓여 있으면 현재 커서에서 각자 역산하고 가장 이른 날로 커서 이동
        if pending_parallel:
            earliest = cursor
            for p in pending_parallel:
                st, err = apply(p, cursor)
                if st is None:
                    warnings.append(f"{p.get('label')} — {err}")
                    continue
                steps.append(st)
                earliest = min(earliest, st.start)
            cursor = earliest
            pending_parallel = []

        st, err = apply(node, cursor)
        if st is None:
            warnings.append(f"{node.get('label')} — {err}")
            continue
        steps.append(st)
        cursor = st.start

    if pending_parallel:
        earliest = cursor
        for p in pending_parallel:
            st, err = apply(p, cursor)
            if st is None:
                warnings.append(f"{p.get('label')} — {err}")
                continue
            steps.append(st)
            earliest = min(earliest, st.start)
        cursor = earliest

    steps.sort(key=lambda s: s.start)
    start = steps[0].start if steps else target
    slack = (start - today).days

    if slack < 0:
        warnings.append(
            f"역산 결과 착수 기한이 {abs(slack)}일 지났습니다. "
            "목표 준공일을 늦추거나, 이행기간·설계기간을 줄여야 합니다."
        )

    return Schedule(
        steps=steps, target=target, start=start,
        feasible=slack >= 0, slack_days=slack,
        warnings=warnings, unverified_holidays=cal.unverified,
    )


def year_end_deadline(year: int) -> dt.date:
    """연말 마감 앵커. LT-연말마감 (매년 시달되는 지침이므로 확인 필요)."""
    return dt.date(year, 12, 20)
