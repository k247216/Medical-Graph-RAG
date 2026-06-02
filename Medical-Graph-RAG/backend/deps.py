from .config import Settings

_settings: Settings | None = None
_graph_service = None
_llm_service = None
_diagnosis_service = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


async def get_graph_service():
    global _graph_service
    if _graph_service is None:
        from .services.graph_service import GraphService

        _graph_service = GraphService(get_settings())
    return _graph_service


async def get_llm_service():
    global _llm_service
    if _llm_service is None:
        from .services.llm_service import LlmService

        _llm_service = LlmService(get_settings())
    return _llm_service


async def get_diagnosis_service():
    global _diagnosis_service
    if _diagnosis_service is None:
        from .services.diagnosis_service import DiagnosisService

        graph_svc = await get_graph_service()
        llm_svc = await get_llm_service()
        _diagnosis_service = DiagnosisService(graph_svc, llm_svc)
    return _diagnosis_service
