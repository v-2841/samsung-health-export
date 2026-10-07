"""Build the coverage manifest.

The manifest is the promise that *nothing is dropped silently*: every datatype
present in the export is listed with its status — included (with row counts
and the dates of its oldest/newest record), consumed by another section,
deliberately excluded (with a reason), or — importantly — UNKNOWN: a datatype
this tool has never seen, which a future export might introduce. The same
goes for every kind of companion file under ``jsons/`` and ``files/``.
"""

from __future__ import annotations

import csv
import os
from collections import Counter

from . import csvio
from .extract import Result
from .registry import CONSUMED, EXCLUDED, JSON_KINDS, by_id


def _count_rows(path: str) -> int:
    try:
        with open(path, encoding='utf-8-sig', newline='') as f:
            reader = csv.reader(f)
            next(reader, None)   # metadata
            next(reader, None)   # header
            return sum(1 for r in reader if r)
    except OSError:
        return -1


def _kind(filename: str) -> str:
    """``<uuid>.com.samsung.health.x.live_data.json`` -> ``live_data``."""
    rest = filename.split('.', 1)[1] if '.' in filename else filename
    if rest.endswith('.json'):
        rest = rest[:-5]
    parts = [p for p in rest.split('.') if p]
    return parts[-1] if parts else rest


def companion_files(export_dir: str) -> dict[str, Counter]:
    """datatype -> Counter(kind -> file count) for jsons/ and files/."""
    out: dict[str, Counter] = {}
    for top in ('jsons', 'files'):
        root = os.path.join(export_dir, top)
        if not os.path.isdir(root):
            continue
        for dtid in sorted(os.listdir(root)):
            base = os.path.join(root, dtid)
            if not os.path.isdir(base):
                continue
            counter = out.setdefault(dtid, Counter())
            for _, _, names in os.walk(base):
                for name in names:
                    if not name.endswith(csvio.JUNK_SUFFIX):
                        counter[_kind(name)] += 1
    return out


def _companions(dtid: str, kinds: Counter, unknown: list) -> list[dict]:
    known = JSON_KINDS.get(dtid, {})
    out = []
    for kind, n in sorted(kinds.items()):
        status, note = known.get(kind, ('UNKNOWN', 'file kind not known to '
                                        'this tool version — review'))
        if status == 'UNKNOWN':
            unknown.append(f'{dtid}:{kind}')
        out.append({'kind': kind, 'files': n, 'status': status,
                    'note': note})
    return out


def build(export_dir: str, timecode: str, results: dict[str, Result]) -> dict:
    present = csvio.list_datatypes(export_dir, timecode)
    files = companion_files(export_dir)
    included = by_id()
    entries: list[dict] = []
    unknown: list[str] = []
    unknown_files: list[str] = []

    for dtid in present:
        path = csvio.csv_path(export_dir, dtid, timecode)
        if dtid in included:
            r = results.get(dtid) or Result(payload=None)
            dt = included[dtid]
            if not dt.subkey:   # the patient_profile header, not a series
                entry = {
                    'datatype': dtid, 'status': 'included_header',
                    'category': dt.category,
                    'note': 'emitted as patient_profile header; not '
                            'filtered by the day window',
                    'fields_total': r.rows_total,
                }
            else:
                entry = {
                    'datatype': dtid, 'status': 'included',
                    'category': dt.category, 'section': dt.subkey,
                    'description': dt.friendly,
                    'rows_total': r.rows_total,
                    'rows_in_window': r.rows_in_window,
                    'detail_items_in_window': r.detail_items,
                    'first_record': r.first_record,
                    'last_record': r.last_record,
                }
                if r.source_rows_in_window != r.rows_in_window:
                    entry['source_rows_in_window'] = r.source_rows_in_window
                if r.offset_assumed:
                    entry['rows_with_assumed_utc_offset'] = r.offset_assumed
                if r.duplicates_dropped:
                    entry['duplicate_detail_points_dropped'] = (
                        r.duplicates_dropped)
        elif dtid in CONSUMED:
            entry = {'datatype': dtid, 'status': 'consumed',
                     'note': CONSUMED[dtid], 'rows_total': _count_rows(path)}
        elif dtid in EXCLUDED:
            kind, reason = EXCLUDED[dtid]
            entry = {'datatype': dtid, 'status': 'excluded',
                     'exclusion_kind': kind, 'reason': reason,
                     'rows_total': _count_rows(path)}
        else:
            unknown.append(dtid)
            entry = {'datatype': dtid, 'status': 'UNKNOWN',
                     'note': 'datatype not known to this tool version — '
                             'review manually',
                     'rows_total': _count_rows(path)}
        if dtid in files:
            entry['companion_files'] = _companions(dtid, files[dtid],
                                                   unknown_files)
        entries.append(entry)

    # companion folders whose CSV is absent
    for dtid in sorted(set(files) - set(present)):
        entries.append({
            'datatype': dtid, 'status': 'companion_only',
            'note': 'files without a CSV table',
            'companion_files': _companions(dtid, files[dtid], unknown_files),
        })

    # datatypes we expected but that are missing from this export
    missing = [dtid for dtid in included if dtid not in present]
    for dtid in missing:
        entries.append({'datatype': dtid, 'status': 'missing_from_export'})

    entries.sort(key=lambda e: (e['status'] != 'UNKNOWN', e['status'],
                                e['datatype']))

    incl = [e for e in entries if e['status'] == 'included']
    summary = {
        'datatypes_present': len(present),
        'included': len(incl),
        'included_with_data_in_window': sum(
            1 for e in incl if e.get('rows_in_window')),
        'consumed': sum(1 for e in entries if e['status'] == 'consumed'),
        'excluded': sum(1 for e in entries if e['status'] == 'excluded'),
        'unknown': len(unknown),
        'missing_from_export': len(missing),
        'companion_file_kinds_unknown': len(unknown_files),
    }
    if unknown:
        summary['unknown_datatypes'] = unknown
    if unknown_files:
        summary['unknown_companion_kinds'] = unknown_files
    if missing:
        summary['missing_datatypes'] = missing
    return {'summary': summary, 'datatypes': entries}
