#!/usr/bin/env python3
"""Generate index.html from test-data.json.

The answer key is deliberately NOT embedded in the page: the page only ships
the question prompts and options. Grading happens server-side in the Apps
Script, so a student cannot read the answers from the page source.
"""
import json
import html
from pathlib import Path

ROOT = Path(__file__).parent
data = json.loads((ROOT / "test-data.json").read_text(encoding="utf-8"))

# Strip answers: the page never sees the key.
public_questions = [
    {"n": q["n"], "level": q["level"], "prompt": q["prompt"], "options": q["options"]}
    for q in data["questions"]
]
questions_json = json.dumps(public_questions, ensure_ascii=False)
meta = data["meta"]
notes_html = "".join(f"<li>{html.escape(n)}</li>" for n in meta["notes"])

page = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(meta["title"])}</title>
<style>
  :root {{
    --ink: #1f2937; --muted: #6b7280; --line: #e5e7eb; --bg: #f8fafc;
    --card: #ffffff; --brand: #dc2626; --brand-ink: #ffffff; --ok: #16a34a;
    --pick: #eff6ff; --pick-line: #3b82f6;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  header {{
    background: var(--ink); color: #fff; padding: 20px 16px; text-align: center;
  }}
  header h1 {{ margin: 0; font-size: 22px; }}
  header p {{ margin: 6px 0 0; color: #cbd5e1; font-size: 14px; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 16px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 12px;
    padding: 16px; margin: 14px 0;
  }}
  .notes ul {{ margin: 8px 0 0; padding-left: 20px; color: var(--muted); font-size: 14px; }}
  label.field {{ display: block; margin: 10px 0; font-weight: 600; }}
  label.field input {{
    display: block; width: 100%; margin-top: 6px; padding: 10px;
    border: 1px solid var(--line); border-radius: 8px; font-size: 16px; font-weight: 400;
  }}
  .q {{ scroll-margin-top: 12px; }}
  .q .num {{
    display: inline-block; min-width: 30px; height: 30px; line-height: 30px;
    text-align: center; background: var(--ink); color: #fff; border-radius: 8px;
    font-weight: 700; margin-right: 8px;
  }}
  .q .prompt {{ font-weight: 600; white-space: pre-line; }}
  .q .level-tag {{
    float: right; font-size: 12px; color: var(--muted); border: 1px solid var(--line);
    border-radius: 999px; padding: 2px 8px;
  }}
  .opts {{ margin-top: 12px; display: grid; gap: 8px; }}
  .opt {{
    display: flex; align-items: center; gap: 10px; padding: 10px 12px;
    border: 1px solid var(--line); border-radius: 8px; cursor: pointer; background: #fff;
  }}
  .opt:hover {{ border-color: var(--pick-line); }}
  .opt input {{ accent-color: var(--pick-line); width: 18px; height: 18px; }}
  .opt.chosen {{ background: var(--pick); border-color: var(--pick-line); }}
  .opt .key {{
    font-weight: 700; background: var(--ink); color: #fff; border-radius: 6px;
    width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center;
    font-size: 13px;
  }}
  .bar {{
    position: sticky; bottom: 0; background: var(--card); border-top: 1px solid var(--line);
    padding: 12px 16px; display: flex; align-items: center; gap: 12px; justify-content: space-between;
  }}
  .bar .count {{ color: var(--muted); font-size: 14px; }}
  button {{
    background: var(--brand); color: var(--brand-ink); border: 0; border-radius: 10px;
    padding: 12px 20px; font-size: 16px; font-weight: 700; cursor: pointer;
  }}
  button:disabled {{ opacity: .5; cursor: not-allowed; }}
  .result {{ text-align: center; padding: 32px 16px; }}
  .result .level {{ font-size: 48px; font-weight: 800; color: var(--brand); margin: 8px 0; }}
  .hidden {{ display: none; }}
  footer {{ text-align: center; color: var(--muted); font-size: 12px; padding: 24px 16px; }}
</style>
</head>
<body>
<header>
  <h1>{html.escape(meta["title"])}</h1>
  <p>{html.escape(meta["source"])}</p>
</header>

