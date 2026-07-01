from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from pipeline import run_pipeline

app = FastAPI(title="BS Detector")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Liveness probe: reports the process is up and which model is configured.
    Does not call the LLM, so it is safe to poll (Docker healthcheck, load balancer)."""
    return {"status": "ok", "model": config.MODEL}


@app.post("/analyze")
async def analyze():
    """Run the multi-agent verification pipeline over the case file."""
    report = await run_pipeline()
    return {"report": report.model_dump()}
