# CLAUDE.md

구매설치사업을 단계별로 관리하고, 단계별 서류 틀을 만들어 주며, 조심할 것을 알려주는 도구.
FastAPI(백엔드) + React/Vite(프론트엔드) 웹앱.

## 실행

```bat
run_web.bat            REM 백엔드+프론트 함께 실행 (Windows)
```

직접 실행:
- 백엔드: `python -m uvicorn backend.main:app --reload --port 8000`
- 프론트: `cd frontend && npm run start` → http://localhost:5173

## 구조

```
backend/
  main.py              FastAPI 앱 (CORS · 라우터 · /api/health)
  routers/
    projects.py        사업 CRUD · /analyze · 서류 생성(zip 포함)
    boq.py             내역서 검증 (/inspect, /check)
  services/            도메인 로직 (구 engine/)
    analysis.py        판정→절차→서류 구조 조립 (JSON 반환)
    rules.py procedure.py docgen.py guidance.py store.py
    boq.py verify.py schedule.py audit.py paths.py
frontend/src/
  App.jsx              상단 탭 2개
  components/ProjectPage.jsx   사업 절차관리
  components/BoqPage.jsx       내역서 검증
  services/api.js      axios, baseURL '/api'
rules/  docs/  data/   규정·서류틀·공휴일 YAML (자산)
projects/ 생성서류/     런타임 데이터 (gitignore)
tests/run_tests.py     회귀 테스트 (python tests/run_tests.py)
```

## 규칙

- **규정값은 코드에 없다.** `rules/*.yaml`, `docs/templates.yaml`, `data/*.yaml` 만 고친다.
- 모든 판정은 근거(citation)와 status(confirmed/unverified/inferred)를 달고 나온다.
  status가 confirmed가 아니면 화면에 경고가 붙는다 — 확정처럼 보이게 하지 말 것.
- 서류 빈칸은 지어내지 말고 「( 작성 필요 )」로 남긴다.
- 경로는 `backend/services/paths.py` 한 곳에서 관리 (저장소 루트 기준).
- 도메인/데이터를 바꾸면 `python tests/run_tests.py` 를 돌린다.
