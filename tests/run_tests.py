"""
회귀 테스트 — pytest 없이 그냥 실행한다.

    python tests/run_tests.py

룰 YAML을 고친 뒤에는 반드시 한 번 돌려 보십시오.
기준금액을 바꾸면 여기 기대치도 함께 바꿔야 합니다.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services import audit, boq, docgen, guidance, specgen, store, verify  # noqa: E402
from backend.services.procedure import build_procedure, judge_contract_type        # noqa: E402
from backend.services.rules import load_rules, rule_index                          # noqa: E402
from backend.services.schedule import backward_schedule, load_calendar             # noqa: E402

PASS, FAIL = 0, 0


def check(label: str, got, want):
    global PASS, FAIL
    ok = got == want
    if ok:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}\n         기대 {want!r}\n         실제 {got!r}")


def approx(label: str, got: float, want: float, tol: float = 1.0):
    check(label + f" ({got:,.0f})", abs(got - want) <= tol, True)


# ---------------------------------------------------------------- 룰 로딩
print("\n[1] 룰 로딩")
rules = load_rules()
idx = rule_index(rules)
check("검증룰 45건", len(rules.get("검증룰", [])), 45)
check("구매설치 단계 6개", len(rules.get("단계", [])), 6)
check("MX-001 존재", "MX-001" in idx, True)
check("MX-001 미확정 표시", idx["MX-001"].get("status"), "unverified")

# ---------------------------------------------------------------- 계약유형
print("\n[2] 계약유형 판정 (MX-001)")
for mat, lab, exp, want_kind, want_boundary in [
    (210_000_000, 52_000_000, 18_000_000, "구매설치", False),   # 25.0%
    (104_000_000, 76_000_000, 20_000_000, "구매설치", True),    # 48.0% 경계
    (80_000_000, 100_000_000, 20_000_000, "공사계약", False),   # 60.0% — 경계 아님
    (100_000_000, 80_000_000, 20_000_000, "공사계약", True),    # 50.0% 정확히
    (0, 0, 0, "판정불가", False),
]:
    ct = judge_contract_type(mat, lab, exp)
    check(f"{mat:,}/{lab:,}/{exp:,} -> {want_kind}", ct.kind, want_kind)
    if ct.ratio is not None:
        check(f"   경계 판정", ct.boundary, want_boundary)

# ---------------------------------------------------------------- 절차
print("\n[3] 절차 인스턴스")
base = {
    "사업유형": "구매설치", "추정가격": 280_000_000, "고시금액": 230_000_000,
    "중기간경쟁제품": True, "CCTV설치": True, "품목": ["CCTV"],
    "설치작업있음": True, "시설물신축_증개축": False, "정보통신제품도입": True,
    "정화사업": False, "정보화사업": False, "소프트웨어포함": False, "방송장비": False,
    "관급자재있음": False, "제작품목있음": True, "선금신청": True,
    "일상감사대상": True, "산업안전보건관리비계상": True, "철거발생품있음": False,
    "계약변경발생": False, "납품기한연장신청": False, "계약방법": "제한경쟁",
    "낙찰방법": "계약이행능력심사", "설치공사금액": 70_000_000, "설치기간": "3개월",
}
proc = build_procedure(base)
check("활성 + 제외 = 52", len(proc.tasks) + len(proc.dropped), 52)
check("사전규격공개는 금액 무관 항상 활성", "T-P1-090" in proc.ids, True)
check("일상감사 활성", "T-P1-110" in proc.ids, True)
check("행정예고 활성 (CCTV)", "T-P1-075" in proc.ids, True)

no_cctv = build_procedure({**base, "CCTV설치": False, "품목": []})
check("CCTV 아니면 행정예고 제외", "T-P1-075" in no_cctv.ids, False)
check("CCTV 아니면 TTA 확인 제외", "T-P1-070" in no_cctv.ids, False)

small = build_procedure({**base, "추정가격": 50_000_000, "일상감사대상": False})
check("일상감사 비대상이면 태스크 제외", "T-P1-110" in small.ids, False)
check("그래도 사전규격공개는 남는다", "T-P1-090" in small.ids, True)

# ---------------------------------------------------------------- 근무일
print("\n[4] 근무일 계산")
cal = load_calendar()
check("공휴일 로드", len(cal.holidays) > 30, True)
check("미검증 공휴일 존재 (경고 대상)", len(cal.unverified) > 0, True)
check("2026-08-15 (광복절, 토) 비근무일", cal.is_workday(dt.date(2026, 8, 15)), False)
check("2026-08-17 (월) 근무일", cal.is_workday(dt.date(2026, 8, 17)), True)
# 9/1(화) -> 9/8(화): 9/2,3,4,7,8 = 5근무일
check("9/1 -> 9/8 근무일 5일", cal.count_business_days(dt.date(2026, 9, 1), dt.date(2026, 9, 8)), 5)
check("9/8 기준 7근무일 전", cal.minus_business_days(dt.date(2026, 9, 8), 7), dt.date(2026, 8, 28))

# ---------------------------------------------------------------- 역산
print("\n[5] 일정 역산")
sch = backward_schedule(
    dt.date(2026, 12, 20),
    {**base, "조달트랙_자체입찰": False, "보안성검토대상": True,
     "이행기간일": 90, "설계일수": 20, "보안성검토일": 21, "조달청소요일": 45},
    today=dt.date(2026, 8, 2), calendar=cal)
check("착수일이 목표일보다 앞", sch.start < sch.target, True)
check("2026-08-02 기준 실행 불가", sch.feasible, False)
check("행정예고가 병렬로 잡힘",
      any(s.label == "행정예고" and s.parallel for s in sch.steps), True)
check("조달청 트랙이면 입찰공고 제외",
      any(s.label == "입찰공고" for s in sch.steps), False)

sch2 = backward_schedule(
    dt.date(2027, 11, 30),
    {**base, "조달트랙_자체입찰": True, "보안성검토대상": False,
     "이행기간일": 60, "설계일수": 15, "조달청소요일": 0},
    today=dt.date(2026, 8, 2), calendar=cal)
check("자체입찰이면 입찰공고 포함",
      any(s.label == "입찰공고" for s in sch2.steps), True)
check("여유 있으면 실행 가능", sch2.feasible, True)

# ---------------------------------------------------------------- 검증룰
print("\n[6] Phase 1 검증룰")
actx = {**base, "설치비중": 0.25, "계약유형": "구매설치",
        "일상감사_해당사유": ["추정가격 2.8억 (DA-008)"],
        "일상감사의뢰일": dt.date(2026, 9, 1), "예정결재일": dt.date(2026, 9, 8),
        "사전공개완료일": dt.date(2026, 8, 25),
        "입찰참가_제한사유": ["중소기업"],
        "공사업종": "정보통신공사", "공사예정가격": 280_000_000,
        "직접구매대상품목": False, "직접구매품목_추정가격": 0,
        "총공사금액": 308_000_000, "목표준공일": dt.date(2026, 12, 20),
        "하자담보년수": 1, "예비품있음": True}
fs = {f.rule_id: f for f in audit.run_all(actx, proc, cal)}
check("11개 룰 실행", len(fs), 11)
check("AUD-033 회부 5근무일 -> 미통과", fs["AUD-033"].passed, False)
check("AUD-036 순서 정상 -> 통과", fs["AUD-036"].passed, True)
check("AUD-043 일치 -> 통과", fs["AUD-043"].passed, True)

bad = audit.run_all({**actx, "입찰참가_제한사유": ["실적", "기술보유"],
                     "추정가격": 90_000_000}, proc, cal)
bd = {f.rule_id: f for f in bad}
check("AUD-022 중복제한 위반 탐지", bd["AUD-022"].passed, False)
check("AUD-023 고시금액 미만 실적제한 탐지", bd["AUD-023"].passed, False)
check("AUD-023 심각도 blocker", bd["AUD-023"].severity, "blocker")

rev = audit.run_all({**actx, "사전공개완료일": dt.date(2026, 9, 5)}, proc, cal)
check("AUD-036 순서 역전 탐지",
      next(f for f in rev if f.rule_id == "AUD-036").passed, False)

wrong = audit.run_all({**actx, "낙찰방법": "적격심사"}, proc, cal)
check("AUD-043 낙찰기준 불일치 탐지",
      next(f for f in wrong if f.rule_id == "AUD-043").passed, False)

# ---------------------------------------------------------------- 내역서 파싱
print("\n[7] 내역서 파싱 (병합 헤더)")
data_ok = (ROOT / "sample/sample_내역서_정상.xlsx").read_bytes()
data_ng = (ROOT / "sample/sample_내역서_오류.xlsx").read_bytes()
sh = {s.name: s for s in boq.read_workbook(data_ok)}
bs, qs = sh["내역서"], sh["수량산출서"]
mp = {c.guess: c.index for c in bs.columns if c.guess}
check("재료비는 금액 열(F)", bs.columns[mp["재료비"]].letter, "F")
check("재료비단가는 E", bs.columns[mp["재료비단가"]].letter, "E")
check("노무비는 H", bs.columns[mp["노무비"]].letter, "H")
check("경비는 J", bs.columns[mp["경비"]].letter, "J")
check("합계는 K", bs.columns[mp["합계"]].letter, "K")

t = boq.aggregate(bs, mp)
approx("재료비 합계", t.material, 90_826_000)
approx("노무비 합계", t.labor, 26_878_000)
approx("경비 합계", t.expense, 6_910_000)
ct = judge_contract_type(t.material, t.labor, t.expense)
check("샘플은 구매설치", ct.kind, "구매설치")

# ---------------------------------------------------------------- Phase 2
print("\n[8] Phase 2 검증기")
qm = {c.guess: c.index for c in qs.columns if c.guess}
br = verify.check_boq(data_ok, "내역서", mp, bs.header_row)
qr = verify.check_quantity(bs, mp, qs, qm)
check("정상본 AUD-030 오탐 0", len(br.issues), 0)
check("정상본 AUD-014 오탐 0", len(qr.issues), 0)
check("검산이 실제로 수행됨", br.checked > 50, True)

sh2 = {s.name: s for s in boq.read_workbook(data_ng)}
bs2, qs2 = sh2["내역서"], sh2["수량산출서"]
mp2 = {c.guess: c.index for c in bs2.columns if c.guess}
qm2 = {c.guess: c.index for c in qs2.columns if c.guess}
br2 = verify.check_boq(data_ng, "내역서", mp2, bs2.header_row)
qr2 = verify.check_quantity(bs2, mp2, qs2, qm2)
kinds = {}
for i in list(br2.issues) + list(qr2.issues):
    kinds[i.kind] = kinds.get(i.kind, 0) + 1
print(f"       유형별 탐지: {kinds}")
for k in ("R1", "R2", "R3", "R4", "R5", "R6", "Q1", "Q2", "Q3"):
    check(f"{k} 탐지", kinds.get(k, 0) > 0, True)
check("R1 1건", kinds.get("R1"), 1)
check("Q1 2건 (수량 불일치)", kinds.get("Q1"), 2)

# ---------------------------------------------------------------- 주의사항
print("\n[9] 주의사항 수집")
p1 = [t for t in proc.tasks if t.stage_id == "P1"]
cau = guidance.stage_summary(p1)
check("P1 주의사항 수집됨", len(cau) > 3, True)
check("모두 실제 지적 사례", all(c.strong for c in cau), True)
t090 = proc.get("T-P1-090")
check("사전규격공개 주의사항 있음", len(guidance.cautions_for(t090)) > 0, True)

# ---------------------------------------------------------------- 서류 생성
print("\n[10] 서류 틀 생성")
import shutil, tempfile
tpls = docgen.load_templates()
check("서류 틀 13종", len(tpls), 13)
check("6개 단계 전부 커버",
      sorted({t.stage for t in tpls.values()}), ["P1", "P2", "P3", "P4", "P5", "P6"])

sample_proj = {
    "사업명": "테스트 사업", "연도": 2026, "공항": "김포공항",
    "부서": "통신부", "담당자": "홍길동", "추정가격": 280_000_000, "이행기간": 90,
    "물품분": 90_826_000, "설치분_노무": 26_878_000, "설치분_경비": 6_910_000,
    "계약유형": "구매설치", "조달트랙": "조달청 위탁", "낙찰방법": "계약이행능력심사",
}
tmp = Path(tempfile.mkdtemp())
made, failed = [], []
for tid in tpls:
    try:
        made.append(docgen.render(tid, sample_proj, tmp))
    except Exception as e:
        failed.append(f"{tid}: {type(e).__name__} {e}")
for f in failed:
    print("       " + f)
check("13종 전부 생성", len(made), 13)
check("생성 실패 0", len(failed), 0)
check("모두 파일로 존재", all(p.exists() and p.stat().st_size > 1000 for p in made), True)

ctx = docgen.build_context(sample_proj)
check("치환자 설치비중", ctx["설치비중"], "27.1%")
check("치환자 총설계금액", ctx["총설계금액"], "124,614,000원")
check("빈 값은 채우지 않음",
      docgen.build_context({"사업명": "x"})["물품분"], docgen.FILL_MARK)

txt = None
for p in made:
    if p.name.startswith("시행계획보고"):
        from hwpx.document import HwpxDocument
        txt = HwpxDocument.open(str(p)).export_text()
check("시행계획보고 생성됨", txt is not None, True)
if txt:
    for item in ["합법성 및 필요성", "타당성", "목적의 명확성", "추진 주체",
                 "재원 조달", "원가계산", "계약방법", "목적 외 사용", "방만 경영"]:
        check(f"   일상감사 중점검토 '{item}' 포함", item in txt, True)
shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------- 저장
print("\n[11] 사업 저장·불러오기")
import datetime as _dt
saved = {**store.blank(), "사업명": "저장테스트 사업", "추정가격": 1234,
         "완료태스크": {"T-P1-010", "T-P1-020"}, "목표준공일": _dt.date(2026, 12, 20)}
pid = store.save(saved)
back = store.load(pid)
check("사업명 왕복", back["사업명"], "저장테스트 사업")
check("완료태스크 왕복", back["완료태스크"], {"T-P1-010", "T-P1-020"})
check("날짜 왕복", back["목표준공일"], _dt.date(2026, 12, 20))
store.delete(pid)
check("삭제됨", pid not in [x[0] for x in store.list_projects()], True)

# ---------------------------------------------------------------- 규격서
print("\n[12] 구매규격서 초안")
groups = {g.id: g for g in specgen.item_groups()}
check("품목군 4개", len(groups), 4)
check("CCTV 규격항목 7개", len(groups["CCTV"].spec_fields), 7)

sp = {"사업명": "테스트 CCTV 구매설치", "공항": "김포공항", "부서": "통신부",
      "담당자": "홍길동", "추정가격": 280_000_000, "이행기간": 90, "설치작업있음": True}
vals = {"해상도": "400만 화소", "프레임": "30fps", "저장기간": "30일",
        "압축방식": "H.265", "카메라수량": "고정형 18대", "방진방수": "IP66",
        "동작온도": "-30 ~ +50℃"}
d = specgen.build_draft("CCTV", sp, vals)
check("조항 17개", d.clause_count, 17)
check("6개 절 구성", [n for n, _, _ in d.sections], [1, 2, 3, 4, 5, 6])
body = specgen.to_text(d)
check("사업명 치환", "테스트 CCTV 구매설치" in body, True)
check("규격 수치 치환 (해상도)", "400만 화소 이상" in body, True)
check("규격 수치 치환 (수량)", "고정형 18대" in body, True)
check("미입력 항목은 빈칸 유지", any("연동 대상" in b for _, b in d.blanks), True)
check("오탐 없음 (표준 규격·모델 등)", len(d.brand_hits), 0)

d2 = specgen.build_draft("CCTV", sp, {})
check("수치 미입력 시 빈칸 늘어남", len(d2.blanks) > len(d.blanks), True)

nosafety = specgen.build_draft("CCTV", {**sp, "설치작업있음": False}, vals)
check("설치작업 없으면 안전관리 조항 제외",
      nosafety.clause_count, d.clause_count - 1)

hits = specgen.scan_text(
    "가. 카메라는 한화비전 XNO-8080R 또는 동등 이상으로 한다.\n"
    "나. 스위치는 Cisco 정품 제품으로 한다.\n"
    "다. 전원은 PoE (IEEE 802.3af) 및 H.265, IP66을 지원한다.")
terms = {h.term for h in hits}
check("상표 '한화비전' 탐지", "한화비전" in terms, True)
check("모델번호 'XNO-8080R' 탐지", "XNO-8080R" in terms, True)
check("상표 'Cisco' 탐지", "Cisco" in terms, True)
check("유도표현 '정품 제품' 탐지", "정품 제품" in terms, True)
check("표준 규격 오탐 없음 (IEEE/H.265/IP66)",
      any(t.startswith(("IEEE", "H.26", "IP6")) for t in terms), False)
check("완화문구 인식", any(h.mitigated for h in hits if h.term == "한화비전"), True)

import tempfile as _tf
_o = Path(_tf.mkdtemp())
_p = specgen.render(d, sp, _o)
check("hwpx 생성", _p.exists() and _p.stat().st_size > 5000, True)
shutil.rmtree(_o, ignore_errors=True)

# ---------------------------------------------------------------- 조달청 API
print("\n[13] 조달청 API 클라이언트 (모의)")
from unittest.mock import MagicMock, patch                            # noqa: E402

from backend.services import harvest as H                                       # noqa: E402
from backend.services.g2b import (G2BClient, G2BError, classify, is_spec_file,  # noqa: E402
                                  load_conf, parse_record, preferred_org)

gconf = load_conf()
check("엔드포인트 설정됨", "HrcspSsstndrdInfoService" in gconf["api"]["base"], True)
check("필드명 미확정 표시", gconf["api"]["status"], "unverified")
check("요청 간 대기 설정", gconf["api"]["throttle_sec"] > 0, True)
check("다운로드 상한 설정", gconf["collect"]["max_files_per_run"] > 0, True)

FAKE = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
        "body": {"totalCount": 2, "numOfRows": 100, "pageNo": 1, "items": [
            {"bfSpecRgstNo": "20260100123-00",
             "prdctClsfcNoNm": "OO공항 영상감시장치 구매설치",
             "rcptDt": "20260115", "dminsttNm": "한국공항공사",
             "asignBdgtAmt": "280000000", "prdctSpecNm": "IP 카메라 24대",
             "specDocFileNm1": "구매규격서.hwpx",
             "specDocFileUrl1": "https://example.invalid/a.hwpx",
             "specDocFileNm2": "입찰공고문.pdf",
             "specDocFileUrl2": "https://example.invalid/b.pdf",
             "신규필드": "값"},
            {"bfSpecRgstNo": "20260100124-00", "prdctClsfcNoNm": "OO역사 조명설비 교체",
             "dminsttNm": "철도공사", "asignBdgtAmt": "90000000"}]}}}

n1 = parse_record(FAKE["response"]["body"]["items"][0], gconf)
check("등록번호 파싱", n1.등록번호, "20260100123-00")
check("예산 정수 변환", n1.budget, 280_000_000)
check("첨부 2개 파싱", len(n1.파일), 2)
check("품목군 분류 CCTV", classify(n1, gconf), "CCTV")
check("선호기관 판정", preferred_org(n1, gconf), True)
check("규격서 파일 판정", is_spec_file("구매규격서.hwpx", gconf), True)
check("공고문은 제외", is_spec_file("입찰공고문.pdf", gconf), False)

n2 = parse_record(FAKE["response"]["body"]["items"][1], gconf)
check("무관한 품목은 분류 안 됨", classify(n2, gconf), None)

with patch("requests.Session.get") as g:
    g.return_value = MagicMock(status_code=200, json=lambda: FAKE)
    pr = G2BClient("dummy").probe()
check("probe 총건수", pr["total"], 2)
check("probe 필드 매핑", pr["매핑결과"]["등록번호"], "bfSpecRgstNo")
check("probe 미사용 키 보고", "신규필드" in pr["미매핑키"], True)

for code, frag in (("30", "인증키"), ("22", "트래픽")):
    with patch("requests.Session.get") as g:
        g.return_value = MagicMock(
            status_code=200,
            json=lambda c=code: {"response": {"header": {
                "resultCode": c, "resultMsg": "ERROR"}}})
        try:
            G2BClient("k").probe()
            check(f"오류 {code} 예외 발생", False, True)
        except G2BError as e:
            check(f"오류 {code} 안내 포함", frag in str(e), True)

try:
    G2BClient("")
    check("빈 인증키 거부", False, True)
except G2BError:
    check("빈 인증키 거부", True, True)

# ---------------------------------------------------------------- 조항 추출
print("\n[14] 규격서 텍스트 추출 · 조항 분해")
_t = Path(tempfile.mkdtemp())
_sp = {"사업명": "OO공항 CCTV 구매설치", "공항": "OO공항", "부서": "통신부",
       "담당자": "홍", "추정가격": 280_000_000, "이행기간": 90, "설치작업있음": True}
_d = specgen.build_draft("CCTV", _sp, {
    "해상도": "200만 화소", "프레임": "30fps", "저장기간": "30일", "압축방식": "H.265",
    "카메라수량": "24대", "방진방수": "IP66", "동작온도": "-30~50℃"})
_f = specgen.render(_d, _sp, _t)
_text, _how = H.extract_text(_f)
check("hwpx 추출 방법", _how, "hwpx")
check("hwpx 추출 내용 있음", len(_text) > 1000, True)

_cl = H.split_clauses(_text, "규격서.hwpx", org="한국공항공사", notice="X")
check("조항 17개 복구", len(_cl), 17)
_got = {c.title: c.section for c in _cl}
for _title, _sec in (("적용범위", 1), ("관련 규격 및 기준", 1), ("네트워크 카메라", 2),
                     ("개인영상정보 보호", 2), ("시험성적서", 3), ("검수", 4),
                     ("하자담보 책임", 5), ("기술지원 및 교육", 5), ("안전관리", 6)):
    check(f"   '{_title}' -> {_sec}절", _got.get(_title), _sec)
check("본문에 항목이 보존됨",
      "한국산업표준(KS)" in _got and False or
      "한국산업표준(KS)" in next(c.body for c in _cl if c.title == "관련 규격 및 기준"), True)

_flat = ("제1조 적용범위\n본 규격서는 물품 구매에 적용한다. 세부는 지시에 따른다.\n"
         "제2조 기술규격\n가. 정격용량 : 100kVA\n나. 백업시간 : 30분 이상\n"
         "제3조 제출서류\n가. 시험성적서 1부\n나. 취급설명서 1부\n"
         "제4조 하자보증\n검수완료일로부터 1년간 무상보증한다. 24시간 내 조치한다.")
_fc = {c.title: c.section for c in H.split_clauses(_flat, "flat.hwp", min_body=20)}
check("제N조 형식 4개 인식", len(_fc), 4)
check("   제2조 기술규격 -> 2절", _fc.get("기술규격"), 2)
check("   제4조 하자보증 -> 5절", _fc.get("하자보증"), 5)

check("미지원 형식은 사유 반환", H.extract_text(_t / "none.zip")[0], "")

_e = _cl[0].as_yaml_entry(1)
check("YAML 항목 출처가 '수집'", _e["출처"], "수집")
check("YAML 항목에 수집출처 기록", _e["수집출처"]["기관"], "한국공항공사")
shutil.rmtree(_t, ignore_errors=True)

# 레거시 .hwp — 업로드 파일이 있으면
_legacy = Path("/mnt/user-data/uploads/사업집행_및_계획시_관리절차내용-1.hwp")
if _legacy.exists():
    _lt, _lh = H.extract_text(_legacy)
    check("레거시 .hwp 추출", _lh, "hwp")
    check("레거시 .hwp 내용 있음", len(_lt) > 10000, True)

# ---------------------------------------------------------------- 결과
print(f"\n{'='*56}\n통과 {PASS}  실패 {FAIL}\n{'='*56}")
sys.exit(1 if FAIL else 0)
