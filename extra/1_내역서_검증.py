"""
내역서 검증 — Phase 2

AUD-030  소계·합계 검산 (행 금액 / 합계 열 / 소계 / SUM 범위 / 하드코딩 / 총계)
AUD-014  수량산출서 ↔ 내역서 수량 대조

실무자가 매번 전자계산기로 하던 검산을 대신한다.
감사 지적 원문: "각 내역별 소계 및 합계는 전자계산기로 수계산하여 확인 (엑셀의 오류 방지)"
"""
from __future__ import annotations

import streamlit as st

from engine import boq, verify

st.set_page_config(page_title="내역서 검증", page_icon="◫", layout="wide")

st.markdown("""
<style>
:root{ --ink:#1B3A5C; --ink2:#48657E; --brick:#8E2F21; --brickbg:#F7EBE8;
       --rule:#CDD4D9; --okbg:#EAF0F3; }
.block-container{padding-top:2.2rem;max-width:1180px}
.trap{border-left:3px solid var(--brick);background:var(--brickbg);color:#6E241A;
      padding:10px 13px;margin:6px 0;font-size:13.5px;line-height:1.6}
.okline{border-left:3px solid #7B94A9;background:var(--okbg);color:#274156;
      padding:10px 13px;margin:6px 0;font-size:13.5px;line-height:1.6}
.small{font-size:12.5px;color:#6C7A85}
.kind{display:inline-block;font-family:ui-monospace,Menlo,monospace;font-size:11px;
      font-weight:600;background:var(--brick);color:#fff;padding:1px 6px;border-radius:3px;
      margin-right:6px}
</style>
""", unsafe_allow_html=True)

KIND_LABEL = {
    "R1": "행 금액 ≠ 수량 × 단가",
    "R2": "합계 ≠ 재료비 + 노무비 + 경비",
    "R3": "소계 ≠ 명세 행의 합",
    "R4": "SUM 수식 범위 누락",
    "R5": "수식이 아닌 하드코딩",
    "R6": "총계 ≠ 소계의 합",
    "Q1": "수량 불일치",
    "Q2": "내역서에만 있는 항목",
    "Q3": "수량산출서에만 있는 항목",
}

st.title("내역서 검증")
st.caption("소계·합계 검산과 수량 대조. 설계 단계에서 돌리면 감사 지적 두 건이 사라집니다.")

up = st.file_uploader("내역서 (.xlsx) — 수량산출서가 같은 파일에 있으면 함께 대조합니다", type=["xlsx"])

if not up:
    st.info(
        "샘플로 먼저 확인해 보세요.\n\n"
        "· `sample/sample_내역서_정상.xlsx` — 오류 없음. 검증기가 통과시켜야 합니다\n"
        "· `sample/sample_내역서_오류.xlsx` — 오류 6종을 심어 둔 파일"
    )
    st.stop()

data = up.getvalue()
try:
    sheets = boq.read_workbook(data)
except Exception as e:
    st.error(f"파일을 읽지 못했습니다: {e}")
    st.stop()

if not sheets:
    st.error("읽을 수 있는 시트가 없습니다.")
    st.stop()

names = [s.name for s in sheets]


def sheet_label(i: int) -> str:
    s = sheets[i]
    return f"{s.name}  (헤더 {s.header_row}행 · {s.n_rows}행)"


c1, c2 = st.columns(2)
bi = c1.selectbox("내역서 시트", range(len(sheets)), format_func=sheet_label,
                  index=next((i for i, n in enumerate(names) if "내역" in n), 0))
qi = c2.selectbox("수량산출서 시트 (없으면 '— 대조 안 함 —')",
                  [None] + list(range(len(sheets))),
                  format_func=lambda i: "— 대조 안 함 —" if i is None else sheet_label(i),
                  index=(next((i for i, n in enumerate(names) if "수량" in n), -1) + 1) or 0)

bs = sheets[bi]
qs = sheets[qi] if qi is not None else None


def mapping_ui(sh: boq.Sheet, roles: list[str], prefix: str) -> dict[str, int | None]:
    opts = [None] + [c.index for c in sh.columns]

    def label(i):
        if i is None:
            return "— 없음 —"
        c = sh.columns[i]
        return f"{c.letter}. {c.header[:26]}"

    def default(role):
        for c in sh.columns:
            if c.guess == role:
                return opts.index(c.index)
        return 0

    out: dict[str, int | None] = {}
    cols = st.columns(min(len(roles), 6))
    for n, role in enumerate(roles):
        with cols[n % len(cols)]:
            out[role] = st.selectbox(role, opts, index=default(role),
                                     format_func=label, key=f"{prefix}_{role}")
    return out


with st.expander("열 매핑 확인 · 수정", expanded=False):
    st.markdown("**내역서**")
    bmap = mapping_ui(bs, ["품명", "규격", "수량", "재료비단가", "재료비", "노무비단가"], "b1")
    bmap |= mapping_ui(bs, ["노무비", "경비단가", "경비", "합계"], "b2")
    if qs is not None:
        st.markdown("**수량산출서**")
        qmap = mapping_ui(qs, ["품명", "규격", "수량"], "q1")
    else:
        qmap = {}

missing = [r for r in ("재료비", "노무비") if bmap.get(r) is None]
if missing:
    st.warning(f"{', '.join(missing)} **금액** 열이 지정되지 않았습니다. 단가 열이 아니라 금액 열입니다.")

# ---------------------------------------------------------------- 실행
brep = verify.check_boq(data, bs.name, bmap, bs.header_row)
qrep = verify.check_quantity(bs, bmap, qs, qmap) if qs is not None else None
findings = verify.to_findings(brep, qrep)

