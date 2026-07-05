import json
from unittest.mock import patch

from pico.providers.base import ModelResult, complete_model
from pico.providers.clients import AnthropicCompatibleModelClient, OpenAICompatibleModelClient


class _FakeOpenAIResponse:
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"output_text": "<final>ok</final>"}).encode("utf-8")


class _FakeAnthropicResponse:
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {"content": [{"type": "text", "text": "<final>ok</final>"}]}
        ).encode("utf-8")


def _capture_payload(response):
    captured = {}

    def fake_urlopen(request, timeout):
        del timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return response

    return captured, fake_urlopen


def test_openai_compatible_client_maps_system_prompt_to_instructions():
    captured, fake_urlopen = _capture_payload(_FakeOpenAIResponse())
    client = OpenAICompatibleModelClient(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete(
            "selector user prompt",
            64,
            system_prompt="selector rules",
        )

    assert result == "<final>ok</final>"
    assert captured["body"]["instructions"] == "selector rules"
    assert captured["body"]["input"][0]["content"][0]["text"] == "selector user prompt"


def test_openai_compatible_client_omits_instructions_without_system_prompt():
    captured, fake_urlopen = _capture_payload(_FakeOpenAIResponse())
    client = OpenAICompatibleModelClient(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("main user prompt", 64)

    assert result == "<final>ok</final>"
    assert "instructions" not in captured["body"]
    assert captured["body"]["input"][0]["content"][0]["text"] == "main user prompt"


def test_anthropic_compatible_client_maps_system_prompt_to_system():
    captured, fake_urlopen = _capture_payload(_FakeAnthropicResponse())
    client = AnthropicCompatibleModelClient(
        model="claude-test",
        base_url="https://example.test/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete(
            "selector user prompt",
            64,
            system_prompt="selector rules",
        )

    assert result == "<final>ok</final>"
    assert captured["body"]["system"] == "selector rules"
    assert (
        captured["body"]["messages"][0]["content"][0]["text"]
        == "selector user prompt"
    )


def test_anthropic_compatible_client_omits_system_without_system_prompt():
    captured, fake_urlopen = _capture_payload(_FakeAnthropicResponse())
    client = AnthropicCompatibleModelClient(
        model="claude-test",
        base_url="https://example.test/v1",
        api_key="sk-test",
        temperature=None,
        timeout=30,
    )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.complete("main user prompt", 64)

    assert result == "<final>ok</final>"
    assert "system" not in captured["body"]
    assert captured["body"]["messages"][0]["content"][0]["text"] == "main user prompt"


def test_complete_model_forwards_system_prompt_only_when_provided():
    class CapturingClient:
        def __init__(self):
            self.calls = []

        def complete_result(self, prompt, max_new_tokens, **kwargs):
            self.calls.append((prompt, max_new_tokens, kwargs))
            return ModelResult(text="ok", metadata={"source": "complete_result"})

    with_system = CapturingClient()
    result = complete_model(
        with_system,
        "selector user prompt",
        64,
        system_prompt="selector rules",
        prompt_cache_key="prefix-key",
    )

    assert result.text == "ok"
    assert result.metadata == {"source": "complete_result"}
    assert with_system.calls == [
        (
            "selector user prompt",
            64,
            {
                "system_prompt": "selector rules",
                "prompt_cache_key": "prefix-key",
            },
        )
    ]

    without_system = CapturingClient()
    complete_model(
        without_system,
        "main user prompt",
        64,
        prompt_cache_key="prefix-key",
    )

    assert without_system.calls == [
        (
            "main user prompt",
            64,
            {
                "prompt_cache_key": "prefix-key",
            },
        )
    ]
