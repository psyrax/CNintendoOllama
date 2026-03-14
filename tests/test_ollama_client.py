import json
import pytest
import httpx
import respx as respx_lib
from cnintendo.ollama_client import OllamaClient


def test_client_reads_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://test-host:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llava-test")
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "llama3-test")
    client = OllamaClient()
    assert client.base_url == "http://test-host:11434"
    assert client.vision_model == "llava-test"
    assert client.text_model == "llama3-test"


def test_client_defaults(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    client = OllamaClient()
    assert client.base_url == "http://localhost:11434"
    assert client.vision_model == "llava"
    assert client.text_model == "llama3"
    assert client.timeout == 120.0


@respx_lib.mock
def test_generate_calls_correct_endpoint():
    respx_lib.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "hola mundo"})
    )
    client = OllamaClient()
    result = client.generate("di hola")
    assert result == "hola mundo"


@respx_lib.mock
def test_generate_vision_sends_image(tmp_path):
    # Create a small test image file
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"fake-image-data")

    respx_lib.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "texto extraído"})
    )
    client = OllamaClient()
    result = client.generate_vision("extrae texto", img_path)
    assert result == "texto extraído"
    # Verify the request body included an images list
    request = respx_lib.calls.last.request
    body = json.loads(request.content)
    assert "images" in body
    assert len(body["images"]) == 1


@respx_lib.mock
def test_is_available_returns_true_on_success():
    respx_lib.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    client = OllamaClient()
    assert client.is_available() is True


@respx_lib.mock
def test_is_available_returns_false_on_error():
    respx_lib.get("http://localhost:11434/api/tags").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    client = OllamaClient()
    assert client.is_available() is False


@respx_lib.mock
def test_is_available_returns_false_on_os_error(monkeypatch):
    respx_lib.get("http://localhost:11434/api/tags").mock(
        side_effect=OSError("network unreachable")
    )
    client = OllamaClient()
    assert client.is_available() is False