k1, k2, k3, k4 = st.columns(4)
k1.metric("검산 건수", f"{brep.checked:,}건", f"명세 {brep.detail_rows}행 · 소계 {brep.subtotal_rows}개")
k2.metric("소계·합계 불일치", f"{len(brep.issues)}건",
          delta_color="inverse" if brep.issues else "off")
if qrep:
    k3.metric("수량 대조", f"{qrep.matched}/{qrep.boq_items} 일치",
              f"문제 {len(qrep.issues)}건" if qrep.issues else None,
              delta_color="inverse" if qrep.issues else "off")
else:
    k3.metric("수량 대조", "미실시")
total_issues = len(brep.issues) + (len(qrep.issues) if qrep else 0)
k4.metric("전체 지적 후보", f"{total_issues}건", delta_color="off")

for n in brep.notes:
    st.warning(n)

if total_issues == 0:
    st.success("검산과 대조 모두 통과했습니다.")

t1, t2, t3 = st.tabs(["AUD-030 소계·합계 검산", "AUD-014 수량 대조", "요약"])

with t1:
    if not brep.issues:
        st.markdown(f'<div class="okline">검산 {brep.checked}건 모두 일치합니다.</div>',
                    unsafe_allow_html=True)
    else:
        order = ["R6", "R5", "R4", "R3", "R2", "R1"]
        for kind in order:
            group = brep.of(kind)
            if not group:
                continue
            st.markdown(f"##### {KIND_LABEL[kind]}  ({len(group)}건)")
            rows = []
            for i in group:
                rows.append({
                    "셀": i.where, "항목": i.label,
                    "기댓값": f"{i.expected:,.0f}" if i.expected is not None else "-",
                    "실제값": f"{i.actual:,.0f}" if i.actual is not None else "-",
                    "차액": f"{i.diff:+,.0f}" if i.diff is not None else "-",
                    "내용": i.message,
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

        if brep.of("R5"):
            st.markdown('<div class="trap"><b>하드코딩된 합계가 있습니다.</b> '
                        '원본 수량이나 단가가 바뀌어도 이 값은 따라오지 않습니다. '
                        '설계변경 때 조용히 틀어지는 대표적인 경로입니다.</div>',
                        unsafe_allow_html=True)
        if brep.of("R4"):
            st.markdown('<div class="trap"><b>SUM 범위가 명세 블록을 덮지 못합니다.</b> '
                        '수식 오류가 아니라 값만 틀리므로 엑셀에서는 아무 경고도 뜨지 않습니다. '
                        '눈으로는 절대 못 잡는 유형입니다.</div>', unsafe_allow_html=True)

with t2:
    if qrep is None:
        st.info("수량산출서 시트를 선택하면 대조합니다.")
    elif not qrep.issues:
        st.markdown(f'<div class="okline">{qrep.matched}개 항목 수량이 모두 일치합니다.</div>',
                    unsafe_allow_html=True)
    else:
        st.caption(f"내역서 {qrep.boq_items}개 · 수량산출서 {qrep.qty_items}개 · 일치 {qrep.matched}개")
        for kind in ("Q1", "Q2", "Q3"):
            group = [i for i in qrep.issues if i.kind == kind]
            if not group:
                continue
            st.markdown(f"##### {KIND_LABEL[kind]}  ({len(group)}건)")
            st.dataframe([{
                "항목": i.label,
                "내역서": f"{i.actual:,g}" if i.actual is not None else "없음",
                "수량산출서": f"{i.expected:,g}" if i.expected is not None else "없음",
                "내용": i.message,
            } for i in group], use_container_width=True, hide_index=True)
        st.markdown('<div class="trap">품명과 규격이 조금씩 다르게 적혀 있으면 '
                    '다른 항목으로 잡힙니다. Q2·Q3에 같은 물건이 짝으로 올라와 있으면 '
                    '표기를 통일하세요. 감사 지적 원문도 "수량산출서의 순서를 내역서와 일치"입니다.</div>',
                    unsafe_allow_html=True)

with t3:
    for f in findings:
        cls = "trap" if not f.passed else "okline"
        st.markdown(
            f'<div class="{cls}"><b>{f.rule_id} · {f.name}</b><br>{f.message}'
            f'<div class="small" style="margin-top:6px">{f.citation}</div></div>',
            unsafe_allow_html=True)
    st.markdown("""
##### 검사 항목

| 코드 | 내용 | 왜 필요한가 |
|---|---|---|
| R1 | 행 금액 ≠ 수량 × 단가 | 셀 하나만 손으로 고치면 생긴다 |
| R2 | 합계 ≠ 재료비 + 노무비 + 경비 | 수식 복사 중 열이 빠진다 |
| R3 | 소계 ≠ 명세 행의 합 | 행 삽입 후 범위 미갱신 |
| R4 | SUM 범위 누락 | 엑셀이 경고하지 않는다. 눈으로 못 잡는다 |
| R5 | 하드코딩된 합계 | 원본이 바뀌어도 따라오지 않는다 |
| R6 | 총계 ≠ 소계의 합 | 원가계산서까지 그대로 흘러간다 |
| Q1 | 수량 불일치 | 설계변경 사유가 되지 않아 그대로 손실 |
| Q2·Q3 | 한쪽에만 있는 항목 | 산출 근거 없는 물량 = 지적 |
""")
    st.caption("근거 — 감사PPT p.25 「각 내역별 소계 및 합계는 전자계산기로 수계산하여 확인」, "
               "「수량산출서와 내역서의 수량이 일치하는지 확인」")
