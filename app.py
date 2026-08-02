"""
구매설치 사업관리

하는 일 세 가지
  1. 단계별로 무엇을 해야 하는지 안내하고 진행 상태를 관리한다
  2. 각 단계에서 작성해야 할 서류를 알려주고, 틀을 만들어 준다
  3. 각 단계에서 조심할 것을 알려준다

실행:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile
from pathlib import Path

import streamlit as st

from engine import docgen, guidance, store
from engine.procedure import build_procedure, judge_contract_type, judge_procurement_track

st.set_page_config(page_title="구매설치 사업관리", page_icon="◧", layout="wide")

st.markdown("""
<style>
:root{ --ink:#1B3A5C; --ink2:#48657E; --brick:#8E2F21; --brickbg:#F7EBE8;
       --rule:#CDD4D9; --okbg:#EAF0F3; }
.block-container{padding-top:2rem;max-width:1120px}
h1,h2,h3{letter-spacing:-.01em}
.bar{border:1px solid var(--rule);border-radius:10px;padding:0;overflow:hidden;
     display:flex;background:#fff;margin-bottom:16px}
.bar .side{width:52px;flex:0 0 52px;background:var(--ink);color:#fff;display:flex;
     align-items:center;justify-content:center;writing-mode:vertical-rl;
     font-size:11px;letter-spacing:.2em;font-weight:600}
.bar .side.warn{background:var(--brick)}
.bar .body{padding:14px 18px;flex:1}
.bar .big{font-size:22px;font-weight:600;color:var(--ink)}
.bar .big.warn{color:var(--brick)}
.bar .sub{font-size:13px;color:var(--ink2);margin-top:2px}
.trap{border-left:3px solid var(--brick);background:var(--brickbg);color:#6E241A;
      padding:9px 12px;margin:5px 0;font-size:13px;line-height:1.6}
.tip{border-left:3px solid #7B94A9;background:var(--okbg);color:#274156;
      padding:9px 12px;margin:5px 0;font-size:13px;line-height:1.6}
.meta{font-size:12px;color:#6C7A85;margin:-6px 0 8px 30px}
.cite{font-size:11.5px;color:#8A959D}
.doc{font-size:13px;color:var(--ink);font-weight:600}
</style>
""", unsafe_allow_html=True)

STAGES = {
    "P1": "설계 — 규격서부터 계약의뢰까지",
    "P2": "입찰 · 계약",
    "P3": "착수 · 제작",
    "P4": "납품 · 설치",
    "P5": "준공 · 정산",
    "P6": "하자관리",
}


def won(v) -> str:
    try:
        return f"{int(v):,}원"
    except Exception:
        return "-"


# ================================================================ 사업 선택
st.sidebar.markdown("### 사업")
existing = store.list_projects()
choices = ["＋ 새 사업"] + [f"{n}" for _, n in existing]
pick = st.sidebar.selectbox("선택", range(len(choices)), format_func=lambda i: choices[i],
                            label_visibility="collapsed")

if "pid" not in st.session_state:
    st.session_state.pid = None

if pick == 0:
    if st.session_state.pid is not None:
        st.session_state.proj = store.blank()
        st.session_state.pid = None
    proj = st.session_state.setdefault("proj", store.blank())
else:
    pid = existing[pick - 1][0]
    if st.session_state.pid != pid:
        st.session_state.proj = store.load(pid)
        st.session_state.pid = pid
    proj = st.session_state.proj

# ================================================================ 입력
st.sidebar.markdown("### 기본 정보")
proj["사업명"] = st.sidebar.text_input("사업명", proj.get("사업명", ""))
c1, c2 = st.sidebar.columns(2)
proj["연도"] = c1.number_input("연도", 2024, 2032, int(proj.get("연도", dt.date.today().year)))
proj["공항"] = c2.text_input("공항", proj.get("공항", ""))
proj["부서"] = st.sidebar.text_input("주관부서", proj.get("부서", ""))
proj["담당자"] = st.sidebar.text_input("담당자", proj.get("담당자", ""))
proj["추정가격"] = st.sidebar.number_input("추정가격 (VAT 제외)", 0, step=1_000_000,
                                       value=int(proj.get("추정가격", 0)))
c3, c4 = st.sidebar.columns(2)
proj["이행기간"] = c3.number_input("이행기간(일)", 1, 720, int(proj.get("이행기간", 90)))
proj["목표준공일"] = c4.date_input("준공목표", proj.get("목표준공일", dt.date(int(proj["연도"]), 12, 20)))

st.sidebar.markdown("### 설계금액")
st.sidebar.caption("계약유형 판정에 쓰입니다")
proj["물품분"] = st.sidebar.number_input("재료비 (물품분)", 0, step=1_000_000,
                                      value=int(proj.get("물품분", 0)))
proj["설치분_노무"] = st.sidebar.number_input("직접노무비 (설치분)", 0, step=1_000_000,
                                         value=int(proj.get("설치분_노무", 0)))
proj["설치분_경비"] = st.sidebar.number_input("경비 (설치분)", 0, step=1_000_000,
                                         value=int(proj.get("설치분_경비", 0)))

st.sidebar.markdown("### 사업 조건")
st.sidebar.caption("체크한 것만 절차에 나타납니다")
for key, label in [
    ("설치작업있음", "설치작업 있음"), ("CCTV설치", "영상정보처리기기(CCTV)"),
    ("중기간경쟁제품", "중기간경쟁제품"), ("시설물신축_증개축", "시설물 신축·증개축"),
    ("정보통신제품도입", "정보통신제품 도입"), ("정보화사업", "정보화사업"),
    ("소프트웨어포함", "소프트웨어 포함"), ("방송장비", "방송장비"),
    ("관급자재있음", "관급자재 있음"), ("예비품있음", "예비품 입고"),
]:
    proj[key] = st.sidebar.checkbox(label, bool(proj.get(key, False)), key=f"cond_{key}")

proj["낙찰방법"] = st.sidebar.selectbox(
    "낙찰방법", ["계약이행능력심사", "협상에 의한 계약", "전자공개수의계약"],
    index=["계약이행능력심사", "협상에 의한 계약", "전자공개수의계약"].index(
        proj.get("낙찰방법", "계약이행능력심사")))

st.sidebar.divider()
if st.sidebar.button("저장", type="primary", use_container_width=True):
    if not proj.get("사업명"):
        st.sidebar.error("사업명을 입력하세요.")
    else:
        st.session_state.pid = store.save(proj)
        st.sidebar.success("저장했습니다.")
if st.session_state.pid and st.sidebar.button("삭제", use_container_width=True):
    store.delete(st.session_state.pid)
    st.session_state.pid = None
    st.session_state.proj = store.blank()
    st.rerun()

# ================================================================ 판정
st.title("구매설치 사업관리")

if not proj.get("사업명"):
    st.info("좌측에서 사업명을 입력하면 시작합니다. 설계금액 세 칸을 채우면 계약유형이 판정됩니다.")
    st.stop()

ct = judge_contract_type(proj["물품분"], proj["설치분_노무"], proj["설치분_경비"])
proj["계약유형"] = ct.kind

ctx = dict(proj)
ctx |= {
    "사업유형": "구매설치", "계약방법": "제한경쟁", "품목": ["CCTV"] if proj.get("CCTV설치") else [],
    "제작품목있음": True, "선금신청": True, "철거발생품있음": False,
    "계약변경발생": False, "납품기한연장신청": False,
    "산업안전보건관리비계상": proj.get("설치작업있음", False),
    "설치공사금액": proj["설치분_노무"] + proj["설치분_경비"],
    "설치기간": f"{proj['이행기간']}일",
    "일상감사대상": proj.get("추정가격", 0) > 100_000_000,
}
track = judge_procurement_track(ctx, dt.date(int(proj["연도"]), 1, 1))
proj["조달트랙"] = str(track.value)
proc = build_procedure(ctx)

pct = f"{ct.ratio*100:.1f}%" if ct.ratio is not None else "—"
warn = not ct.in_scope
st.markdown(f"""
<div class="bar">
  <div class="side {'warn' if warn else ''}">판 정</div>
  <div class="body">
    <div class="big {'warn' if warn else ''}">{ct.kind} · 설치비중 {pct}</div>
    <div class="sub">{proj['사업명']} · {track.value} · {proj['낙찰방법']} ·
        추정가격 {won(proj.get('추정가격'))}</div>
  </div>
</div>
""", unsafe_allow_html=True)

for n in ct.notes:
    st.markdown(f'<div class="trap">{n}</div>', unsafe_allow_html=True)
if ct.kind == "판정불가":
    st.stop()
if not ct.in_scope:
    st.warning("공사계약이므로 이 절차의 적용 범위를 벗어납니다.")
    st.stop()

done: set[str] = set(proj.get("완료태스크", set()))
total = len(proc.tasks)
st.progress(len(done & proc.ids) / total if total else 0.0,
            text=f"진행 {len(done & proc.ids)} / {total} 태스크")

# ================================================================ 단계별
tpls = docgen.load_templates()
by_stage = {}
for t in proc.tasks:
    by_stage.setdefault(t.stage_id, []).append(t)

out_root = store.out_dir(proj)

for sid, sname in STAGES.items():
    tasks = by_stage.get(sid, [])
    if not tasks:
        continue
    n_done = len([t for t in tasks if t.id in done])
    docs_here = [x for x in tpls.values() if x.stage == sid]

    with st.expander(f"**{sid[1]}. {sname}**  —  {n_done}/{len(tasks)} 완료 · 서류 {len(docs_here)}종",
                     expanded=(sid == "P1")):

        strong = guidance.stage_summary(tasks)
        if strong:
            st.markdown("###### 이 단계에서 조심할 것")
            for c in strong[:6]:
                st.markdown(
                    f'<div class="trap">{c.text}'
                    f'<div class="cite">{c.source} · {c.citation}</div></div>',
                    unsafe_allow_html=True)

        st.markdown("###### 할 일")
        for t in tasks:
            checked = st.checkbox(t.name, value=(t.id in done), key=f"t_{t.id}")
            if checked:
                done.add(t.id)
            else:
                done.discard(t.id)

            bits = []
            if t.deadline:
                bits.append(f"시점 {t.deadline}")
            if t.period:
                bits.append(f"주기 {t.period}")
            if t.documents:
                bits.append("징구 " + ", ".join(t.documents[:4])
                            + (" 외" if len(t.documents) > 4 else ""))
            if bits:
                st.markdown(f'<div class="meta">{" · ".join(bits)}</div>',
                            unsafe_allow_html=True)

        if docs_here:
            st.markdown("###### 작성할 서류")
            for d in docs_here:
                cols = st.columns([5, 2, 1.4])
                cols[0].markdown(
                    f'<div class="doc">{d.name} <span class="cite">· {d.fmt}</span></div>'
                    f'<div class="cite">{d.note}</div>', unsafe_allow_html=True)
                cols[1].markdown(f'<div class="cite">{d.citation}</div>',
                                 unsafe_allow_html=True)
                if cols[2].button("틀 만들기", key=f"g_{d.id}", use_container_width=True):
                    try:
                        p = docgen.render(d.id, proj, out_root)
                        st.session_state[f"made_{d.id}"] = str(p)
                    except Exception as e:
                        st.error(f"{d.name} 생성 실패: {e}")
                made = st.session_state.get(f"made_{d.id}")
                if made and Path(made).exists():
                    with open(made, "rb") as fh:
                        cols[2].download_button("내려받기", fh, file_name=Path(made).name,
                                                key=f"d_{d.id}", use_container_width=True)

proj["완료태스크"] = done

# ================================================================ 일괄 생성
st.divider()
c1, c2 = st.columns([1, 3])
with c1:
    if st.button("전체 서류 틀 한 번에 만들기", type="primary", use_container_width=True):
        made, failed = [], []
        for d in tpls.values():
            try:
                made.append(docgen.render(d.id, proj, out_root))
            except Exception as e:
                failed.append(f"{d.name}: {e}")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in made:
                z.write(p, arcname=p.name)
        st.session_state["zip"] = buf.getvalue()
        st.session_state["zipn"] = len(made)
        for f in failed:
            st.error(f)
with c2:
    if st.session_state.get("zip"):
        st.download_button(
            f"서류 {st.session_state['zipn']}종 내려받기 (zip)",
            st.session_state["zip"],
            file_name=f"{store.slug(proj['사업명'])}_서류틀.zip",
            mime="application/zip")
        st.caption(f"생성 위치: {out_root}")

st.caption(
    "한글 문서는 .hwpx 로 만들어집니다. .hwp 가 필요하면 한글에서 다른 이름으로 저장하세요.  ·  "
    "「( 작성 필요 )」로 표시된 곳은 사람이 판단해야 하는 항목이라 비워 두었습니다."
)
