from __future__ import annotations
import base64
import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()


class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.vision_model = os.getenv("OLLAMA_MODEL", "llava")
        self.text_model = os.getenv("OLLAMA_TEXT_MODEL", "llama3")
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "120"))

    def generate(self, prompt: str, model: str | None = None) -> str:
        """Genera texto a partir de un prompt."""
        model = model or self.text_model
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            return response.json()["response"]

    def generate_vision(
        self, prompt: str, image_path: Path, model: str | None = None
    ) -> str:
        """Genera texto a partir de un prompt e imagen (para OCR/análisis)."""
        model = model or self.vision_model
        image_data = base64.b64encode(image_path.read_bytes()).decode()
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["response"]

    def is_available(self) -> bool:
        """Verifica si Ollama está accesible."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except httpx.ConnectError:
            return False
