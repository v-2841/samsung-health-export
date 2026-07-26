# samsung-health-export

Turn a **Samsung Health** data export into a **single, self-describing JSON file**
covering the last *N* days — designed to be handed to a doctor whose AI assistant
analyses it.

- **All medical data, nothing dropped silently.** Every datatype in the export is
  accounted for in a coverage manifest (included / excluded-with-reason / unknown).
- **Private by design.** Only medical fields are read; device ids, Bluetooth/MAC,
  GPS routes, names and app config never leave the CSV.
- **Self-describing.** The output embeds a legend (units, code tables, caveats) plus
  a coverage manifest, so it is readable even without this repo.
- **Zero dependencies.** Pure Python standard library.

---

## Requirements

- Python **3.9+** (no `pip install` needed).

## Quick start

1. Export your data from the Samsung Health app
   (*Settings → Download personal data*) and unzip it.
2. Put the export folder (named like `samsunghealth_v-2841_20260722105897`) inside a
   `data/` directory next to `export_health.py`.
3. Run:

```bash
python3 export_health.py
# → asks "How many days back should be exported?" then writes the JSON here
```

Non-interactive:

```bash
python3 export_health.py --days 14
python3 export_health.py --days 14 --out-dir ~/exports
```

The tool writes two files: a pretty `health_export_<start>_to_<end>.json` and a
compact `….min.json` (~half the size, best for uploading to an AI).

## Command-line options

| Option | Meaning |
|---|---|
| `--days N` | Number of days back to include. If omitted, the tool asks interactively. |
| `--out-dir DIR` | Destination directory (created if missing). Default: current directory. |
| `--out PATH` | Output filename/path. Default: `health_export_<start>_to_<end>.json`. |
| `--folder PATH` | Use a specific export folder instead of auto-picking from `data/`. |
| `--data-dir DIR` | Where to look for export folders. Default: `data`. |
| `--anchor YYYY-MM-DD` | End date of the window. Default: the export's own date. |
| `--no-minify` | Do not also write the compact `.min.json`. |
| `--selftest` | Run correctness self-checks (incl. an empirical timezone proof) and exit. |

If several exports sit in `data/`, the newest (by timecode) is used automatically.

## What's in the output

```
metadata          export info, the day window, units, language
patient_profile   sex, age, height, latest weight, BMI, unit prefs (name/ids stripped)
legend            units per field, decoded code tables, interpretation caveats
coverage_manifest every datatype in the source and what happened to it
data              the measurements, grouped by clinical category
```

Categories under `data`: `cardiovascular`, `respiratory`, `body`, `sleep`,
`activity`, `stress`, `readiness`, `mental`, `exercise`, `nutrition`. High-resolution
per-minute series are nested under `detail` / `live_data` / `recovery_samples` /
`hypnogram`.

### Two things to understand when reading it

- **Timestamps are local ISO-8601** (e.g. `2026-07-13T01:20:00+04:00`). Samsung stores
  wall-clock strings in UTC; the tool shifts them to the local time actually
  experienced, using each record's `time_offset`. (Verified empirically — see
  `--selftest`.)
- **Absence ≠ normal.** A datatype with `rows_in_window: 0` but a `last_record` date
  was *not measured in this period*, not "normal". Blood pressure, glucose and food
  logs in a typical recent window are often empty for this reason — the manifest makes
  that explicit so a reader never mistakes missing data for a healthy reading.

## Sharing with a doctor

Give the doctor **two files**:

1. the `….min.json` result, and
2. [`INSTRUCTIONS_FOR_AI.md`](INSTRUCTIONS_FOR_AI.md) — tells their AI how to read it.

> ⚠️ These files contain personal medical data. They are git-ignored by default; share
> them deliberately, not by committing them.

## Architecture

A small package with one responsibility per module (`shealth_export/`):

| Module | Responsibility |
|---|---|
| `registry.py` | **Declarative spec** of every datatype: fields, units, codes, binning. Add a datatype = add a data entry, not code. |
| `csvio.py` | Samsung CSV reader (BOM, metadata line, namespaced columns, ragged rows). |
| `timeutil.py` | Pure time helpers: UTC-string + offset → local ISO, epoch-ms, day windowing. |
| `binning.py` | Load & map the high-resolution binning JSON, filtered to the window. |
| `extract.py` | Generic extractor + special handlers (sleep hypnogram, food names, dedup, profile). |
| `enums.py` | Code → label tables (sleep stages, meal/exercise types, …). |
| `coverage.py` | Build the coverage manifest. |
| `legend.py` | Build the embedded, self-describing legend. |
| `assemble.py` | Assemble the final document and write pretty + minified. |
| `discovery.py` | Find the newest export folder. |
| `cli.py` | Argument parsing, interactive prompt, orchestration. |
| `selftest.py` | Unit checks + empirical timezone proof against real data. |

Privacy is enforced structurally: only columns listed in `registry.py` are read, so
identifiers and GPS can't leak. To include a new field or datatype, edit the registry.

## Disclaimer

This is **consumer wearable data**, not medical-grade instrumentation, and several
metrics (`stress`, `vitality`, sleep recovery scores) are proprietary Samsung indices,
not validated clinical measures. The tool aids review; it does not diagnose.

## License

[MIT](LICENSE).
