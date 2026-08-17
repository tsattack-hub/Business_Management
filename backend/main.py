from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import boq, projects, specgen

app = FastAPI(title="구매설치 사업관리 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(boq.router)
app.include_router(specgen.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
