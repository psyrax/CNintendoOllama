#!/usr/bin/env python3
"""Genera un reporte HTML con gráficas a partir de benchmark_results.json."""
from __future__ import annotations
import json
import sys
from pathlib import Path

RESULTS_FILE = Path("tools/benchmark_results.json")
OUTPUT_FILE = Path("tools/benchmark_report.html")


def load_results() -> list[dict]:
    if not RESULTS_FILE.exists():
        print(f"No se encontró {RESULTS_FILE}")
        sys.exit(1)
    return json.loads(RESULTS_FILE.read_text())


def build_html(results: list[dict]) -> str:
    # Separar OK vs error
    ok = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    # Datos para gráficas
    labels = [f"{r['model'].split(':')[0]}\n({r['mode']})" for r in ok]
    labels_json = json.dumps(labels)
    times = [r["time"] for r in ok]
    times_json = json.dumps(times)
    articles = [r["articles"] for r in ok]
    articles_json = json.dumps(articles)
    valid_json = [1 if r.get("valid_json") else 0 for r in ok]
    valid_json_json = json.dumps(valid_json)

    # Colores por modo
    color_map = {
        "plain": "#4f86c6",
        "tools": "#43b97f",
        "tools+thinking": "#e8703a",
    }
    bar_colors = json.dumps([color_map.get(r["mode"], "#888") for r in ok])

    # Tabla rows
    table_rows = ""
    for r in results:
        if "error" in r:
            table_rows += f"""
            <tr class="error-row">
                <td><span class="model-name">{r['model']}</span></td>
                <td><span class="badge badge-plain">{r.get('mode','?')}</span></td>
                <td>—</td><td>—</td>
                <td><span class="badge badge-error">ERROR</span></td>
                <td class="error-text">{r['error'][:60]}</td>
            </tr>"""
        else:
            mode_class = r["mode"].replace("+", "-")
            ok_badge = '<span class="badge badge-ok">✓ Sí</span>' if r["valid_json"] else '<span class="badge badge-error">✗ No</span>'
            table_rows += f"""
            <tr>
                <td><span class="model-name">{r['model']}</span></td>
                <td><span class="badge badge-{mode_class}">{r['mode']}</span></td>
                <td class="num">{r['time']}s</td>
                <td class="num">{r['articles']}</td>
                <td>{ok_badge}</td>
                <td>{r.get('quality','—')}</td>
            </tr>"""

    # Mejor por tiempo (entre los que funcionaron)
    if ok:
        fastest = min(ok, key=lambda r: r["time"])
        most_articles = max(ok, key=lambda r: r["articles"])
        thinking_ok = [r for r in ok if "thinking" in r["mode"]]
        best_thinking = min(thinking_ok, key=lambda r: r["time"]) if thinking_ok else None
    else:
        fastest = most_articles = best_thinking = None

    highlights = ""
    if fastest:
        highlights += f'<div class="highlight"><span class="hl-icon">⚡</span><b>Más rápido:</b> {fastest["model"]} ({fastest["mode"]}) — {fastest["time"]}s</div>'
    if most_articles:
        highlights += f'<div class="highlight"><span class="hl-icon">📰</span><b>Más artículos:</b> {most_articles["model"]} ({most_articles["mode"]}) — {most_articles["articles"]} artículos</div>'
    if best_thinking:
        highlights += f'<div class="highlight"><span class="hl-icon">🧠</span><b>Mejor con thinking:</b> {best_thinking["model"]} — {best_thinking["time"]}s, {best_thinking["articles"]} artículos</div>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Benchmark Modelos Ollama — cnintendo</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #252836;
    --border: #2e3248;
    --text: #e2e4ed;
    --muted: #7b80a0;
    --accent: #4f86c6;
    --green: #43b97f;
    --orange: #e8703a;
    --red: #e05252;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; padding: 2rem; }}
  h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.25rem; }}
  .subtitle {{ color: var(--muted); margin-bottom: 2rem; font-size: 0.95rem; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; }}
  .card h2 {{ font-size: 1rem; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem; }}
  .chart-wrap {{ position: relative; height: 280px; }}
  .highlights {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }}
  .highlight {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; flex: 1; min-width: 220px; font-size: 0.9rem; }}
  .hl-icon {{ margin-right: 0.5rem; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 12px; overflow: hidden; border: 1px solid var(--border); }}
  thead {{ background: var(--surface2); }}
  th {{ padding: 0.75rem 1rem; text-align: left; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }}
  td {{ padding: 0.75rem 1rem; border-top: 1px solid var(--border); font-size: 0.9rem; vertical-align: middle; }}
  .num {{ font-variant-numeric: tabular-nums; text-align: right; }}
  .model-name {{ font-family: monospace; font-size: 0.85rem; color: #a0a8c8; }}
  .error-row td {{ opacity: 0.6; }}
  .error-text {{ font-family: monospace; font-size: 0.78rem; color: var(--red); }}
  .badge {{ display: inline-block; padding: 0.15rem 0.6rem; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }}
  .badge-plain {{ background: #1e3256; color: #7ab0e8; }}
  .badge-tools {{ background: #1a3b2a; color: #6dd4a5; }}
  .badge-tools-thinking {{ background: #3b2214; color: #f4a46a; }}
  .badge-ok {{ background: #1a3b2a; color: #6dd4a5; }}
  .badge-error {{ background: #3b1414; color: #f47a7a; }}
  .legend {{ display: flex; gap: 1.5rem; margin-bottom: 1rem; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; color: var(--muted); }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 3px; }}
  @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>Benchmark Modelos Ollama</h1>
<p class="subtitle">Tarea: análisis estructurado de revista de videojuegos — {len(results)} configuraciones probadas</p>

<div class="highlights">
{highlights}
</div>

<div class="legend">
  <div class="legend-item"><div class="legend-dot" style="background:#4f86c6"></div> Plain JSON prompt</div>
  <div class="legend-item"><div class="legend-dot" style="background:#43b97f"></div> Tool calls</div>
  <div class="legend-item"><div class="legend-dot" style="background:#e8703a"></div> Tool calls + Thinking</div>
</div>

<div class="grid">
  <div class="card">
    <h2>Tiempo de respuesta (segundos)</h2>
    <div class="chart-wrap"><canvas id="chartTime"></canvas></div>
  </div>
  <div class="card">
    <h2>Artículos extraídos</h2>
    <div class="chart-wrap"><canvas id="chartArticles"></canvas></div>
  </div>
</div>

<div class="card" style="margin-bottom:2rem">
  <h2>Resultados detallados</h2>
  <div style="overflow-x:auto; margin-top:1rem">
    <table>
      <thead><tr>
        <th>Modelo</th><th>Modo</th><th style="text-align:right">Tiempo</th>
        <th style="text-align:right">Artículos</th><th>JSON válido</th><th>Calidad</th>
      </tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
  </div>
</div>

<div class="card">
  <h2>Notas de interpretación</h2>
  <ul style="padding-left:1.25rem; line-height:1.8; color:var(--muted); font-size:0.9rem; margin-top:0.5rem">
    <li><b style="color:var(--text)">Plain JSON prompt</b>: el modelo recibe el texto y debe devolver JSON puro. Propenso a code fences y alucinaciones.</li>
    <li><b style="color:var(--text)">Tool calls</b>: el modelo usa una función estructurada con schema definido. Elimina el problema de JSON malformado.</li>
    <li><b style="color:var(--text)">Tool calls + Thinking</b>: el modelo razona antes de responder. Mayor calidad, mayor tiempo.</li>
    <li>Un modelo rápido con JSON inválido es peor que uno lento con JSON válido.</li>
    <li>Para OCR (escaneos), los modelos con capacidad <b style="color:var(--text)">vision</b> son preferibles.</li>
  </ul>
</div>

<script>
const labels = {labels_json};
const times = {times_json};
const articles = {articles_json};
const colors = {bar_colors};

const chartOpts = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{ legend: {{ display: false }} }},
  scales: {{
    x: {{ ticks: {{ color: '#7b80a0', font: {{ size: 10 }} }}, grid: {{ color: '#1e2235' }} }},
    y: {{ ticks: {{ color: '#7b80a0' }}, grid: {{ color: '#1e2235' }} }},
  }},
}};

new Chart(document.getElementById('chartTime'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ data: times, backgroundColor: colors, borderRadius: 4 }}] }},
  options: {{ ...chartOpts, scales: {{ ...chartOpts.scales, y: {{ ...chartOpts.scales.y, title: {{ display: true, text: 'segundos', color: '#7b80a0' }} }} }} }},
}});

new Chart(document.getElementById('chartArticles'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ data: articles, backgroundColor: colors, borderRadius: 4 }}] }},
  options: {{ ...chartOpts, scales: {{ ...chartOpts.scales, y: {{ ...chartOpts.scales.y, title: {{ display: true, text: 'artículos encontrados', color: '#7b80a0' }} }} }} }},
}});
</script>
</body>
</html>"""


if __name__ == "__main__":
    results = load_results()
    html = build_html(results)
    OUTPUT_FILE.write_text(html)
    print(f"Reporte generado: {OUTPUT_FILE}")
    print(f"Abre en el navegador: file://{OUTPUT_FILE.resolve()}")
