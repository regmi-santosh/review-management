from fastapi import FastAPI

from app.db import init_db
from app.routes import router

app = FastAPI(title="Review Management Dashboard")
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
