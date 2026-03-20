from app.domain.models.app_config import (
    BUILTIN_CLAUDE_PROVIDER_ID,
    BUILTIN_GEMINI3_PROVIDER_ID,
    LLMConfig,
    ensure_builtin_llm_providers,
)


def test_llm_config_migrates_legacy_single_provider_shape():
    llm_config = LLMConfig.model_validate({
        "base_url": "https://legacy.example.com/v1",
        "api_key": "legacy-key",
        "model_name": "legacy-model",
        "temperature": 0.2,
        "max_tokens": 1024,
        "vision_enabled": False,
    })

    assert llm_config.active_provider_id == "legacy-openai-compatible"
    assert len(llm_config.providers) == 1
    assert str(llm_config.providers[0].base_url) == "https://legacy.example.com/v1"
    assert llm_config.providers[0].api_key == "legacy-key"
    assert llm_config.providers[0].model_name == "legacy-model"


def test_ensure_builtin_llm_providers_injects_defaults_and_preserves_existing_keys():
    llm_config = LLMConfig.model_validate({
        "active_provider_id": "legacy-openai-compatible",
        "providers": [{
            "id": "legacy-openai-compatible",
            "provider": "openai_compatible",
            "name": "用户自定义",
            "base_url": "https://legacy.example.com/v1",
            "api_key": "legacy-key",
            "model_name": "legacy-model",
        }, {
            "id": BUILTIN_GEMINI3_PROVIDER_ID,
            "provider": "gemini3",
            "name": "官方默认gemini3",
            "base_url": "https://runway.devops.rednote.life/openai/google/v1:generateContent",
            "api_key": "user-overridden-gemini-key",
            "model_name": "gemini-3-pro",
        }],
    })

    ensured = ensure_builtin_llm_providers(
        llm_config,
        gemini3_api_key="builtin-gemini-key",
        claude_api_key="builtin-claude-key",
    )

    providers = {provider.id: provider for provider in ensured.providers}
    assert BUILTIN_GEMINI3_PROVIDER_ID in providers
    assert BUILTIN_CLAUDE_PROVIDER_ID in providers
    assert providers[BUILTIN_GEMINI3_PROVIDER_ID].api_key == "user-overridden-gemini-key"
    assert providers[BUILTIN_CLAUDE_PROVIDER_ID].api_key == "builtin-claude-key"
    assert ensured.active_provider_id == "legacy-openai-compatible"
