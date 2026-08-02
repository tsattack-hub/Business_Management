"""
감사 검증룰 — Phase 1 (11건)

원칙
  · 위반 메시지에는 반드시 근거 조항을 붙인다. 감사 수감 시 그대로 제시할 수 있어야 한다.
  · status가 unverified인 룰을 쓰면 결과에 '미확정 기준' 표시를 남긴다.
  · blocker는 막되, 사유를 입력하면 우회할 수 있게 한다(사유는 이력에 남는다).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .procedure import Procedure
from .rules import Finding, citation_of, load_rules, rule_index
from .schedule import Calendar

SEVERITY_ORDER = {"blocker": 0, "error": 1, "warning": 2, "info": 3}


def _meta(rid: str) -> tuple[str, str, str, str]:
    """(명칭, 근거, status, 심각도) 를 룰 파일에서 읽는다."""
    idx = rule_index(load_rules())
    r = idx.get(rid, {})
    return (
        r.get("명칭", rid),
        citation_of(r),
        r.get("status", "confirmed"),
        r.get("심각도", "warning"),
    )


def _f(rid: str, passed: bool, message: str, detail: list[str] | None = None,
       severity: str | None = None, status: str | None = None) -> Finding:
    name, cite, st, sev = _meta(rid)
    return Finding(
        rule_id=rid, name=name, severity=severity or sev, passed=passed,
        message=message, citation=cite, status=status or st, detail=detail or [],
    )


# ---------------------------------------------------------------- 개별 룰
def aud_039(ctx: dict[str, Any]) -> Finding:
    """계약유형 판정 오류."""
    ratio = ctx.get("설치비중")
    kind = ctx.get("계약유형")
    if ratio is None:
        return _f("AUD-039", False, "설치비중을 계산하지 못했습니다. 내역서 매핑 또는 직접입력을 확인하세요.",
                  severity="blocker")
    pct = ratio * 100
    if ratio >= 0.50 and kind == "구매설치":
        return _f("AUD-039", False,
                  f"설치비중 {pct:.1f}% 는 50% 이상이므로 공사계약입니다. 구매설치로 진행할 수 없습니다.",
                  severity="blocker")
    if abs(ratio - 0.50) <= 0.05:
        return _f("AUD-039", True,
                  f"설치비중 {pct:.1f}% — 50% 경계 구간입니다. 비목별 귀속 근거를 문서로 남기세요.",
                  detail=["과거 사례: 배관·배선공사가 50% 이상인데 20%로 산정한 건이 지적됨"],
                  severity="warning")
    return _f("AUD-039", True, f"설치비중 {pct:.1f}% — 물품제조·구매계약으로 판정됩니다.")


def aud_010(ctx: dict[str, Any], proc: Procedure) -> Finding:
    """일상감사 미이행."""
    targets: list[str] = ctx.get("일상감사_해당사유", [])
    if not targets:
        return _f("AUD-010", True, "일상감사 대상에 해당하지 않습니다.",
                  detail=["단, 납품기한 연장·계약금액 변경·협약 체결이 발생하면 그때 다시 판정해야 합니다."])
    has_task = "T-P1-110" in proc.ids
    if not has_task:
        return _f("AUD-010", False,
                  "일상감사 대상인데 절차에 일상감사가 없습니다.", detail=targets, severity="blocker")
    return _f("AUD-010", True, "일상감사 대상입니다. 절차에 포함되어 있습니다.", detail=targets)


def aud_033(ctx: dict[str, Any], cal: Calendar) -> Finding:
    """일상감사 회부기한 미달 — 근무일 7일."""
    if not ctx.get("일상감사_해당사유"):
        return _f("AUD-033", True, "일상감사 대상이 아니므로 회부기한을 적용하지 않습니다.")
    req = ctx.get("일상감사의뢰일")
    dec = ctx.get("예정결재일")
    if not req or not dec:
        return _f("AUD-033", True,
                  "의뢰일 또는 예정 결재일이 입력되지 않아 회부기한을 확인하지 못했습니다.",
                  severity="info")
    gap = cal.count_business_days(req, dec)
    if gap < 7:
        latest = cal.minus_business_days(dec, 7)
        return _f("AUD-033", False,
                  f"회부까지 근무일 {gap}일뿐입니다. 7일 이상 필요합니다.",
                  detail=[f"예정 결재일 {dec.isoformat()} 기준 최늦 의뢰일은 {latest.isoformat()} 입니다.",
                          f"공휴일 반영 시 달력상 {(dec - latest).days}일에 해당합니다."])
    return _f("AUD-033", True, f"회부까지 근무일 {gap}일 확보 (기준 7일).")


def aud_036(ctx: dict[str, Any], proc: Procedure) -> Finding:
    """구매규격 사전공개 미이행 또는 순서 오류."""
    if "T-P1-090" not in proc.ids:
        return _f("AUD-036", False,
                  "구매설치는 금액과 무관하게 사전규격공개 전건 대상인데 절차에서 빠져 있습니다.",
                  severity="blocker")
    open_done = ctx.get("사전공개완료일")
    audit_req = ctx.get("일상감사의뢰일")
    if not ctx.get("일상감사_해당사유"):
        return _f("AUD-036", True, "사전규격공개 대상입니다. 공개 5일 + 의뢰 2일을 일정에 반영하세요.")
    if not open_done or not audit_req:
        return _f("AUD-036", True,
                  "사전규격공개는 반드시 일상감사 의뢰 이전에 완료해야 합니다. 날짜를 입력하면 순서를 검증합니다.",
                  severity="info")
    if open_done > audit_req:
        return _f("AUD-036", False,
                  f"사전공개 완료({open_done.isoformat()})가 일상감사 의뢰({audit_req.isoformat()})보다 늦습니다.",
                  detail=["사전규격공개 → 일상감사 순서를 어기면 반송 사유가 됩니다."],
                  severity="blocker")
    return _f("AUD-036", True,
              f"사전공개 완료({open_done.isoformat()}) → 일상감사 의뢰({audit_req.isoformat()}) 순서가 맞습니다.")


def aud_043(ctx: dict[str, Any]) -> Finding:
    """계약유형과 낙찰기준 불일치."""
    kind = ctx.get("계약유형")
    method = ctx.get("낙찰방법")
    if not method:
        return _f("AUD-043", True, "낙찰방법이 선택되지 않았습니다.", severity="info")
    if kind == "구매설치" and method == "적격심사":
        return _f("AUD-043", False,
                  "물품제조·구매계약인데 공사용 적격심사 기준을 선택했습니다. 계약이행능력심사가 맞습니다.")
    if kind == "공사계약" and method == "계약이행능력심사":
        return _f("AUD-043", False,
                  "공사계약인데 물품용 계약이행능력심사를 선택했습니다. 적격심사가 맞습니다.")
    return _f("AUD-043", True, f"계약유형({kind})과 낙찰방법({method})이 일치합니다.",
              detail=["기준점·낙찰하한율은 현행 세부기준으로 확인이 필요합니다 (PC-004 미확정)."])


def aud_024(ctx: dict[str, Any]) -> Finding:
    """공사용 자재 직접구매 회피."""
    trade = ctx.get("공사업종")
    cwork = ctx.get("공사예정가격", 0) or 0
    item_price = ctx.get("직접구매품목_추정가격", 0) or 0
    is_target_item = ctx.get("직접구매대상품목", False)
    has_gov_supply = ctx.get("관급자재있음", False)

    threshold_work = 4_000_000_000 if trade == "종합공사" else 300_000_000
    if not is_target_item or cwork < threshold_work:
        return _f("AUD-024", True, "직접구매(분리발주) 의무 대상이 아닙니다.",
                  detail=[f"판정 기준 — 공사예정가격 {threshold_work:,}원 이상 + 대상품목 4천만원 이상"])
    if item_price < 40_000_000:
        return _f("AUD-024", True, "대상품목 금액이 4천만원 미만이므로 직접구매 의무가 없습니다.")
    if not has_gov_supply:
        return _f("AUD-024", False,
                  f"직접구매 대상입니다(공사 {cwork:,}원, 품목 {item_price:,}원). "
                  "해당 품목을 관급자재로 설계에 반영해야 합니다.",
                  detail=["직접구매가 불가하면 그 사유를 입찰공고에 공표해야 합니다 (시행령 제11조 제3항).",
                          "2개 이상 중기간경쟁제품은 무조건 분리발주."],
                  severity="blocker")
    return _f("AUD-024", True, "직접구매 대상이며 관급자재로 반영되어 있습니다.")


def aud_022(ctx: dict[str, Any]) -> Finding:
    """제한경쟁 중복 제한."""
    limits: list[str] = ctx.get("입찰참가_제한사유", []) or []
    if len(limits) <= 1:
        return _f("AUD-022", True,
                  "제한사유가 1개 이하입니다." if limits else "입찰참가자격 제한을 적용하지 않습니다.")
    s = set(limits)
    allowed_pair = s == {"지역", "실적"}
    has_sme = bool(s & {"중소기업", "소기업등"})
    if allowed_pair or has_sme:
        return _f("AUD-022", True, f"허용되는 조합입니다: {' + '.join(limits)}",
                  detail=["지역(제6호)+실적(제2호), 또는 중소기업(제8호)·소기업등(제10호의)과의 조합만 허용됩니다."])
    return _f("AUD-022", False, f"중복 제한 위반 가능성: {' + '.join(limits)}",
              detail=["같은 항 각 호 또는 각 호 내의 사항을 중복 제한할 수 없습니다.",
                      "예외 — 지역+실적, 중소기업 또는 소기업등과의 조합"])


def aud_023(ctx: dict[str, Any]) -> Finding:
    """고시금액 미만 실적제한."""
    limits: list[str] = ctx.get("입찰참가_제한사유", []) or []
    if "실적" not in limits:
        return _f("AUD-023", True, "실적제한을 적용하지 않습니다.")
    price = ctx.get("추정가격", 0) or 0
    threshold = ctx.get("고시금액", 230_000_000)
    if price < threshold:
        return _f("AUD-023", False,
                  f"추정가격 {price:,}원은 고시금액 {threshold:,}원 미만이므로 실적제한이 절대 불가합니다.",
                  detail=["★ 고시금액 값 자체가 미확정입니다 (2.1억 / 2.2억 / 2.3억 혼재). 계약부서 확인 필요."],
                  severity="blocker")
    return _f("AUD-023", True,
              f"추정가격 {price:,}원 ≥ 고시금액 {threshold:,}원 — 실적제한 가능.",
              detail=["실적 배수는 납품 금액 또는 수량의 1/3이 원칙, 최대 1배수."])


def aud_044(ctx: dict[str, Any]) -> Finding:
    """설치분 안전 서류 (착수 단계 예정 확인)."""
    if not ctx.get("설치작업있음"):
        return _f("AUD-044", True, "설치작업이 없어 해당하지 않습니다.")
    total = ctx.get("총공사금액", 0) or 0
    if total < 40_000_000:
        return _f("AUD-044", True,
                  f"총공사금액 {total:,}원 — 4천만원 미만이므로 산업안전보건관리비 계상 대상이 아닙니다.")
    return _f("AUD-044", True,
              f"총공사금액 {total:,}원 — 산업안전보건관리비 계상·집행·정산 대상입니다.",
              detail=["착수 시 징구: 산업안전보건관리비 사용계획서, 안전관리계획서, 위험성평가 자료, 고용·산재보험 가입증명원",
                      "설계 단계에서 원가계산서에 산업안전보건관리비를 계상해 두어야 합니다.",
                      "★ '구매설치니까 공사가 아니다'라고 판단해 생략하는 오류가 잦습니다."],
              severity="warning")


def aud_003(ctx: dict[str, Any]) -> Finding:
    """하자검사 일정 (준공 후 예정 확인)."""
    target = ctx.get("목표준공일")
    if not target:
        return _f("AUD-003", True, "목표 준공일이 없어 하자검사 일정을 생성하지 못했습니다.", severity="info")
    years = ctx.get("하자담보년수", 1) or 1
    end = dt.date(target.year + int(years), target.month, min(target.day, 28))
    plan = [f"담보기간 만료 예정: {end.isoformat()} (계약조건 {years}년 기준)"]
    for i in range(1, int(years) * 2 + 1):
        d = target + dt.timedelta(days=182 * i)
        if d < end:
            plan.append(f"정기 하자검사 {i}회차 — {d.isoformat()} 무렵")
    plan.append(f"최종 하자검사 — {(end - dt.timedelta(days=14)).isoformat()} ~ {end.isoformat()}")
    return _f("AUD-003", True, "하자검사 일정을 미리 등록하세요. 담당자 교체 시 가장 잘 누락되는 항목입니다.",
              detail=plan, severity="warning")


def aud_004(ctx: dict[str, Any]) -> Finding:
    """부외자산 등재 (준공 단계 예정 확인)."""
    if not ctx.get("예비품있음"):
        return _f("AUD-004", True, "예비품·부외자산 대상이 없다고 입력되었습니다.",
                  detail=["구매설치는 예비품이 함께 입고되는 경우가 많습니다. 규격서의 부속품·예비품 내역을 다시 확인하세요."])
    return _f("AUD-004", True, "준공 시 부외자산·부외 예비품을 전산 등재해야 합니다.",
              detail=["내용연수 1년 이상 + 취득가액 30만원 이상 100만원 미만 + 비용처리된 자산성 물품",
                      "구매발주 시 입고되는 예비품은 부외 예비품으로 등재"],
              severity="warning")


# ---------------------------------------------------------------- 실행
def run_all(ctx: dict[str, Any], proc: Procedure, cal: Calendar) -> list[Finding]:
    findings = [
        aud_039(ctx),
        aud_010(ctx, proc),
        aud_033(ctx, cal),
        aud_036(ctx, proc),
        aud_043(ctx),
        aud_024(ctx),
        aud_022(ctx),
        aud_023(ctx),
        aud_044(ctx),
        aud_003(ctx),
        aud_004(ctx),
    ]
    findings.sort(key=lambda f: (f.passed, SEVERITY_ORDER.get(f.severity, 9), f.rule_id))
    return findings


def summarize(findings: list[Finding]) -> dict[str, int]:
    out = {"blocker": 0, "error": 0, "warning": 0, "info": 0, "passed": 0, "unverified": 0}
    for f in findings:
        if f.passed:
            out["passed"] += 1
        else:
            out[f.severity] = out.get(f.severity, 0) + 1
        if f.needs_review:
            out["unverified"] += 1
    return out
