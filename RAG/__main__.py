"""
RAG Service Main Entrypoint
Run with: python -m RAG
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("RAG_PORT", "8001"))
    host = os.environ.get("RAG_HOST", "0.0.0.0")
    uvicorn.run("RAG.app:app", host=host, port=port)
