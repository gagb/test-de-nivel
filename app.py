#!/usr/bin/env python3
"""Placement-test web app (one question at a time, server-driven).

Flow
----
1. Gate: the student reads the instructions and enters name, class and the
   shared ACCESS_CODE. The server creates (or resumes) an attempt.
2. Questions are served one at a time. Each answer is saved and graded on the
   server immediately, so a refresh or dropped connection loses nothing.
3. After each block of 20 questions (one CEFR level) the server applies the
   stop rule: more than MAX_ERRORS wrong in the block ends the test.
4. Result screen shows level and points. Grades live in results.db.

The answer key never leaves the server.

Run
---
    pip install -r requirements.txt
    ACCESS_CODE=code TEACHER_PASSWORD=secret python app.py

Teacher console: /teacher   (any username, password = TEACHER_PASSWORD)
"""
import csv
import io
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, Response, g, jsonify, redirect, request, send_file,
    render_template_string, url_for,
)

ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "results.db"))
TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD", "changeme")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "clase")


def _app_version() -> str:
    """'1.1.0+855d356' — VERSION file plus the git commit, if available.
    Stamped on every attempt so results can be traced to the exact code."""
    ver = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "0.0.0"
    try:
        import subprocess
        sha = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if sha:
            ver += "+" + sha + ("-dirty" if dirty else "")
    except Exception:
        pass
    return ver


APP_VERSION = _app_version()

# ---- Test definition ----------------------------------------------------
DATA = json.loads((ROOT / "test-data.json").read_text(encoding="utf-8"))
META = DATA["meta"]
QUESTIONS = {q["n"]: q for q in DATA["questions"]}
LEVELS = META["levels"]                     # ["A1", ..., "C2"]
LEVEL_RANGES = META["levelRanges"]          # {"A1": [1, 20], ...}
PER_LEVEL = META["questionsPerLevel"]       # 20
MAX_ERRORS = META["maxErrorsPerLevel"]      # 6 -> pass with <= 6 errors
TOTAL = META["totalQuestions"]              # 120

app = Flask(__name__)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def level_of(n: int) -> str:
    for lvl, (lo, hi) in LEVEL_RANGES.items():
        if lo <= n <= hi:
            return lvl
    raise ValueError(n)