<main id="app">
  <section class="card notes">
    <strong>Notas</strong>
    <ul>{notes_html}</ul>
  </section>

  <section class="card">
    <label class="field">Nombre y apellido(s)
      <input id="name" type="text" autocomplete="name" required>
    </label>
    <label class="field">Clase
      <input id="klass" type="text" required>
    </label>
  </section>

  <div id="questions"></div>

  <div class="bar">
    <span class="count" id="count">0 / {len(public_questions)} respondidas</span>
    <button id="submit" type="button">Enviar test</button>
  </div>
</main>

<section id="done" class="result hidden">
  <p>¡Gracias, <span id="doneName"></span>!</p>
  <p>Tu nivel aproximado es</p>
  <div class="level" id="doneLevel"></div>
  <p id="donePoints" class="count"></p>
</section>

<footer>{html.escape(meta["copyright"])}</footer>

<script>
// Served by the Flask app; grading happens server-side at /submit.
const ENDPOINT = "/submit";

const QUESTIONS = {questions_json};
const TOTAL = QUESTIONS.length;
const answers = {{}};

const qWrap = document.getElementById("questions");
const countEl = document.getElementById("count");

QUESTIONS.forEach(q => {{
  const card = document.createElement("section");
  card.className = "card q";
  card.id = "q" + q.n;
  const optsHtml = Object.entries(q.options).map(([k, v]) => `
    <label class="opt" data-q="${{q.n}}" data-k="${{k}}">
      <input type="radio" name="q${{q.n}}" value="${{k}}">
      <span class="key">${{k.toUpperCase()}}</span>
      <span class="txt"></span>
    </label>`).join("");
  card.innerHTML = `
    <div><span class="level-tag">${{q.level}}</span>
    <span class="num">${{q.n}}</span><span class="prompt"></span></div>
    <div class="opts">${{optsHtml}}</div>`;
  card.querySelector(".prompt").textContent = q.prompt;
  const txts = card.querySelectorAll(".txt");
  Object.values(q.options).forEach((v, i) => {{ txts[i].textContent = v; }});
  qWrap.appendChild(card);
}});

qWrap.addEventListener("change", e => {{
  if (e.target.type !== "radio") return;
  const n = e.target.name.slice(1);
  answers[n] = e.target.value;
  const card = document.getElementById("q" + n);
  card.querySelectorAll(".opt").forEach(o => o.classList.remove("chosen"));
  e.target.closest(".opt").classList.add("chosen");
  countEl.textContent = Object.keys(answers).length + " / " + TOTAL + " respondidas";
}});

document.getElementById("submit").addEventListener("click", async () => {{
  const name = document.getElementById("name").value.trim();
  const klass = document.getElementById("klass").value.trim();
  if (!name || !klass) {{ alert("Escribe tu nombre y tu clase."); return; }}
  const btn = document.getElementById("submit");
  btn.disabled = true; btn.textContent = "Enviando...";

  const payload = {{ name, klass, answers, ts: new Date().toISOString() }};
  try {{
    if (!ENDPOINT) throw new Error("no-endpoint");
    const res = await fetch(ENDPOINT, {{
      method: "POST",
      body: JSON.stringify(payload),
      headers: {{ "Content-Type": "text/plain;charset=utf-8" }}
    }});
    const data = await res.json();
    showDone(name, data.level, data.points);
  }} catch (err) {{
    btn.disabled = false; btn.textContent = "Enviar test";
    alert("No se pudo enviar. Revisa tu conexión e inténtalo otra vez.");
  }}
}});

function showDone(name, level, points) {{
  document.getElementById("app").classList.add("hidden");
  document.getElementById("done").classList.remove("hidden");
  document.getElementById("doneName").textContent = name;
  document.getElementById("doneLevel").textContent = level;
  const p = document.getElementById("donePoints");
  p.textContent = (points == null) ? "" : (points + " / " + TOTAL + " puntos");
  window.scrollTo(0, 0);
}}
</script>
</body>
</html>
"""

(ROOT / "index.html").write_text(page, encoding="utf-8")
print(f"Wrote index.html ({len(page)} bytes, {len(public_questions)} questions, no answer key embedded)")
