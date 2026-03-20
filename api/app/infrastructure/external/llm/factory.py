from app.domain.external.llm import LLM
from app.domain.models.app_config import LLMProviderConfig, LLMProviderType
from app.infrastructure.external.llm.gemini_llm import GeminiLLM
from app.infrastructure.external.llm.openai_llm import OpenAILLM


def build_llm(provider_config: LLMProviderConfig) -> LLM:
    if provider_config.provider == LLMProviderType.GEMINI3:
        return GeminiLLM(provider_config)

    if provider_config.provider in {LLMProviderType.CLAUDE, LLMProviderType.OPENAI_COMPATIBLE}:
        return OpenAILLM(provider_config)

    return OpenAILLM(provider_config)
