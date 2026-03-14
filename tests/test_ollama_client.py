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
