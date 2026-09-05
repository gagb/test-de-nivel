# Test de nivel — online placement test

An online version of the ProfeDeELE.es progressive Spanish placement test
(*Examen progresivo - Test de nivel v.1.3*), built so students take it in a
browser and results land in a spreadsheet.

## Status

- [x] `test-data.json` — all 120 questions, options and answer key, transcribed
  verbatim from the source PDF, grouped into the six CEFR levels (A1–C2).
- [ ] Student-facing web page (single HTML file).
- [ ] Results collector (Google Apps Script → Google Sheet / Excel).
- [ ] Hosting.

## Test structure

- 120 multiple-choice questions, one correct answer each.
- 20 questions per level, in order: A1, A2, B1, B2, C1, C2.
- A level is *passed* with **6 or fewer** wrong answers out of its 20.
- The test is progressive: a student's level is the highest level they pass
  before the first level they fail.

## Data format

`test-data.json` holds a `meta` block (level ranges, thresholds, source notes)
and a `questions` array. Each question:

```json
{
  "n": 1,
  "level": "A1",
  "prompt": "A - ¿Quién eres?\nB - ___ Lorena.",
  "options": { "a": "Soy", "b": "Eres", "c": "Es", "d": "Son" },
  "answer": "a"
}
```

Note: question 115 has three options (a–c); all others have four.

## Copyright

The test content is © ProfeDeELE.es, licensed for non-commercial classroom use.
Keep any hosted version private or password-protected rather than public.
