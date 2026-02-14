# Tech Debt Report — Quality Review

**Report:** `tech_debt_report.json`  
**Files scanned:** 7 | **Total issues:** 53

---

## Summary

| File        | Issues | Assessment |
|------------|--------|------------|
| cli.py     | 43     | **Low quality** — mostly duplicate noise |
| report.py  | 6      | **Good** — mix of valid and minor |
| reviewer.py| 1      | **False positive** |
| scanner.py | 3      | **Reasonable** — actionable |
| models.py  | 0      | — |
| __init__.py / __main__.py | 0 | — |

---

## What’s Good

- **report.py** — Solid findings:
  - **Missing error handling in `write_report`** (high): valid; no try/except around file write or directory creation.
  - **Long `print_summary`** (medium): function is long and could be split.
  - **Table duplication** (medium): severity/category table logic is repeated.
  - **`sev_table` naming** (low): fair suggestion.
  - Magic number 30 in bar length (low): minor but consistent with “magic number” guidance.

- **scanner.py** — Reasonable:
  - Long `_yield_code_files` (medium): does several things; splitting is defensible.
  - `target_root` naming (medium): optional but clear suggestion.
  - `BINARY_DETECTION_CHUNK_SIZE` documentation (medium): asking for a docstring is fair.

- **Severity and categories** are used sensibly (high for error handling, medium for complexity/duplication).

---

## What’s Wrong or Noisy

### 1. cli.py — Massive over-reporting (43 issues)

- **Cause:** Model hit `num_predict: 4096` and kept emitting issues. Almost all are the same finding repeated: *“The number 2 is used in the `main` function to format the elapsed time with two decimal places.”*
- **Reality:** The `2` is the precision in format strings like `f".2f"` (e.g. in `_elapsed()`). That’s a format specifier, not a domain “magic number” that should be a named constant.
- **Line ranges:** Many point to lines 185–264; several of those lines are in `main` but the actual “2” is inside `_elapsed(t0)` or similar. So location is approximate and sometimes wrong function.
- **Result:** Dozens of duplicate, low-value items that obscure the few useful ones (e.g. timeouts 30.0, 60.0, 300.0, default max file size 100).

### 2. reviewer.py — False positive

- **Finding:** “Magic Number” for `3060` — “Define a constant for the GPU model name.”
- **Reality:** The `3060` appears only in a **comment**: `# max new tokens (fits 8GB e.g. 3060 Ti)`. It’s example hardware text, not a configurable magic number. No change needed.

### 3. report.py — Minor noise

- **“Readability problems”** with `line_range: null`: very vague (“better formatting and spacing”). Low signal.

---

## Recommendations

1. **Prompt / behavior**
   - Tell the model **not** to report format-specifier numbers (e.g. `.2f`, `.1f`, padding widths) as magic numbers.
   - Tell it to report **at most one issue per logical finding** (e.g. one “magic number” for “timeout constants” with a line range, not 30 separate “number 2” issues).
   - Optionally ask for a **maximum number of issues per file** (e.g. 10–15) and “most important” first to avoid runaway generation.

2. **Deduplication**
   - Post-process: merge issues that share (file, title, same or very similar description) and keep one with a combined or first line_range.

3. **Validation**
   - Ignore or downrank issues whose `line_range` points to comments only (e.g. “3060” in reviewer.py) or to format strings that are clearly not domain magic numbers.

4. **num_predict**
   - Consider lowering `num_predict` for the review task (e.g. 512–1024) so the model stops earlier and produces fewer duplicate issues while still covering the file.

---

## Verdict

- **report.py and scanner.py:** Quality is **good enough to act on** (error handling, structure, naming).
- **cli.py:** Quality is **poor** for that file; the 43 issues are mostly one repeated, low-value finding. Rely on report.py/scanner.py (and optionally reviewer.py’s real logic) and treat cli.py’s magic-number list as noise unless we tighten the prompt and/or add deduplication and filters.
