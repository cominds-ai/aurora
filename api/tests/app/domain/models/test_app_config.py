from app.domain.models.app_config import (
    BUILTIN_CLAUDE_PROVIDER_ID,
    BUILTIN_GPT_PROVIDER_ID,
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
            "id": BUILTIN_GPT_PROVIDER_ID,
            "provider": "openai_compatible",
            "name": "官方默认gpt",
            "base_url": "https://codex.ysaikeji.cn/v1",
            "api_key": "user-overridden-gpt-key",
            "model_name": "gpt-5.4",
        }],
    })

    ensured = ensure_builtin_llm_providers(
        llm_config,
        gpt_api_key="builtin-gpt-key",
        claude_api_key="builtin-claude-key",
    )

    providers = {provider.id: provider for provider in ensured.providers}
    assert BUILTIN_GPT_PROVIDER_ID in providers
    assert BUILTIN_CLAUDE_PROVIDER_ID in providers
    assert providers[BUILTIN_GPT_PROVIDER_ID].api_key == "user-overridden-gpt-key"
    assert providers[BUILTIN_CLAUDE_PROVIDER_ID].api_key == "builtin-claude-key"
    assert ensured.active_provider_id == "legacy-openai-compatible"


def test_ensure_builtin_llm_providers_removes_legacy_builtin_gemini():
    llm_config = LLMConfig.model_validate({
        "active_provider_id": "builtin-gemini3",
        "providers": [{
            "id": "builtin-gemini3",
            "provider": "gemini3",
            "name": "官方默认gemini3",
            "base_url": "https://runway.devops.rednote.life/openai/google/v1:generateContent",
            "api_key": "old-key",
            "model_name": "gemini-3-pro",
            "builtin": True,
        }],
    })

    ensured = ensure_builtin_llm_providers(
        llm_config,
        gpt_api_key="builtin-gpt-key",
        claude_api_key="builtin-claude-key",
    )

    provider_ids = {provider.id for provider in ensured.providers}
    assert "builtin-gemini3" not in provider_ids
    assert BUILTIN_GPT_PROVIDER_ID in provider_ids
    assert BUILTIN_CLAUDE_PROVIDER_ID in provider_ids
    assert ensured.active_provider_id == BUILTIN_GPT_PROVIDER_ID
