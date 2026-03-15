#!/usr/bin/env python3
"""Benchmark de modelos Ollama para la tarea de análisis de revista."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
TIMEOUT = 600

MODELS = {
    # Caben en VRAM (<=4GB) — rápidos
    "lfm2.5-thinking:latest": {"thinking": True,  "tools": True,  "size_gb": 0.7},
    "qwen3.5:0.8b":           {"thinking": True,  "tools": True,  "size_gb": 1.0},
    "llama3.2:latest":        {"thinking": False, "tools": True,  "size_gb": 2.0},
    "qwen3.5:2b":             {"thinking": True,  "tools": True,  "size_gb": 2.7},
    "gemma3:4b":              {"thinking": False, "tools": False, "size_gb": 3.3},
    # Corren en RAM — lentos, se pueden saltar con --fast
    "gemma3n:latest":         {"thinking": False, "tools": False, "size_gb": 7.5},
    "gemma3:12b-it-qat":      {"thinking": False, "tools": False, "size_gb": 8.9},
    "llava:7b":               {"thinking": False, "tools": False, "size_gb": 4.7},  # vision model
}

ARTICLES_TOOL = {
    "type": "function",
    "function": {
        "name": "save_articles",
        "description": "Guarda los artículos identificados en la revista",
        "parameters": {
            "type": "object",
            "required": ["articles"],
            "properties": {
                "articles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["page", "section"],
                        "properties": {
                            "page":     {"type": "integer"},
                            "section":  {"type": "string", "enum": ["review", "preview", "news", "editorial", "unknown"]},
                            "title":    {"type": ["string", "null"]},
                            "game":     {"type": ["string", "null"]},
                            "platform": {"type": ["string", "null"]},
                            "score":    {"type": ["number", "null"]},
                            "text":     {"type": ["string", "null"]},
                        },
                    },
                }
            },
        },
    },
}

PROMPT_TEXT = """Analiza el siguiente texto extraído de una revista de videojuegos en español.

TEXTO POR PÁGINA:
{pages_text}

Identifica cada artículo o reseña independiente. Omite páginas sin contenido claro.
Para cada artículo indica: página, sección, título, juego, plataforma, puntuación y resumen breve en español correcto."""

PROMPT_JSON = PROMPT_TEXT + """

INSTRUCCIONES ESTRICTAS:
- Responde ÚNICAMENTE con el objeto JSON, sin texto adicional, sin markdown, sin bloques de código.
- No uses ``` ni ```json. Solo el JSON puro.
- Los campos "game" y "platform" deben ser strings simples.

