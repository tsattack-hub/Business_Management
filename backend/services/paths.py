"""
경로 상수 한 곳 모음

backend/services/ 아래에서 저장소 루트를 기준으로 자산·런타임 폴더를 가리킨다.
자산(rules, docs, data)과 런타임 데이터(projects, 생성서류)는 저장소 루트에 둔다.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RULES_DIR = ROOT / "rules"
DOCS_DIR = ROOT / "docs"
DATA_DIR = ROOT / "data"

PROJ_DIR = ROOT / "projects"
OUT_DIR = ROOT / "생성서류"
