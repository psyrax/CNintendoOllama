from __future__ import annotations
import base64
import os
from pathlib import Path

from dotenv import load_dotenv


class OllamaClient:
    """Cliente LLM multi-proveedor. Soporta 'openai' y 'anthropic'.
    Configurar LLM_PROVIDER en .env para seleccionar el proveedor activo.
    """

    def __init__(self):
        load_dotenv(override=False)
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()

        if self.provider == "anthropic":
            self.text_model = os.getenv("ANTHROPIC_TEXT_MODEL", "claude-haiku-4-5")
            self.vision_model = os.getenv("ANTHROPIC_VISION_MODEL", "claude-haiku-4-5")
            self.clean_model = os.getenv("ANTHROPIC_CLEAN_MODEL", self.text_model)
            self.clean_prompt_id: str | None = None
            self.analyze_prompt_id: str | None = None
            self.summarize_prompt_id: str | None = None
            self.describe_prompt_id: str | None = None
            self.process_prompt_id: str | None = None
            self._prompt_versions: dict[str, str] = {}
            import anthropic as _anthropic
            self._client = _anthropic.Anthropic()
        else:  # openai (default)
            self.text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
            self.vision_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
            self.clean_model = os.getenv("OPENAI_CLEAN_MODEL", self.text_model)
            self.clean_prompt_id = os.getenv("OPENAI_PROMPT_ID_CLEAN") or None
            self.analyze_prompt_id = os.getenv("OPENAI_PROMPT_ID_ANALYZE") or None
            self.summarize_prompt_id = os.getenv("OPENAI_PROMPT_ID_SUMMARIZE") or None
            self.describe_prompt_id = os.getenv("OPENAI_PROMPT_ID_DESCRIBE") or None
            self.process_prompt_id = os.getenv("OPENAI_PROMPT_ID_PROCESS") or None
            # Versiones opcionales por prompt
            self._prompt_versions = {
                "clean": os.getenv("OPENAI_PROMPT_VERSION_CLEAN") or None,
                "analyze": os.getenv("OPENAI_PROMPT_VERSION_ANALYZE") or None,
                "summarize": os.getenv("OPENAI_PROMPT_VERSION_SUMMARIZE") or None,
                "describe": os.getenv("OPENAI_PROMPT_VERSION_DESCRIBE") or None,
                "process": os.getenv("OPENAI_PROMPT_VERSION_PROCESS") or None,
            }
            # Opciones globales de Responses API
            self._reasoning_summary = os.getenv("OPENAI_REASONING_SUMMARY") or None
            self._store_responses = os.getenv("OPENAI_STORE_RESPONSES", "false").lower() == "true"
            import openai as _openai
            self._client = _openai.OpenAI()

    def _build_prompt_param(self, prompt_id: str, task: str | None = None) -> dict:
        """Construye el parámetro prompt={id, version} para Responses API."""
        obj: dict = {"id": prompt_id}
        version = self._prompt_versions.get(task) if task else None
        if version:
            obj["version"] = version
        return obj

    def _build_responses_kwargs(
        self,
        input_payload,
        model: str,
        max_tokens: int,
        prompt_id: str | None,
        task: str | None,
    ) -> dict:
        """Construye kwargs para client.responses.create()."""
        kwargs: dict = {"input": input_payload}

        if prompt_id:
            kwargs["prompt"] = self._build_prompt_param(prompt_id, task)
            # No se pasa model cuando el prompt almacenado ya lo define
        else:
            kwargs["model"] = model

        if self._reasoning_summary:
            kwargs["reasoning"] = {"summary": self._reasoning_summary}
            kwargs["include"] = ["reasoning.encrypted_content"]

        if self._store_responses:
            kwargs["store"] = True

        return kwargs

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 4096,
        prompt_id: str | None = None,
        task: str | None = None,
    ) -> str:
        """Genera texto a partir de un prompt."""
        model = model or self.text_model

        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return next((b.text for b in response.content if b.type == "text"), "")
        else:
            input_payload = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
            kwargs = self._build_responses_kwargs(input_payload, model, max_tokens, prompt_id, task)
            response = self._client.responses.create(**kwargs)
            return response.output_text or ""

    def generate_vision(
        self,
        prompt: str,
        image_path: Path,
        model: str | None = None,
        prompt_id: str | None = None,
        task: str | None = None,
    ) -> str:
        """Genera texto a partir de un prompt e imagen."""
        model = model or self.vision_model
        suffix = image_path.suffix.lower()
        media_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(suffix, "image/jpeg")
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode()

        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            return next((b.text for b in response.content if b.type == "text"), "")
        else:
            content: list = [
                {
                    "type": "input_image",
                    "image_url": f"data:{media_type};base64,{image_data}",
                }
            ]
            if prompt:
                content.append({"type": "input_text", "text": prompt})

            input_payload = [{"role": "user", "content": content}]
            kwargs = self._build_responses_kwargs(input_payload, model, 1024, prompt_id, task)
            response = self._client.responses.create(**kwargs)
            return response.output_text or ""

    def is_available(self) -> bool:
        """Verifica si el proveedor activo está configurado."""
        if self.provider == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY"))
        return bool(os.getenv("OPENAI_API_KEY"))
