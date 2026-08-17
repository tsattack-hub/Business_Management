"""
조달청 사전규격 수집 CLI

    # 0. 최초 1회 — 실제 응답 필드명 확인 (필수)
    python scripts/collect.py probe --key 발급받은키

    # 1. 목록만 조회 (파일 다운로드 없음, 부하 거의 없음)
    python scripts/collect.py list --key 키 --days 90 --group CCTV

    # 2. 규격서 파일 수집 + 조항 추출
    python scripts/collect.py harvest --key 키 --days 90 --group CCTV --max 30

    # 3. 추출한 조항을 라이브러리에 넣을 형태로 내보내기
    python scripts/collect.py export --in 수집결과/clauses.json

인증키는 --key 로 주거나 환경변수 G2B_KEY 에 넣으십시오.
    PowerShell:  $env:G2B_KEY="발급받은키"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml                                                          # noqa: E402

from backend.services import harvest as H                                      # noqa: E402
from backend.services.g2b import (G2BClient, G2BError, classify,               # noqa: E402
                                  load_conf, preferred_org)

OUT = ROOT / "수집결과"


def get_key(args) -> str:
    key = args.key or os.environ.get("G2B_KEY", "")
    if not key:
        sys.exit("인증키가 없습니다.  --key 로 주거나 환경변수 G2B_KEY 에 넣으십시오.\n"
                 "발급: https://www.data.go.kr/data/15129437/openapi.do")
    return key


# ---------------------------------------------------------------- probe
def cmd_probe(args) -> None:
    c = G2BClient(get_key(args))
    print("조달청 사전규격정보서비스 — 응답 필드 확인\n")
    try:
        r = c.probe(business=args.business, days=args.days)
    except G2BError as e:
        sys.exit(f"실패: {e}")

    if r.get("note"):
        print(r["note"])
        return

    print(f"기간 내 총 {r['total']:,}건\n")
    print("필드 매핑 결과")
    miss = []
    for name, hit in r["매핑결과"].items():
        if hit:
            print(f"  OK   {name:12s} <- {hit}")
        else:
            print(f"  ??   {name:12s} <- 찾지 못함")
            miss.append(name)

    if r["미매핑키"]:
        print(f"\n응답에는 있으나 우리가 안 쓰는 키 {len(r['미매핑키'])}개")
        for k in r["미매핑키"]:
            v = str(r["sample"].get(k, ""))[:50]
            print(f"     {k:28s} = {v}")

    if miss:
        print("\n──────────────────────────────────────────────")
        print("찾지 못한 필드가 있습니다. 위 '안 쓰는 키' 목록에서")
        print("해당하는 이름을 골라 docs/g2b_api.yaml 의")
        print("fields.<이름>.candidates 맨 앞에 추가하십시오.")
        print("──────────────────────────────────────────────")
    else:
        print("\n모든 필드가 매핑되었습니다. 수집을 시작할 수 있습니다.")

    OUT.mkdir(exist_ok=True)
    (OUT / "probe.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n원본 응답 저장: {OUT / 'probe.json'}")


# ---------------------------------------------------------------- list
def _collect_notices(c: G2BClient, conf: dict, args) -> list:
    end = dt.date.today()
    begin = end - dt.timedelta(days=args.days)
    print(f"조회 기간 {begin} ~ {end}  ({args.business})")

    picked, seen = [], 0
    for n in c.iter_notices(args.business, begin, end, keyword=args.keyword):
        seen += 1
        g = classify(n, conf)
        if args.group and g != args.group:
            continue
        if not args.group and g is None:
            continue
        if args.only_preferred and not preferred_org(n, conf):
            continue
        n.품목군 = g
        picked.append(n)
        if seen % 200 == 0:
            print(f"  ... 조회 {seen}건, 선별 {len(picked)}건")
    print(f"조회 {seen}건 -> 선별 {len(picked)}건\n")
    return picked


def cmd_list(args) -> None:
    conf = load_conf()
    c = G2BClient(get_key(args), conf)
    try:
        picked = _collect_notices(c, conf, args)
    except G2BError as e:
        sys.exit(f"실패: {e}")

    for n in picked[: args.show]:
        b = f"{n.budget:,}원" if n.budget else "-"
        files = len(n.파일)
        print(f"  [{getattr(n, '품목군', '?'):8s}] {(n.사업명 or '')[:44]:46s} "
              f"{b:>16s}  첨부{files}  {n.수요기관 or ''}")
    if len(picked) > args.show:
        print(f"  ... 외 {len(picked) - args.show}건")

    OUT.mkdir(exist_ok=True)
    dest = OUT / "notices.json"
    dest.write_text(json.dumps(
        [{"등록번호": n.등록번호, "사업명": n.사업명, "수요기관": n.수요기관,
          "배정예산": n.budget, "공개일자": n.공개일자,
          "품목군": getattr(n, "품목군", None), "파일": n.파일}
         for n in picked], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {dest}")
    print("파일까지 받으려면:  python scripts/collect.py harvest --key ... --group CCTV")


# ---------------------------------------------------------------- harvest
def cmd_harvest(args) -> None:
    conf = load_conf()
    if args.max:
        conf["collect"]["max_files_per_run"] = args.max
    c = G2BClient(get_key(args), conf)
    try:
        picked = _collect_notices(c, conf, args)
    except G2BError as e:
        sys.exit(f"실패: {e}")

    if not picked:
        sys.exit("선별된 건이 없습니다. --days 를 늘리거나 --group 을 바꿔 보십시오.")

    cap = conf["collect"]["max_files_per_run"]
    print(f"규격서 파일 수집 시작 (상한 {cap}건, 요청 간 "
          f"{conf['collect']['download_throttle_sec']}초 대기)\n")

    def prog(i, total, name):
        print(f"  [{i}/{total}] {name[:60]}")

    OUT.mkdir(exist_ok=True)
    res = H.harvest(picked, conf, OUT, session=c.s, progress=prog)
    print(f"\n{res.summary}")

    for f in res.failures[:10]:
        print(f"  실패: {f}")

    dest = OUT / "clauses.json"
    dest.write_text(json.dumps(
        [{"제목": x.title, "절": x.section, "본문": x.body,
          "파일": x.source_file, "기관": x.source_org, "사전규격": x.source_notice}
         for x in res.clauses], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n조항 저장: {dest}")

    if res.clauses:
        from collections import Counter
        cnt = Counter(x.section for x in res.clauses)
        print("절별 조항 수:", dict(sorted(cnt.items())))
        print("\n표본:")
        for x in res.clauses[:3]:
            print(f"  [{x.section}절] {x.title}")
            print("      " + x.body[:120].replace("\n", " ") + " ...")
    print("\n라이브러리에 넣을 형태로 바꾸려면:  python scripts/collect.py export")


# ---------------------------------------------------------------- export
def cmd_export(args) -> None:
    src = Path(args.inp) if args.inp else OUT / "clauses.json"
    if not src.exists():
        sys.exit(f"파일이 없습니다: {src}\n먼저 harvest 를 실행하십시오.")
    data = json.loads(src.read_text(encoding="utf-8"))

    entries = []
    for i, c in enumerate(data, 1):
        entries.append({
            "id": f"HARV-{i:04d}",
            "절": c["절"],
            "제목": c["제목"],
            "출처": "수집",
            "본문": c["본문"],
            "수집출처": {"기관": c.get("기관") or "미확인",
                        "사전규격": c.get("사전규격") or "미확인",
                        "파일": c.get("파일") or "미확인"},
        })

    OUT.mkdir(exist_ok=True)
    dest = OUT / "수집조항.yaml"
    header = (
        "# 수집한 조항 후보\n"
        "# ----------------------------------------------------------------\n"
        "# ★ 그대로 쓰지 마십시오.\n"
        "#   다른 기관 규격서에는 그 기관 사정에 맞춘 조건이 섞여 있습니다.\n"
        "#   특정 제조사 모델, 그 기관만의 인증 요구, 지역 조건 등을 그대로\n"
        "#   옮기면 부당한 입찰 제한이 되고 감사 지적 사유입니다 (AUD-013).\n"
        "#\n"
        "# 검토 후 쓸 것만 docs/spec_clauses.yaml 의 품목조항 또는 공통조항으로\n"
        "# 옮기고, 그때 '출처'를 수집 -> 관행 또는 표준으로 올리십시오.\n"
        "# ----------------------------------------------------------------\n\n"
    )
    dest.write_text(
        header + yaml.dump({"수집조항": entries}, allow_unicode=True,
                           sort_keys=False, width=100),
        encoding="utf-8")
    print(f"조항 {len(entries)}개 -> {dest}")
    print("\n검토 후 쓸 것만 docs/spec_clauses.yaml 로 옮기십시오.")


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="조달청 사전규격 수집")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--key", help="공공데이터포털 인증키 (없으면 G2B_KEY 환경변수)")
        p.add_argument("--business", default="물품",
                       choices=["물품", "용역", "공사", "외자"])

    p = sub.add_parser("probe", help="응답 필드명 확인 (최초 1회 필수)")
    common(p)
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=cmd_probe)

    for name, fn, help_ in (("list", cmd_list, "목록만 조회"),
                            ("harvest", cmd_harvest, "규격서 파일 수집 + 조항 추출")):
        p = sub.add_parser(name, help=help_)
        common(p)
        p.add_argument("--days", type=int, default=90)
        p.add_argument("--group", choices=["CCTV", "NETWORK", "POWER"],
                       help="품목군 필터")
        p.add_argument("--keyword", help="사업명 키워드 (API 검색조건)")
        p.add_argument("--only-preferred", action="store_true",
                       help="선호기관(공항공사 등)만")
        p.add_argument("--show", type=int, default=30)
        if name == "harvest":
            p.add_argument("--max", type=int, help="다운로드 상한 (기본 50)")
        p.set_defaults(func=fn)

    p = sub.add_parser("export", help="조항을 라이브러리 형태로 내보내기")
    p.add_argument("--in", dest="inp", help="clauses.json 경로")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
