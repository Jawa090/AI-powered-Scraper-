"""
RAG Service FastAPI Application
Implements CONTRACT.md v1
"""
from fastapi import FastAPI
from contextlib import asynccontextmanager
from RAG.settings import get_rag_settings

@asynccontextmanager
async def lifespan(app):
    app.state.settings = get_rag_settings(reload=True)
    yield

from RAG.api.routes import router

app = FastAPI(
    title="DataOps RAG Service",
    lifespan=lifespan,
    description="Dedicated microservice for document ingestion, vector storage, and semantic retrieval.",
    version="v1",
)

app.include_router(router)
