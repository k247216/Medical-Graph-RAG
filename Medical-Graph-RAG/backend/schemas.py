from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Request models ──────────────────────────────────────────────

class GraphSearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1)
    hop: int = Field(default=2, ge=1, le=3)
    limit: int = Field(default=30, ge=1, le=200)
    layers: list[str] = Field(default=["bottom", "middle", "top"])
    reference_hops: int = Field(default=1, ge=0, le=3)


class DiagnosisRequest(BaseModel):
    patient_info: str = Field(..., min_length=1)
    keywords: str = Field(..., min_length=1)
    top_k: int = Field(default=20, ge=1, le=200)
    layers: list[str] = Field(default=["bottom", "middle", "top"])
    reference_hops: int = Field(default=1, ge=0, le=3)
    stream: bool = Field(default=False)


# ── Graph response sub-models ───────────────────────────────────

class GraphNode(BaseModel):
    id: str
    label: str
    name: str
    layer: Optional[str] = None
    gid: Optional[str] = None
    properties: dict[str, Any]


class GraphLink(BaseModel):
    source: str
    target: str
    label: str
    properties: dict[str, Any]


class SummaryItem(BaseModel):
    text: str
    gid: str


class GraphSearchResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    summary: List[SummaryItem] = []
    layerStats: dict[str, int] = {}


# ── Diagnosis response sub-models ───────────────────────────────

class DiagnosisSuggestion(BaseModel):
    diagnosis: str
    confidence: str
    evidence: str
    evidence_nodes: List[dict[str, Any]] = []
    evidence_paths: List[str] = []


class DiagnosisChain(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    summary: str


class DiagnosisResponse(BaseModel):
    diagnosis_suggestions: List[DiagnosisSuggestion]
    diagnosis_chain: DiagnosisChain
    graph_summary: List[SummaryItem] = []
    layer_stats: dict[str, int] = {}


class HealthResponse(BaseModel):
    status: str
    neo4j: str
    qwen: str

    model_config = ConfigDict(extra="ignore")


# ── Error models ────────────────────────────────────────────────

class ErrorCode(str, Enum):
    GRAPH_EMPTY = "GRAPH_EMPTY"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_PARSE_ERROR = "LLM_PARSE_ERROR"
    NEO4J_UNAVAILABLE = "NEO4J_UNAVAILABLE"
    INVALID_KEYWORDS = "INVALID_KEYWORDS"


class ErrorResponse(BaseModel):
    error_code: ErrorCode
    message: str
    detail: Optional[str] = None
