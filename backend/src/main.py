from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.grading import router as grading_router
from .storage import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="JCodeQuest Backend", lifespan=lifespan)
app.include_router(grading_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
