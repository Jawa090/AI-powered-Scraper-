"""
RAG Service FastAPI Application
Implements CONTRACT.md v1
"""
from fastapi import FastAPI
from RAG.api.routes import router

app = FastAPI(
    title="DataOps RAG Service",
    description="Dedicated microservice for document ingestion, vector storage, and semantic retrieval.",
    version="v1",
)

app.include_router(router)