Estructura exacta requerida:
{{"articles": [{{"page": <int>, "section": <"review"|"preview"|"news"|"editorial"|"unknown">, "title": <string o null>, "game": <string o null>, "platform": <string o null>, "score": <número o null>, "text": <resumen breve>}}]}}"""


def call_generate(model: str, prompt: str, use_thinking: bool = False) -> tuple[str, float]:
    """Llama a /api/generate. Retorna (respuesta, segundos)."""
    t0 = time.time()
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if use_thinking:
        payload["think"] = True
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
    elapsed = time.time() - t0
    data = resp.json()
    # Con think=true, el modelo devuelve thinking separado; la respuesta final está en "response"
    return data["response"], elapsed


def call_chat_with_tools(model: str, prompt: str, use_thinking: bool) -> tuple[str | None, float]:
    """Llama a /api/chat con tools definidas. Retorna (JSON de args, segundos)."""
    t0 = time.time()
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [ARTICLES_TOOL],
        "stream": False,
    }
    if use_thinking:
        payload["think"] = True
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        resp.raise_for_status()
    elapsed = time.time() - t0
    data = resp.json()
    msg = data.get("message", {})
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        args = tool_calls[0].get("function", {}).get("arguments", {})
        # args puede ser dict ya parseado o string JSON
        if isinstance(args, dict):
            return json.dumps(args), elapsed
        return args or "", elapsed
    # fallback: modelo no usó tools, devuelve texto
    return msg.get("content", ""), elapsed


def parse_articles(raw: str, debug: bool = False) -> list[dict]:
    """Extrae lista de artículos del texto de respuesta."""
    if not raw:
        if debug:
            print(f"    [debug] respuesta vacía")
        return []
    cleaned = raw.strip()
    # Stripear bloques <think>...</think> que algunos modelos incluyen antes del JSON
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    if debug:
        print(f"    [debug] primeros 200 chars: {cleaned[:200]!r}")
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    # Intentar extraer JSON aunque haya texto antes/después
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        parsed = json.loads(cleaned)
        articles = parsed.get("articles", parsed if isinstance(parsed, list) else [])
        return articles
    except json.JSONDecodeError as e:
        if debug:
            print(f"    [debug] JSON inválido: {e}")
        return []


def score_articles(articles: list[dict]) -> str:
    """Resumen de calidad: cuántos tienen game, title, text."""
    if not articles:
        return "0 artículos"
    with_game = sum(1 for a in articles if a.get("game"))
    with_text = sum(1 for a in articles if a.get("text"))
    return f"{len(articles)} artículos, {with_game} con juego, {with_text} con texto"


def run_benchmark(pages_text: str, vram_only: bool = False):
    results = []
    vram_limit = 4.0

    for model, caps in MODELS.items():
        if vram_only and caps.get("size_gb", 0) > vram_limit:
            print(f"\nSaltando {model} ({caps['size_gb']}GB > {vram_limit}GB VRAM)")
            continue
        print(f"\n{'='*60}")
        print(f"Modelo: {model}  [thinking={caps['thinking']} tools={caps['tools']}]")

        # --- Modo plain JSON (prompt directo) ---
        mode_label = "plain+thinking" if caps["thinking"] else "plain"
        print(f"  [1/2] Llamada directa ({mode_label})...", end=" ", flush=True)
        try:
            response, elapsed = call_generate(model, PROMPT_JSON.format(pages_text=pages_text), use_thinking=caps["thinking"])
            articles = parse_articles(response, debug=True)
            quality = score_articles(articles)
            print(f"{elapsed:.1f}s → {quality}")
            results.append({
                "model": model, "mode": mode_label,
                "time": round(elapsed, 1), "articles": len(articles), "quality": quality,
                "valid_json": len(articles) > 0,
            })
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"model": model, "mode": mode_label, "time": None, "error": str(e)})

        if caps["tools"]:
            mode = "tools+thinking" if caps["thinking"] else "tools"
            print(f"  [2/2] Con tool calls ({mode})...", end=" ", flush=True)
            try:
                raw, elapsed = call_chat_with_tools(model, PROMPT_TEXT.format(pages_text=pages_text), caps["thinking"])
                articles = parse_articles(raw, debug=True)
                quality = score_articles(articles)
                print(f"{elapsed:.1f}s → {quality}")
                results.append({
                    "model": model, "mode": mode,
                    "time": round(elapsed, 1), "articles": len(articles), "quality": quality,
                    "valid_json": len(articles) > 0,
                })
            except Exception as e:
                print(f"ERROR: {e}")
                results.append({"model": model, "mode": mode, "time": None, "error": str(e)})

    # --- Tabla resumen ---
    print(f"\n{'='*60}")
    print("RESULTADOS:")
    print(f"{'Modelo':<30} {'Modo':<18} {'Tiempo':>7}  {'Artículos':>10}  {'JSON OK':>7}")
    print("-" * 75)
    for r in results:
        if "error" in r:
            print(f"{r['model']:<30} {r['mode']:<18} {'ERROR':>7}  {r.get('error','')[:30]}")
        else:
            ok = "✓" if r["valid_json"] else "✗"
            print(f"{r['model']:<30} {r['mode']:<18} {r['time']:>6.1f}s  {r['articles']:>10}  {ok:>7}")

    # Guardar resultados
    out = Path("tools/benchmark_results.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResultados guardados en {out}")


if __name__ == "__main__":
    args = sys.argv[1:]
    vram_only = "--fast" in args
    args = [a for a in args if a != "--fast"]
    extracted_json = Path(args[0]) if args else None
    if not extracted_json:
        # Buscar el primero disponible
        candidates = list(Path("data/extracted").glob("*_extracted.json"))
        if not candidates:
            print("No se encontró ningún *_extracted.json en data/extracted/")
            sys.exit(1)
        extracted_json = candidates[0]

    print(f"Usando: {extracted_json}")
    raw_data = json.loads(extracted_json.read_text())
    pages = raw_data.get("pages", [])
    pages_text = "\n\n---\n\n".join(
        f"[Página {p['page_number']}]\n{p['text']}"
        for p in pages
        if p.get("text", "").strip()
    )[:6000]

    if not pages_text.strip():
        print("No hay texto en el JSON extraído.")
        sys.exit(1)

    if vram_only:
        print("Modo --fast: solo modelos que caben en VRAM (<= 4GB)")


    run_benchmark(pages_text, vram_only=vram_only)
