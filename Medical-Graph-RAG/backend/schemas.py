from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GraphSearchRequest(BaseModel):
    keywords: str = Field(..., min_length=1)
    hop: int = Field(default=2, ge=1, le=3)
    limit: int = Field(default=30, ge=1, le=200)


class GraphNode(BaseModel):
    id: str
    label: str
    name: str
    properties: dict[str, Any]


class GraphLink(BaseModel):
    source: str
    target: str
    label: str
    properties: dict[str, Any]


class GraphSearchResponse(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


class DiagnosisRequest(BaseModel):
    patient_info: str = Field(..., min_length=1)
    keywords: str = Field(..., min_length=1)
    top_k: int = Field(default=20, ge=1, le=200)


class DiagnosisSuggestion(BaseModel):
    diagnosis: str
    confidence: str
    evidence: str


class DiagnosisChain(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]
    summary: str


class DiagnosisResponse(BaseModel):
    diagnosis_suggestions: List[DiagnosisSuggestion]
    diagnosis_chain: DiagnosisChain


class HealthResponse(BaseModel):
    status: str
    neo4j: str
    qwen: str

    model_config = ConfigDict(extra="ignore")