# ---- Database -----------------------------------------------------------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS attempts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            token     TEXT NOT NULL UNIQUE,
            name      TEXT NOT NULL,
            klass     TEXT NOT NULL,
            name_key  TEXT NOT NULL,
            klass_key TEXT NOT NULL,
            started   TEXT NOT NULL,
            finished  TEXT,
            status    TEXT NOT NULL DEFAULT 'in_progress',
            points    INTEGER,
            level     TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS attempts_person
            ON attempts (name_key, klass_key);
        CREATE TABLE IF NOT EXISTS answers (
            attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
            n          INTEGER NOT NULL,
            choice     TEXT,
            correct    INTEGER NOT NULL,
            ts         TEXT NOT NULL,
            PRIMARY KEY (attempt_id, n)
        );
        """
    )
    # Migrations: add columns introduced after the first release (idempotent).
    have = {r[1] for r in conn.execute("PRAGMA table_info(attempts)").fetchall()}
    if "app_version" not in have:
        conn.execute("ALTER TABLE attempts ADD COLUMN app_version TEXT")
    if "duration_s" not in have:
        conn.execute("ALTER TABLE attempts ADD COLUMN duration_s INTEGER")
    conn.commit()
    conn.close()


init_db()  # works under `python app.py` and under WSGI import alike


# ---- Grading helpers ----------------------------------------------------
def public_question(n: int) -> dict:
    """Question as sent to the browser: no level, no answer."""
    q = QUESTIONS[n]
    return {"n": n, "prompt": q["prompt"], "options": q["options"]}


def per_level_stats(attempt_id: int) -> dict:
    """{'A1': {'answered': 20, 'correct': 15, 'errors': 5}, ...} for each level.

    'errors' counts unanswered questions in a *started* block as wrong. Blocks
    never reached have answered == 0.
    """
    rows = db().execute(
        "SELECT n, correct FROM answers WHERE attempt_id = ?", (attempt_id,)
    ).fetchall()
    stats = {lvl: {"answered": 0, "correct": 0, "errors": 0} for lvl in LEVELS}
    for r in rows:
        s = stats[level_of(r["n"])]
        s["answered"] += 1
        s["correct"] += r["correct"]
    for s in stats.values():
        s["errors"] = PER_LEVEL - s["correct"] if s["answered"] else 0
    return stats


def compute_level(stats: dict) -> str:
    """Highest level passed scanning A1 -> C2; stops at the first failure.
    A block must be fully answered to count as passed."""
    passed = None
    for lvl in LEVELS:
        s = stats[lvl]
        if s["answered"] == PER_LEVEL and s["errors"] <= MAX_ERRORS:
            passed = lvl
        else:
            break
    return passed or "-"


def finish_attempt(attempt_id: int) -> dict:
    stats = per_level_stats(attempt_id)
    points = sum(s["correct"] for s in stats.values())
    level = compute_level(stats)
    started = db().execute(
        "SELECT started FROM attempts WHERE id=?", (attempt_id,)
    ).fetchone()["started"]
    finished = now_iso()
    duration_s = int(
        (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    )
    db().execute(
        "UPDATE attempts SET status='finished', finished=?, points=?, level=?,"
        " duration_s=? WHERE id=?",
        (finished, points, level, duration_s, attempt_id),
    )
    db().commit()
    return {"done": True, "level": level, "points": points, "total": TOTAL,
            "duration_s": duration_s}


def fmt_duration(s) -> str:
    if s is None:
        return "—"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def next_payload(attempt) -> dict:
    """What the client needs next: either the next question or the result."""
    if attempt["status"] == "finished":
        return {"done": True, "level": attempt["level"],
                "points": attempt["points"], "total": TOTAL}
    answered = db().execute(
        "SELECT COUNT(*) FROM answers WHERE attempt_id = ?", (attempt["id"],)
    ).fetchone()[0]
    n = answered + 1
    if n > TOTAL:  # defensive: everything answered but not finalised
        return finish_attempt(attempt["id"])
    return {"done": False, "question": public_question(n),
            "answered": answered, "total": TOTAL}


def get_attempt_by_token(token: str):
    if not token:
        return None
    return db().execute(
        "SELECT * FROM attempts WHERE token = ?", (token,)
    ).fetchone()


# ---- Student routes -----------------------------------------------------
@app.route("/")
def index():
    return send_file(ROOT / "index.html")


@app.route("/api/notes")
def notes():
    # Student-facing: neutral title, no publisher branding, plus app version.
    return jsonify({"title": "Test de nivel de español", "notes": META["notes"],
                    "total": TOTAL, "version": APP_VERSION})


@app.route("/api/start", methods=["POST"])
def start():
    p = request.get_json(force=True, silent=True) or {}
    name = (p.get("name") or "").strip()
    klass = (p.get("klass") or "").strip()
    code = (p.get("code") or "").strip()
    if not name or not klass:
        return jsonify({"error": "Escribe tu nombre y tu clase."}), 400
    if code != ACCESS_CODE:
        return jsonify({"error": "Código de acceso incorrecto."}), 403

    name_key, klass_key = name.casefold(), klass.casefold()
    existing = db().execute(
        "SELECT * FROM attempts WHERE name_key=? AND klass_key=?",
        (name_key, klass_key),
    ).fetchone()
    if existing:
        if existing["status"] == "finished":
            return jsonify({"error": "Ya has completado este test. "
                            "Habla con tu profe si necesitas repetirlo."}), 409
        attempt = existing  # resume
    else:
        token = secrets.token_urlsafe(24)
        db().execute(
            "INSERT INTO attempts (token, name, klass, name_key, klass_key, started,"
            " app_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (token, name, klass, name_key, klass_key, now_iso(), APP_VERSION),
        )
        db().commit()
        attempt = get_attempt_by_token(token)

    out = next_payload(attempt)
    out["token"] = attempt["token"]
    out["name"] = attempt["name"]
    return jsonify(out)


@app.route("/api/next")
def api_next():
    attempt = get_attempt_by_token(request.args.get("token", ""))
    if not attempt:
        return jsonify({"error": "invalid token"}), 401
    out = next_payload(attempt)
    out["name"] = attempt["name"]
    return jsonify(out)


@app.route("/api/answer", methods=["POST"])
def api_answer():
    p = request.get_json(force=True, silent=True) or {}
    attempt = get_attempt_by_token(p.get("token", ""))
    if not attempt:
        return jsonify({"error": "invalid token"}), 401
    if attempt["status"] == "finished":
        return jsonify(next_payload(attempt))

    n = p.get("n")
    choice = p.get("choice")  # option letter, or None for "no lo sé"
    answered = db().execute(
        "SELECT COUNT(*) FROM answers WHERE attempt_id = ?", (attempt["id"],)
    ).fetchone()[0]
    expected = answered + 1
    if n != expected:
        # Out of sync (double-tap, stale tab): tell the client where we are.
        out = next_payload(attempt)
        out["resync"] = True
        return jsonify(out), 409
    q = QUESTIONS[n]
    if choice is not None and choice not in q["options"]:
        return jsonify({"error": "invalid choice"}), 400

    correct = 1 if choice == q["answer"] else 0
    db().execute(
        "INSERT INTO answers (attempt_id, n, choice, correct, ts) VALUES (?, ?, ?, ?, ?)",
        (attempt["id"], n, choice, correct, now_iso()),
    )
    db().commit()

    # Stop rule at the end of each level block, and at the end of the test.
    if n % PER_LEVEL == 0:
        stats = per_level_stats(attempt["id"])
        if stats[level_of(n)]["errors"] > MAX_ERRORS or n == TOTAL:
            return jsonify(finish_attempt(attempt["id"]))

    attempt = get_attempt_by_token(attempt["token"])
    return jsonify(next_payload(attempt))


# ---- Teacher console ----------------------------------------------------
def require_teacher(f):
    @wraps(f)
    def wrapper(*a, **kw):
        auth = request.authorization
        if not auth or auth.password != TEACHER_PASSWORD:
            return Response(
                "Acceso restringido.", 401,
                {"WWW-Authenticate": 'Basic realm="Teacher console"'},
            )
        return f(*a, **kw)
    return wrapper


TEACHER_HTML = """
<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Consola del profesor</title>
<style>
 body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      margin:0;background:#f8fafc;color:#1f2937}
 header{background:#1f2937;color:#fff;padding:14px 20px;display:flex;
        justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
 header h1{margin:0;font-size:18px}
 header .meta{color:#cbd5e1;font-size:13px}
 a.btn{background:#dc2626;color:#fff;text-decoration:none;padding:8px 14px;
       border-radius:8px;font-weight:700}
 main{max-width:1100px;margin:0 auto;padding:16px;overflow-x:auto}
 table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;
       border-radius:8px;overflow:hidden}
 th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:14px;
       white-space:nowrap}
 th{background:#f1f5f9}
 tr:last-child td{border-bottom:0}
 .lvl{font-weight:700;color:#dc2626}
 .muted{color:#6b7280}
 .prog{color:#b45309;font-weight:600}
 button.del{background:#fff;color:#6b7280;border:1px solid #e5e7eb;border-radius:6px;
            padding:4px 8px;cursor:pointer;font-size:12px}
 button.del:hover{color:#dc2626;border-color:#dc2626}
</style></head><body>
<header>
  <div>
    <h1>Consola del profesor — {{ rows|length }} intentos</h1>
    <div class="meta">Código de acceso para estudiantes: <b>{{ access_code }}</b>
      &nbsp;·&nbsp; app v{{ app_version }}</div>
  </div>
  <div>
    <a class="btn" href="{{ url_for('export_csv') }}">Resultados CSV</a>
    <a class="btn" href="{{ url_for('export_answers_csv') }}">Respuestas CSV</a>
  </div>
</header>
<main>
 {% if rows %}
 <table>
  <tr><th>#</th><th>Inicio</th><th>Nombre</th><th>Clase</th><th>Estado</th>
      <th>Tiempo</th><th>Puntos</th><th>Nivel</th>
      {% for lvl in levels %}<th>{{ lvl }}</th>{% endfor %}<th>Versión</th><th></th></tr>
  {% for r in rows %}
  <tr>
   <td class="muted">{{ r.id }}</td>
   <td class="muted">{{ r.started[:16].replace('T',' ') }}</td>
   <td><a href="{{ url_for('attempt_detail', attempt_id=r.id) }}">{{ r.name }}</a></td>
   <td>{{ r.klass }}</td>
   <td>{% if r.status == 'finished' %}Terminado{% else %}
       <span class="prog">En curso ({{ r.answered }}/{{ total }})</span>{% endif %}</td>
   <td class="muted">{{ r.duration }}</td>
   <td>{% if r.points is not none %}{{ r.points }} / {{ total }}{% else %}—{% endif %}</td>
   <td class="lvl">{{ r.level or '—' }}</td>
   {% for lvl in levels %}
   <td class="muted">{% if r.stats[lvl].answered %}{{ r.stats[lvl].correct }}/{{ per_level }}{% else %}·{% endif %}</td>
   {% endfor %}
   <td class="muted" style="font-size:12px">{{ r.app_version or '—' }}</td>
   <td><form method="post" action="{{ url_for('delete_attempt', attempt_id=r.id) }}"
             onsubmit="return confirm('¿Borrar el intento de {{ r.name }}? Podrá repetir el test.')">
       <button class="del" type="submit">Borrar</button></form></td>
  </tr>
  {% endfor %}
 </table>
 {% else %}
 <p class="muted">Todavía no hay intentos.</p>
 {% endif %}
</main></body></html>
"""


def all_attempts_with_stats():
    rows = []
    for r in db().execute("SELECT * FROM attempts ORDER BY id DESC").fetchall():
        d = dict(r)
        d["stats"] = per_level_stats(r["id"])
        d["answered"] = sum(s["answered"] for s in d["stats"].values())
        d["duration"] = fmt_duration(d.get("duration_s"))
        rows.append(d)
    return rows


@app.route("/teacher")
@require_teacher
def teacher():
    return render_template_string(
        TEACHER_HTML, rows=all_attempts_with_stats(), levels=LEVELS,
        total=TOTAL, per_level=PER_LEVEL, access_code=ACCESS_CODE,
        app_version=APP_VERSION,
    )


@app.route("/teacher/delete/<int:attempt_id>", methods=["POST"])
@require_teacher
def delete_attempt(attempt_id):
    db().execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))
    db().commit()
    return redirect(url_for("teacher"))


DETAIL_HTML = """
<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ a.name }} — respuestas</title>
<style>
 body{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
      margin:0;background:#f8fafc;color:#1f2937}
 header{background:#1f2937;color:#fff;padding:14px 20px;display:flex;
        justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
 header h1{margin:0;font-size:18px}
 header .meta{color:#cbd5e1;font-size:13px}
 a.btn{background:#fff;color:#1f2937;text-decoration:none;padding:8px 14px;
       border-radius:8px;font-weight:700}
 main{max-width:1100px;margin:0 auto;padding:16px;overflow-x:auto}
 table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;
       border-radius:8px;overflow:hidden}
 th,td{padding:7px 10px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:14px;
       vertical-align:top}
 th{background:#f1f5f9;white-space:nowrap}
 tr:last-child td{border-bottom:0}
 .ok{color:#16a34a;font-weight:700}.bad{color:#dc2626;font-weight:700}.blank{color:#6b7280}
 .muted{color:#6b7280}
 .lvl{font-size:12px;color:#6b7280;border:1px solid #e5e7eb;border-radius:999px;padding:1px 7px}
 .prompt{white-space:pre-line;max-width:420px}
</style></head><body>
<header>
  <div>
    <h1>{{ a.name }} · {{ a.klass }}</h1>
    <div class="meta">
      {% if a.status == 'finished' %}Terminado · nivel <b>{{ a.level }}</b> · {{ a.points }}/{{ total }} puntos
      · tiempo {{ duration }}
      {% else %}En curso · {{ rows|length }}/{{ total }} respondidas{% endif %}
      · inicio {{ a.started[:16].replace('T',' ') }}
      · app v{{ a.app_version or '?' }}
    </div>
  </div>
  <a class="btn" href="{{ url_for('teacher') }}">← Volver</a>
</header>
<main>
 <table>
  <tr><th>#</th><th>Nivel</th><th>Pregunta</th><th>Respuesta</th><th>Correcta</th><th>Resultado</th><th>Hora</th></tr>
  {% for r in rows %}
  <tr>
   <td class="muted">{{ r.n }}</td>
   <td><span class="lvl">{{ r.level }}</span></td>
   <td class="prompt">{{ r.prompt }}</td>
   <td>{% if r.choice %}<b>{{ r.choice|upper }}</b> · {{ r.choice_text }}{% else %}<span class="blank">— en blanco —</span>{% endif %}</td>
   <td class="muted"><b>{{ r.answer|upper }}</b> · {{ r.answer_text }}</td>
   <td>{% if r.choice is none %}<span class="blank">blanco</span>{% elif r.correct %}<span class="ok">✓</span>{% else %}<span class="bad">✗</span>{% endif %}</td>
   <td class="muted">{{ r.ts[11:19] }}</td>
  </tr>
  {% endfor %}
 </table>
</main></body></html>
"""


def attempt_answers(attempt_id: int):
    """Every answer for one attempt, enriched with question text and the key."""
    out = []
    for r in db().execute(
        "SELECT n, choice, correct, ts FROM answers WHERE attempt_id=? ORDER BY n",
        (attempt_id,),
    ).fetchall():
        q = QUESTIONS[r["n"]]
        out.append({
            "n": r["n"], "level": q["level"], "prompt": q["prompt"],
            "choice": r["choice"],
            "choice_text": q["options"].get(r["choice"], "") if r["choice"] else "",
            "answer": q["answer"], "answer_text": q["options"][q["answer"]],
            "correct": r["correct"], "ts": r["ts"],
        })
    return out


@app.route("/teacher/attempt/<int:attempt_id>")
@require_teacher
def attempt_detail(attempt_id):
    a = db().execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
    if not a:
        return "No existe.", 404
    return render_template_string(
        DETAIL_HTML, a=a, rows=attempt_answers(attempt_id), total=TOTAL,
        duration=fmt_duration(a["duration_s"]),
    )


@app.route("/export-answers.csv")
@require_teacher
def export_answers_csv():
    """One row per student per question: pivot-friendly for Excel."""
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["intento_id", "nombre", "clase", "pregunta", "nivel",
                "respuesta", "correcta", "resultado", "hora"])
    for a in db().execute("SELECT * FROM attempts ORDER BY id").fetchall():
        for r in attempt_answers(a["id"]):
            result = "blanco" if r["choice"] is None else ("acierto" if r["correct"] else "fallo")
            w.writerow([a["id"], a["name"], a["klass"], r["n"], r["level"],
                        (r["choice"] or "").upper(), r["answer"].upper(), result, r["ts"]])
    fname = f"respuestas_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.route("/export.csv")
@require_teacher
def export_csv():
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel reads accents correctly
    w = csv.writer(buf)
    w.writerow(["id", "inicio", "fin", "duracion_s", "nombre", "clase", "estado",
                "puntos", "nivel"]
               + [f"aciertos_{lvl}" for lvl in LEVELS] + ["version_app"])
    for r in sorted(all_attempts_with_stats(), key=lambda x: x["id"]):
        w.writerow(
            [r["id"], r["started"], r["finished"] or "",
             r["duration_s"] if r.get("duration_s") is not None else "",
             r["name"], r["klass"],
             "terminado" if r["status"] == "finished" else "en curso",
             r["points"] if r["points"] is not None else "", r["level"] or ""]
            + [r["stats"][lvl]["correct"] if r["stats"][lvl]["answered"] else ""
               for lvl in LEVELS]
            + [r.get("app_version") or ""]
        )
    fname = f"resultados_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


if __name__ == "__main__":
    # Debugger OFF by default: this server is exposed through a public tunnel.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=debug)
