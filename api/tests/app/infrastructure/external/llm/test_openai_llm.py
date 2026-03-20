from app.infrastructure.external.llm.openai_llm import OpenAILLM


def test_normalize_messages_removes_empty_assistant_content_when_tool_calls_present():
    messages = [{
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": "{}",
            },
        }],
    }]

    normalized = OpenAILLM._normalize_messages(messages)

    assert "content" not in normalized[0]
    assert normalized[0]["tool_calls"][0]["function"]["name"] == "search"
