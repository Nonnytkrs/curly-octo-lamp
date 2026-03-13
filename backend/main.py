import os
from pathlib import Path
from contextlib import contextmanager

from dotenv import load_dotenv
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv()

app = FastAPI(title="Thai Quiz Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class StartQuizRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=40)


class StartQuizResponse(BaseModel):
    nickname: str
    start_count: int


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return database_url


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
INDEX_FILE = PROJECT_ROOT / "index.html"


@contextmanager
def get_conn():
    conn = psycopg.connect(get_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_users (
                id SERIAL PRIMARY KEY,
                nickname TEXT NOT NULL UNIQUE,
                start_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def serve_index():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return {"message": "index.html not found"}


@app.get("/health")
def health():
    try:
        get_database_url()
        return {"status": "ok", "database_url_set": True}
    except RuntimeError:
        return {"status": "error", "database_url_set": False}


@app.post("/api/start-quiz", response_model=StartQuizResponse)
def start_quiz(payload: StartQuizRequest):
    nickname = payload.nickname.strip()

    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname is required")

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO quiz_users (nickname, start_count, updated_at)
            VALUES (%s, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (nickname)
            DO UPDATE
            SET start_count = quiz_users.start_count + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (nickname,),
        )

        row = conn.execute(
            """
            SELECT nickname, start_count
            FROM quiz_users
            WHERE nickname = %s
            """,
            (nickname,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=500, detail="User could not be loaded")

    print("QUIZ START:", row)

    return StartQuizResponse(
        nickname=row[0],
        start_count=row[1],
    )
