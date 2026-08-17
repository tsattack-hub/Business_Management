"""
계약유형 판정(MX-001) · 절차 인스턴스 생성

절차는 06_절차템플릿_구매설치.yaml 에서 읽는다.
activate_if 를 평가해 해당 사업에 실제로 필요한 태스크만 남긴다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from .rules import Decision, citation_of, evaluate, load_rules, rule_index

BOUNDARY = 0.05          # 50% ± 5%p 구간은 경계값으로 보고 근거 보강을 요구


# ---------------------------------------------------------------- 계약유형
@dataclass
class ContractType:
    ratio: float | None
    material: float
    install: float
    total: float
    kind: str                 # '구매설치' | '공사계약' | '판정불가'
    boundary: bool = False
    citation: str = ""
    status: str = "unverified"
    threshold: float = 0.50
    notes: list[str] = field(default_factory=list)

    @property
    def in_scope(self) -> bool:
        return self.kind == "구매설치"


def judge_contract_type(material: float, labor: float, expense: float) -> ContractType:
    rules = load_rules()
    idx = rule_index(rules)
    mx = idx.get("MX-001", {})

    install = labor + expense
    total = material + install
    cite = citation_of(mx)
    status = mx.get("status", "unverified")

    if total <= 0:
        return ContractType(None, material, install, total, "판정불가",
                            citation=cite, status=status,
                            notes=["설계금액 합계가 0입니다. 내역서 열 매핑 또는 직접입력 값을 확인하세요."])

    ratio = install / total
    kind = "공사계약" if ratio >= 0.50 else "구매설치"
    boundary = abs(ratio - 0.50) <= BOUNDARY

    notes: list[str] = []
    if boundary:
        notes.append(
            "설치비중이 50% 경계(45~55%) 안에 있습니다. 비목별 귀속 근거를 문서로 보강하세요."
        )
    if kind == "공사계약":
        notes.append("공사계약이므로 이 판정기의 적용 범위를 벗어납니다. 공사 절차를 적용하세요.")
    if expense == 0:
        notes.append("경비가 0으로 집계되었습니다. 기계경비·가설비가 누락되면 설치비중이 낮게 나옵니다.")

    return ContractType(ratio, material, install, total, kind,
                        boundary=boundary, citation=cite, status=status, notes=notes)


# ---------------------------------------------------------------- 조달 트랙
def judge_procurement_track(ctx: dict[str, Any], as_of: dt.date) -> Decision:
    """PC-001 적용. 고시금액이 미확정이므로 결과에 status를 달아 돌려준다."""
    rules = load_rules()
    idx = rule_index(rules)
    pc = idx.get("PC-001", {})
    cite = citation_of(pc)

    threshold = ctx.get("고시금액", 230_000_000)
    price = ctx.get("추정가격", 0)
    smpp = ctx.get("중기간경쟁제품", False)

    if smpp and price >= threshold:
        val, note = "조달청 위탁", "중기간경쟁제품이면서 고시금액 이상 → 조달청장에게 구매 위탁"
    elif smpp:
        val, note = "자체 입찰 (중기간경쟁)", "직접생산확인증명서로 참가자격 제한. 제3자단가도 가능"
    elif price >= threshold:
        val, note = "자체 입찰 (일반경쟁)", "고시금액 이상 → 실적 등 제한 가능"
    else:
        val, note = "자체 입찰 (중소기업 우선조달)", "계약업무처리지침 제17조의2 우선조달계약 적용 구간"

    return Decision("PC-001", "조달 트랙", val, citation=cite,
                    status=pc.get("status", "unverified"), note=note)


# ---------------------------------------------------------------- 절차
@dataclass
class Task:
    id: str
    stage_id: str
    stage_name: str
    name: str
    note: str = ""
    caution: str = ""
    predecessors: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    audits: list[str] = field(default_factory=list)
    leadtimes: list[str] = field(default_factory=list)
    citation: str = ""
    status: str = "confirmed"
    deadline: str = ""
    period: str = ""
    active: bool = True
    reason: str = ""          # 비활성 사유


@dataclass
class Procedure:
    tasks: list[Task]
    dropped: list[Task]

    def by_stage(self) -> dict[str, list[Task]]:
        out: dict[str, list[Task]] = {}
        for t in self.tasks:
            out.setdefault(f"{t.stage_id} · {t.stage_name}", []).append(t)
        return out

    def get(self, tid: str) -> Task | None:
        return next((t for t in self.tasks if t.id == tid), None)

    @property
    def ids(self) -> set[str]:
        return {t.id for t in self.tasks}


def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def _flatten_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "\n".join(f"· {x}" for x in v)
    if isinstance(v, dict):
        return "\n".join(f"· {k}: {x}" for k, x in v.items())
    return str(v)


def build_procedure(ctx: dict[str, Any]) -> Procedure:
    rules = load_rules()
    template = rules.get("단계") or []
    keep: list[Task] = []
    dropped: list[Task] = []

    for stage in template:
        sid = stage.get("단계id", "")
        sname = stage.get("명칭", "")
        for raw in stage.get("태스크", []):
            t = Task(
                id=raw.get("id", ""),
                stage_id=sid,
                stage_name=sname,
                name=raw.get("명칭", ""),
                note=_flatten_text(raw.get("비고")),
                caution=_flatten_text(raw.get("주의")),
                predecessors=_as_list(raw.get("선행")),
                outputs=_as_list(raw.get("산출물")),
                documents=_as_list(raw.get("징구서류")),
                audits=_as_list(raw.get("검증룰")),
                leadtimes=_as_list(raw.get("리드타임")),
                citation=citation_of(raw),
                status=raw.get("status", "confirmed"),
                deadline=str(raw.get("기한") or raw.get("시점") or ""),
                period=str(raw.get("주기") or ""),
            )
            cond = raw.get("activate_if")
            if cond is None or evaluate(cond, ctx):
                keep.append(t)
            else:
                t.active = False
                t.reason = _condition_text(cond)
                dropped.append(t)

    # 선행 태스크가 제거되었으면 참조를 정리한다
    alive = {t.id for t in keep}
    for t in keep:
        t.predecessors = [p for p in t.predecessors if p in alive]

    return Procedure(tasks=keep, dropped=dropped)


def _condition_text(cond: Any) -> str:
    if isinstance(cond, dict):
        if "or" in cond:
            return " 또는 ".join(_condition_text(c) for c in cond["or"])
        parts = []
        for k, v in cond.items():
            if isinstance(v, dict):
                op, val = next(iter(v.items()))
                parts.append(f"{k} {op} {val:,}" if isinstance(val, (int, float)) else f"{k} {op} {val}")
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)
    return str(cond)


def gate_status(proc: Procedure, done: set[str]) -> dict[str, bool]:
    """각 태스크가 착수 가능한지(선행 완료 여부)."""
    return {t.id: all(p in done for p in t.predecessors) for t in proc.tasks}
