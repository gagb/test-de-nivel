# Test de nivel — online placement test

An online version of the ProfeDeELE.es progressive Spanish placement test
(*Examen progresivo - Test de nivel v.1.3*). Students take it in a browser,
one question at a time; the teacher reads everyone's grades in a private
console and exports them to Excel.

## How a student takes it

1. **Gate.** Instructions, then name, class, and the shared access code.
2. **One question at a time**, with a progress bar and a "No lo sé, saltar"
   button. Every answer is saved on the server as soon as it's given, so a
   refresh, a dead battery, or a switch to another device resumes where the
   student left off (same name and class).
3. **Stop rule, live.** After each block of 20 questions (one CEFR level), if
   the block has more than 6 errors the test ends. Weaker students aren't
   dragged through questions far above their level.
4. **Result.** Level and points. A student who finished can't retake unless
   the teacher deletes their attempt in the console.

## Architecture

Plain Flask app with a local SQLite database. No third-party services.

- `index.html` — static single-page student UI. It never receives the answer
  key or the level of a question.
- `app.py` — serves questions one at a time, grades each answer, applies the
  stop rule, stores attempts, and hosts the teacher console.
- `results.db` — SQLite: `attempts` and `answers` tables. Created automatically.

## Run

```bash
pip3 install --user -r requirements.txt
ACCESS_CODE=hola2026 TEACHER_PASSWORD=yourpassword python3 app.py
```

- Student test: <http://127.0.0.1:5000/>
- Teacher console: <http://127.0.0.1:5000/teacher> (any username, password =
  `TEACHER_PASSWORD`). Shows the access code, every attempt with status and
  per-level scores, a **Download CSV (Excel)** button, and a **Borrar** button
  per attempt to allow a retake.

Defaults if unset: `ACCESS_CODE=clase`, `TEACHER_PASSWORD=changeme`. Set both.

## Run the test for a class

Free, from the teacher's laptop over a public Cloudflare tunnel:

```bash
ACCESS_CODE=hola2026 TEACHER_PASSWORD=yourpassword ./serve.sh
```

It prints a `https://…trycloudflare.com` URL to share with students; add
`/teacher` for the console. See `DEPLOY.md` for the one-time `cloudflared`
install and for always-on hosting on PythonAnywhere.

## Scoring

- 120 multiple-choice questions, one correct answer each.
- 20 questions per level, in order: A1, A2, B1, B2, C1, C2.
- **Points** = total correct (a skipped question counts as wrong).
- A block is *passed* with **6 or fewer** errors (`maxErrorsPerLevel` in
  `test-data.json`). The test stops after the first failed block.
- **Level** = the last block passed. A student who fails A1 gets `-`
  (shown as "Pre-A1").

## Files

| File | Purpose |
|------|---------|
| `test-data.json` | Source of truth: 120 questions, options, answer key, scoring rules. |
| `index.html` | Student page (gate → questions → result). |
| `app.py` | Flask server: API, grading, stop rule, storage, teacher console, CSV. |
| `serve.sh` | Start app + Cloudflare tunnel for a class session. |
| `pythonanywhere_wsgi.py` | WSGI entry for PythonAnywhere hosting. |
| `requirements.txt` | Python dependencies (Flask). |

Note: question 115 has three options (a–c); all others have four.

## Copyright

The test content is © ProfeDeELE.es, licensed for non-commercial classroom
use. The access code keeps the questions off the open web.
