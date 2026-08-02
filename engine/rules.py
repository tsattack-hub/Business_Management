"""
룰 로더 · 조건 평가기

설계 원칙
  · 규정값은 코드에 없다. rules/*.yaml 만 고친다.
  · 모든 판정 결과는 근거(citation)와 status(confirmed/unverified/inferred)를 달고 나온다.
  · status가 confirmed가 아니면 화면에 경고 배지가 붙는다.
"""
from __future__ import annotations

import datetime as dt
import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

# 구매설치 트랙에서 로드할 파일 (공사 템플릿 02는 참조용으로만 로드)
RULE_FILES = [
    "01_기준금액.yaml",
    "03_리드타임.yaml",
    "04_감사검증룰.yaml",
    "05_서식.yaml",
    "06_절차템플릿_구매설치.yaml",
    "07_기준금액_구매설치.yaml",
    "08_감사검증룰_구매설치.yaml",
    "09_서식_구매설치.yaml",
]

STATUS_LABEL = {
    "confirmed": "확정",
    "unverified": "미확정",
    "inferred": "추정",
}


# ---------------------------------------------------------------- 결과 객체
@dataclass
class Finding:
    """검증룰 판정 결과 한 건."""
    rule_id: str
    name: str
    severity: str               # blocker / error / warning / info
    passed: bool
    message: str
    citation: str = ""
    status: str = "confirmed"
    detail: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.status != "confirmed"


@dataclass
class Decision:
    """룰 적용 결과 (금액 판정 등)."""
    rule_id: str
    name: str
    value: Any
    citation: str = ""
    status: str = "confirmed"
    note: str = ""


# ---------------------------------------------------------------- 로더
@functools.lru_cache(maxsize=1)
def load_rules(rules_dir: str | None = None) -> dict[str, Any]:
    base = Path(rules_dir) if rules_dir else RULES_DIR
    merged: dict[str, Any] = {}
    for name in RULE_FILES:
        path = base / name
        if not path.exists():
            raise FileNotFoundError(f"룰 파일이 없습니다: {path}")
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, val in doc.items():
            if key == "schema_version":
                continue
            if key in merged and isinstance(merged[key], list) and isinstance(val, list):
                merged[key].extend(val)      # 델타 파일 병합 (검증룰, 서식)
            else:
                merged[key] = val
    return merged


def rule_index(rules: dict[str, Any]) -> dict[str, dict]:
    """id를 가진 모든 노드를 평면 인덱스로."""
    idx: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            rid = node.get("id")
            if isinstance(rid, str) and rid not in idx:
                idx[rid] = node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(rules)
    return idx


# ---------------------------------------------------------------- 조건 평가
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(일|주|개월|월|년)\s*$")

_UNIT_DAYS = {"일": 1, "주": 7, "개월": 30, "월": 30, "년": 365}


def _to_number(value: Any) -> Any:
    """'1개월' 같은 기간 문자열을 일수로 바꾼다. 그 외는 원본."""
    if isinstance(value, str):
        m = _DURATION.match(value)
        if m:
            return float(m.group(1)) * _UNIT_DAYS[m.group(2)]
    return value


_OPS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate(condition: Any, ctx: dict[str, Any]) -> bool:
    """
    YAML 조건식을 평가한다. 지원 형태:
        {always: true}
        {필드: 값}                 값 일치
        {필드: [값1, 값2]}          값이 목록 안에 있으면 참
        {필드: {">=": 100}}         비교
        {or: [조건, 조건]}          하나라도 참
        {and: [조건, 조건]}         모두 참
    컨텍스트에 없는 필드는 '조건 미충족'으로 본다(False).
    'or'/'and'/'always'/'제외'/'예외' 는 예약어.
    """
    if condition is None:
        return True
    if isinstance(condition, bool):
        return condition
    if isinstance(condition, list):
        return all(evaluate(c, ctx) for c in condition)
    if not isinstance(condition, dict):
        return bool(condition)

    if "always" in condition:
        return bool(condition["always"])
    if "or" in condition:
        return any(evaluate(c, ctx) for c in condition["or"])
    if "and" in condition:
        return all(evaluate(c, ctx) for c in condition["and"])

    for key, expected in condition.items():
        if key in ("제외", "예외", "산정단위", "업무", "포함업무", "비고"):
            continue
        if key not in ctx:
            return False
        actual = _to_number(ctx[key])
        if actual is None:
            return False

        if isinstance(expected, dict):
            for op, target in expected.items():
                fn = _OPS.get(op)
                if fn is None:
                    continue
                try:
                    if not fn(actual, _to_number(target)):
                        return False
                except TypeError:
                    return False
        elif isinstance(expected, list):
            if isinstance(actual, list):
                if not set(actual) & set(expected):
                    return False
            elif actual not in expected:
                return False
        else:
            if actual != _to_number(expected):
                return False
    return True


# ---------------------------------------------------------------- 시행일 선택
def pick_version(rule: dict, as_of: dt.date) -> tuple[dict | None, list[dict]]:
    """
    적용[] 배열에서 as_of 시점에 유효한 버전을 고른다.
    시행일이 null인 항목은 '시행일 미확인'이므로 후보로 함께 돌려주되
    자동 선택하지 않는다 → 호출부가 사용자에게 선택을 요구한다.
    반환: (선택된 버전 또는 None, 미확정 후보 목록)
    """
    versions = rule.get("적용") or []
    dated, undated = [], []
    for v in versions:
        raw = v.get("시행일")
        if raw is None:
            undated.append(v)
            continue
        d = raw if isinstance(raw, dt.date) else dt.date.fromisoformat(str(raw))
        if d <= as_of:
            dated.append((d, v))
    if dated:
        dated.sort(key=lambda x: x[0])
        return dated[-1][1], undated
    return None, undated


def citation_of(rule: dict) -> str:
    src = rule.get("근거")
    if isinstance(src, list):
        return " / ".join(str(s) for s in src)
    return str(src) if src else ""
