import json

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .deps import get_diagnosis_service, get_graph_service, get_llm_service
from .schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    ErrorCode,
    ErrorResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    HealthResponse,
)

app = FastAPI(title="Medical-Graph-RAG Backend", version="0.2.0")


@app.get("/api/health", response_model=HealthResponse)
async def health_check(
    graph_service=Depends(get_graph_service),
    llm_service=Depends(get_llm_service),
) -> HealthResponse:
    neo4j_ok = await graph_service.health_check()
    qwen_ok = await llm_service.health_check()
    status = "ok" if neo4j_ok and qwen_ok else "degraded"
    return HealthResponse(
        status=status,
        neo4j="ok" if neo4j_ok else "error",
        qwen="ok" if qwen_ok else "error",
    )


@app.post("/api/graph/search", response_model=GraphSearchResponse)
async def graph_search(
    request: GraphSearchRequest,
    graph_service=Depends(get_graph_service),
) -> GraphSearchResponse:
    keywords = [t.strip() for t in request.keywords.split(",") if t.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="No valid keywords provided")

    result = await graph_service.search_subgraph(
        keywords,
        request.hop,
        request.limit,
        layers=request.layers,
        reference_hops=request.reference_hops,
    )

    return GraphSearchResponse(
        nodes=result["nodes"],
        links=result["links"],
        summary=result.get("summary", []),
        layerStats=result.get("layerStats", {}),
    )


@app.post("/api/diagnosis/suggestions", response_model=DiagnosisResponse)
async def diagnosis_suggestions(
    request: DiagnosisRequest,
    diagnosis_service=Depends(get_diagnosis_service),
) -> DiagnosisResponse:
    result = await diagnosis_service.get_suggestions(
        patient_info=request.patient_info,
        keywords=request.keywords,
        top_k=request.top_k,
        layers=request.layers,
        reference_hops=request.reference_hops,
    )

    if not result.get("diagnosis_suggestions"):
        raise HTTPException(status_code=502, detail="LLM returned no suggestions")

    return DiagnosisResponse(
        diagnosis_suggestions=result["diagnosis_suggestions"],
        diagnosis_chain=result["diagnosis_chain"],
        graph_summary=result.get("graph_summary", []),
        layer_stats=result.get("layer_stats", {}),
    )


@app.post("/api/diagnosis/suggestions/stream")
async def diagnosis_suggestions_stream(
    request: DiagnosisRequest,
    diagnosis_service=Depends(get_diagnosis_service),
):
    if not request.keywords.strip():
        raise HTTPException(status_code=400, detail="No valid keywords provided")

    async def event_generator():
        async for payload in diagnosis_service.get_suggestions_stream(
            patient_info=request.patient_info,
            keywords=request.keywords,
            top_k=request.top_k,
            layers=request.layers,
            reference_hops=request.reference_hops,
        ):
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
