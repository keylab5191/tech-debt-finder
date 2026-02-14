# Timing analysis — why ~6 minutes?

## File-by-file breakdown (from your run)

| File | Wall time | Prompt size | LLM tokens | Notes |
|------|-----------|-------------|------------|--------|
| `__init__.py` | **0.00s** | — | — | Skipped (file &lt; 150 chars) |
| `__main__.py` | **0.00s** | — | — | Skipped (file &lt; 150 chars) |
| **`cli.py`** | **320.13s** | 10,152 chars | 1024 | **Outlier: ~5 min** |
| `models.py` | 6.92s | 2,494 chars | 462 | Normal |
| `report.py` | 7.84s | 5,378 chars | 492 | Normal |
| `reviewer.py` | 12.02s | 15,045 chars | 686 | Normal |
| `scanner.py` | 8.79s | 4,642 chars | 4642 | Normal |

**Total LLM-reviewed files:** 5. **Sum of “normal” files:** 6.92 + 7.84 + 12.02 + 8.79 ≈ **35.6s**. So without `cli.py`, the run would be **~36s**, which matches your 10–20s-per-file expectation.

---

## Why is `cli.py` so slow?

Reported for `cli.py`:

- **Load:** 2.7s  
- **Generation:** 1024 tokens in 15.16s (~67.54 t/s) → ~15s  
- **Total “Ollama returned”:** 320.13s  

So **320 − 2.7 − 15 ≈ 302 seconds** are unaccounted for in the current logs. That time is almost certainly **prompt evaluation**: Ollama processing the ~10k-character prompt (system + user) through the model before generating. The reviewer now logs **prompt eval** when it’s &gt; 0.5s, so on the next run you should see something like:

`Prompt eval 302.0s. 1024 tokens in 15.16s (67.54 t/s)`

for `cli.py`.

Why is prompt eval huge only for the first file?

1. **First request = cold start.** The model is loaded (2.7s), then the **first** large prompt is processed. That first prompt eval can be much slower (CPU/GPU warmup, memory layout, etc.).
2. **Subsequent files are warm.** You use `keep_alive: "30m"`, so the model stays in memory. For `models.py`, `report.py`, etc., prompt eval is then in the usual few-seconds range.
3. **`cli.py` is the first “big” file.** `__init__.py` and `__main__.py` are skipped, so the first real LLM call is for `cli.py` with a 10k-char prompt. That first big prompt pays the full cold cost.

So: **overall time is dominated by the first large file’s prompt evaluation**, not by generation speed.

---

## Summary

- **Per-file (after first):** ~7–12s per file is expected and matches 10–20s.
- **Total ~6 min:** Almost all of it is the **first file** (`cli.py`): one-time model load + very slow **first** prompt eval (~302s) + normal generation (~15s).
- **Next run:** The reviewer now prints `Prompt eval X.Xs` when it’s &gt; 0.5s so you can confirm this.

---

## Optional: shorten first-file cost

If you want the first file to be closer to 10–20s:

1. **Warm the model in pre-flight:** In `test_ollama`, after the minimal “Reply with exactly: OK” call, do a second generate with a medium-sized dummy prompt (e.g. a few KB) and `num_predict: 1`. That way the “cold” prompt eval happens during the Ollama check, and the first real file reuses the warm model.
2. **Or accept the first-file spike:** Running once per session, a 5–6 min total (with one 5 min file) may be acceptable; the rest of the files are already fast.
