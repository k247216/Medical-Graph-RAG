from functools import lru_cache

from .config import Settings
from .services.diagnosis_service import DiagnosisService
from .services.graph_service import GraphService
from .services.llm_service import LlmService


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_graph_service() -> GraphService:
    return GraphService(get_settings())


@lru_cache
def get_llm_service() -> LlmService:
    return LlmService(get_settings())


@lru_cache
def get_diagnosis_service() -> DiagnosisService:
    return DiagnosisService(get_graph_service(), get_llm_service())
