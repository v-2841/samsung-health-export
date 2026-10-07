"""Orchestrate extraction and assemble the final self-describing document."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime

from . import __version__, coverage, legend, timeutil
from .csvio import csv_path, read_table
from .discovery import Export
from .extract import Context, Extractor
from .registry import INCLUDED


def detect_primary_offset(export: Export) -> str:
    """Most common UTC offset among heart-rate rows (dense, always present)."""
    path = csv_path(export.path, 'com.samsung.shealth.tracker.heart_rate',
                    export.timecode)
    if path:
        table = read_table(path, 'com.samsung.health.heart_rate.')
        offsets = Counter(r.get('time_offset') for r in table.rows
                          if timeutil.parse_offset(r.get('time_offset')))
        if offsets:
            return offsets.most_common(1)[0][0]
    return 'UTC+0000'


def _window_meta(ctx: Context, n_days: int) -> dict:
    meta = ctx.window.as_dict(n_days, ctx.primary_offset)
    meta['offsets_in_window'] = [
        {'utc_offset': off, 'first_day': v[0].isoformat(),
         'last_day': v[1].isoformat(), 'records': v[2]}
        for off, v in sorted(ctx.offsets.items(), key=lambda kv: kv[1][0])
    ]
    partial = ctx.export_date is not None and ctx.window.contains(
        ctx.export_date)
    meta['end_day_partial'] = partial
    if ctx.cutoff:
        instant, offset = ctx.cutoff
        meta['data_cutoff'] = timeutil.utc_string_to_iso(
            instant.strftime('%Y-%m-%d %H:%M:%S'), offset)
    if partial:
        meta['partial_day_note'] = (
            f'{ctx.export_date.isoformat()} is the export day: its daily '
            'totals stop at data_cutoff and are not a full day.')
    return meta


def build_document(export: Export, n_days: int,
                   anchor: date) -> tuple[dict, dict]:
    primary_offset = detect_primary_offset(export)
    window = timeutil.Window.last_n_days(anchor, n_days)
    ctx = Context(export_dir=export.path, timecode=export.timecode,
                  window=window, primary_offset=primary_offset,
                  anchor_date=anchor,
                  export_date=timeutil.timecode_to_date(export.timecode))
    extractor = Extractor(ctx)

    results = {}
    patient_profile: dict = {}
    data: dict = {}
    for dt in INCLUDED:
        res = extractor.run(dt)
        results[dt.id] = res
        if dt.handler == 'user_profile':
            patient_profile = res.payload
        else:
            data.setdefault(dt.category, {})[dt.subkey] = res.payload

    manifest = coverage.build(export.path, export.timecode, results)

    document = {
        'metadata': {
            'generated_at': datetime.now().astimezone().replace(
                microsecond=0).isoformat(),
            'tool': 'shealth_export',
            'tool_version': __version__,
            'source_export_timecode': export.timecode,
            'window': _window_meta(ctx, n_days),
            'anchor_date': anchor.isoformat(),
            'detail_level': 'full (per-minute where available)',
            'scope': 'all medical data; technical/config/GPS/identifiers '
                     'excluded',
            'language': 'en',
        },
        'patient_profile': patient_profile,
        'legend': legend.build(),
        'coverage_manifest': manifest,
        'data': data,
    }
    return document, manifest


def _dump(document: dict, path: str, minified: bool) -> int:
    with open(path, 'w', encoding='utf-8') as f:
        if minified:
            json.dump(document, f, ensure_ascii=False, separators=(',', ':'))
        else:
            json.dump(document, f, ensure_ascii=False, indent=2)
    return os.path.getsize(path)


def min_path(out_path: str) -> str:
    """Companion minified path: foo.json -> foo.min.json."""
    if out_path.endswith('.json'):
        return out_path[:-5] + '.min.json'
    return out_path + '.min.json'


def write(document: dict, out_path: str,
          minify: bool = True) -> tuple[int, str | None, int]:
    """Write the pretty JSON and (by default) a compact ``.min.json``.

    Returns (pretty_size, min_path_or_None, min_size).
    """
    size = _dump(document, out_path, minified=False)
    if not minify:
        return size, None, 0
    mp = min_path(out_path)
    return size, mp, _dump(document, mp, minified=True)
