#!/usr/bin/env python3
"""Placement-test web app.

- Serves the student test page (index.html), which carries no answer key.
- Grades submissions server-side against test-data.json.
- Stores every result in a local SQLite database (results.db).
- Provides a password-protected teacher console with a CSV/Excel export.

Run:
    pip install -r requirements.txt
    python build.py          # (re)generate index.html from test-data.json
    python app.py            # serves on http://127.0.0.1:5000

Teacher console: http://127.0.0.1:5000/teacher
  user: (any)   password: value of TEACHER_PASSWORD env var (default "changeme")
"""
import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import (
    Flask, Response, g, jsonify, request, send_file, render_template_string,
)

ROOT = Path(__file__).parent
DB_PATH = ROOT / "results.db"
TEACHER_PASSWORD = os.environ.get("TEACHER_PASSWORD", "changeme")

# ---- Load test definition once at startup -------------------------------
DATA = json.loads((ROOT / "test-data.json").read_text(encoding="utf-8"))
META = DATA["meta"]
ANSWERS = {q["n"]: q["answer"] for q in DATA["questions"]}
LEVELS = META["levels"]                       # ["A1", ... "C2"]
LEVEL_RANGES = META["levelRanges"]            # {"A1": [1,20], ...}
MAX_ERRORS = META["maxErrorsPerLevel"]        # 6 -> a level is passed with <= 6 errors
TOTAL = META["totalQuestions"]

app = Flask(__name__)


# ---- Database -----------------------------------------------------------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT NOT NULL,
            name         TEXT NOT NULL,
            klass        TEXT NOT NULL,
            points       INTEGER NOT NULL,
            level        TEXT NOT NULL,
            per_level    TEXT NOT NULL,
            answers      TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# ---- Grading ------------------------------------------------------------
def grade(answers: dict) -> dict:
    """answers maps question-number (as str or int) -> chosen option letter.

    A blank / missing answer counts as wrong.
    Points = total correct out of 120.
    Level  = highest CEFR level passed without a break, scanning A1 -> C2.
             A level is passed when it has MAX_ERRORS or fewer wrong answers.
    """
    def chosen(n):
        return answers.get(str(n), answers.get(n))

    points = 0
    per_level = {}
    passed = []
    broken = False

    for lvl in LEVELS:
        lo, hi = LEVEL_RANGES[lvl]
        correct = 0
        for n in range(lo, hi + 1):
            if chosen(n) == ANSWERS[n]:
                correct += 1
        errors = (hi - lo + 1) - correct
        points += correct
        per_level[lvl] = {"correct": correct, "errors": errors}
        if not broken and errors <= MAX_ERRORS:
            passed.append(lvl)
        else:
            broken = True  # once a level is failed, later passes don't count

    level = passed[-1] if passed else "-"  # "-" = below A1
    return {"points": points, "level": level, "perLevel": per_level}


# ---- Student routes -----------------------------------------------------
@app.route("/")
def index():
    return send_file(ROOT / "index.html")


@app.route("/submit", methods=["POST"])
def submit():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    klass = (payload.get("klass") or "").strip()
    answers = payload.get("answers") or {}
    if not name or not klass:
        return jsonify({"error": "Falta el nombre o la clase."}), 400

    result = grade(answers)
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    db().execute(
        "INSERT INTO results (ts, name, klass, points, level, per_level, answers)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            ts, name, klass, result["points"], result["level"],
            json.dumps(result["perLevel"], ensure_ascii=False),
            json.dumps(answers, ensure_ascii=False),
        ),
    )
    db().commit()
    return jsonify({"level": result["level"], "points": result["points"]})


# ---- Teacher console (password protected) -------------------------------
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
 header{background:#1f2937;color:#fff;padding:16px 20px;display:flex;
        justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
 header h1{margin:0;font-size:18px}
 a.btn{background:#dc2626;color:#fff;text-decoration:none;padding:8px 14px;
       border-radius:8px;font-weight:700}
 main{max-width:1000px;margin:0 auto;padding:16px}
 table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;
       border-radius:8px;overflow:hidden}
 th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #e5e7eb;font-size:14px}
 th{background:#f1f5f9}
 tr:last-child td{border-bottom:0}
 .lvl{font-weight:700;color:#dc2626}
 .muted{color:#6b7280}
</style></head><body>
<header>
  <h1>Consola del profesor — {{ count }} resultados</h1>
  <a class="btn" href="/export.csv">Descargar CSV (Excel)</a>
</header>
<main>
 {% if rows %}
 <table>
  <tr><th>#</th><th>Fecha</th><th>Nombre</th><th>Clase</th>
      <th>Puntos</th><th>Nivel</th><th>Por nivel</th></tr>
  {% for r in rows %}
  <tr>
   <td class="muted">{{ r["id"] }}</td>
   <td class="muted">{{ r["ts"] }}</td>
   <td>{{ r["name"] }}</td>
   <td>{{ r["klass"] }}</td>
   <td>{{ r["points"] }} / {{ total }}</td>
   <td class="lvl">{{ r["level"] }}</td>
   <td class="muted">{{ r["per_level_summary"] }}</td>
  </tr>
  {% endfor %}
 </table>
 {% else %}
 <p class="muted">Todavía no hay resultados.</p>
 {% endif %}
</main></body></html>
"""


def per_level_summary(per_level_json: str) -> str:
    d = json.loads(per_level_json)
    return "  ".join(f"{lvl}:{d[lvl]['correct']}/20" for lvl in LEVELS if lvl in d)


@app.route("/teacher")
@require_teacher
def teacher():
    cur = db().execute("SELECT * FROM results ORDER BY id DESC")
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        row["per_level_summary"] = per_level_summary(row["per_level"])
        rows.append(row)
    return render_template_string(
        TEACHER_HTML, rows=rows, count=len(rows), total=TOTAL
    )


@app.route("/export.csv")
@require_teacher
def export_csv():
    cur = db().execute("SELECT * FROM results ORDER BY id ASC")
    buf = io.StringIO()
    buf.write("﻿")  # BOM so Excel reads accents correctly
    writer = csv.writer(buf)
    header = ["id", "fecha", "nombre", "clase", "puntos", "nivel"]
    header += [f"aciertos_{lvl}" for lvl in LEVELS]
    writer.writerow(header)
    for r in cur.fetchall():
        d = json.loads(r["per_level"])
        writer.writerow(
            [r["id"], r["ts"], r["name"], r["klass"], r["points"], r["level"]]
            + [d.get(lvl, {}).get("correct", "") for lvl in LEVELS]
        )
    fname = f"resultados_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
