from fastapi import Depends, FastAPI, HTTPException

from .deps import get_diagnosis_service, get_graph_service, get_llm_service
from .schemas import (
    DiagnosisRequest,
    DiagnosisResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    HealthResponse,
)

app = FastAPI(title="Medical-Graph-RAG Backend", version="0.1.0")


@app.get("/api/health", response_model=HealthResponse)
def health_check(
    graph_service=Depends(get_graph_service),
    llm_service=Depends(get_llm_service),
) -> HealthResponse:
    neo4j_ok = graph_service.health_check()
    qwen_ok = llm_service.health_check()
    status = "ok" if neo4j_ok and qwen_ok else "degraded"
    return HealthResponse(
        status=status,
        neo4j="ok" if neo4j_ok else "error",
        qwen="ok" if qwen_ok else "error",
    )


@app.post("/api/graph/search", response_model=GraphSearchResponse)
def graph_search(
    request: GraphSearchRequest,
    graph_service=Depends(get_graph_service),
) -> GraphSearchResponse:
    keywords = [token.strip() for token in request.keywords.split(",") if token.strip()]
    result = graph_service.search_subgraph(keywords, request.hop, request.limit)
    return GraphSearchResponse(nodes=result["nodes"], links=result["links"])


@app.post("/api/diagnosis/suggestions", response_model=DiagnosisResponse)
def diagnosis_suggestions(
    request: DiagnosisRequest,
    diagnosis_service=Depends(get_diagnosis_service),
) -> DiagnosisResponse:
    result = diagnosis_service.get_suggestions(
        patient_info=request.patient_info,
        keywords=request.keywords,
        top_k=request.top_k,
    )

    if not result.get("diagnosis_suggestions"):
        raise HTTPException(status_code=502, detail="LLM returned no suggestions")

    return DiagnosisResponse(
        diagnosis_suggestions=result["diagnosis_suggestions"],
        diagnosis_chain=result["diagnosis_chain"],
    )
