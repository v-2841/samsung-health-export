"""Samsung Health CSV reader.

Quirks handled here (verified against the real export):

* UTF-8 **BOM** on the first byte -> opened with ``utf-8-sig``.
* Line 1 is a **metadata** line ``<datatype>,<version>,<n>`` (skipped).
* Line 2 is the real **header**; data starts on line 3.
* Some tables namespace their columns
  (``com.samsung.health.heart_rate.start_time``); callers can look up either
  the full name or the short name via ``Row.get``.
* Every data row ends with one extra empty field (a trailing comma); ``zip``
  with the header drops it, so columns never shift.
* Some tables embed JSON blobs / quoted commas; a standard ``csv.reader``
  over the file object handles the quoting.
* File names are matched **exactly** as ``<datatype>.<timecode>.csv`` — a
  glob like ``exercise.*`` would wrongly also match ``exercise.extension``.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass

# Windows "mark of the web" side-car files that sit next to the real CSVs.
JUNK_SUFFIX = ':Zone.Identifier'

_CSV_RE = re.compile(r'^(?P<dt>.+)\.(?P<tc>\d{8,})\.csv$')


def csv_path(export_dir: str, datatype: str, timecode: str) -> str | None:
    """Absolute path to ``<datatype>.<timecode>.csv`` if it exists."""
    p = os.path.join(export_dir, f'{datatype}.{timecode}.csv')
    return p if os.path.isfile(p) else None


class Row:
    """A data row; resolves columns by full or prefix-stripped short name."""

    __slots__ = ('_data', '_prefix')

    def __init__(self, data: dict[str, str], prefix: str = ''):
        self._data = data
        self._prefix = prefix

    def get(self, name: str, default: str = '') -> str:
        if name in self._data:
            return self._data[name]
        if self._prefix:
            pref = self._prefix + name
            if pref in self._data:
                return self._data[pref]
        return default

    def raw(self) -> dict[str, str]:
        return self._data


@dataclass
class Table:
    datatype: str
    header: list[str]
    rows: list[Row]
    prefix: str = ''
    version: str = ''


def read_table(path: str, prefix: str = '') -> Table:
    """Read a Samsung Health CSV file into a :class:`Table`."""
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        meta = next(reader, [])
        header = next(reader, [])
        datatype = meta[0] if meta else ''
        version = meta[1] if len(meta) > 1 else ''
        rows: list[Row] = []
        for values in reader:
            if not values:
                continue
            # zip stops at the shorter of header/values: the trailing empty
            # field is dropped and short rows simply miss their last columns
            rows.append(Row(dict(zip(header, values)), prefix))
    return Table(datatype=datatype, header=header, rows=rows, prefix=prefix,
                 version=version)


def list_datatypes(export_dir: str, timecode: str) -> list[str]:
    """Every datatype id that has a ``<datatype>.<timecode>.csv`` present."""
    suffix = f'.{timecode}.csv'
    out = []
    for name in os.listdir(export_dir):
        if name.endswith(JUNK_SUFFIX):
            continue
        if name.endswith(suffix):
            out.append(name[: -len(suffix)])
    return sorted(out)


def detect_timecode(export_dir: str) -> str:
    """The most common timecode among ``<datatype>.<timecode>.csv`` names."""
    counts: dict[str, int] = {}
    for name in os.listdir(export_dir):
        m = _CSV_RE.match(name)
        if m:
            counts[m.group('tc')] = counts.get(m.group('tc'), 0) + 1
    return max(counts, key=counts.get) if counts else ''


def iter_json_shard_path(export_dir: str, dir_suffix: str,
                         ref_value: str) -> str | None:
    """Resolve a companion-JSON reference to its sharded path.

    Files live under ``jsons/<dir_suffix>/<first-char-of-name>/<ref_value>``.
    """
    if not ref_value:
        return None
    shard = ref_value[0]
    p = os.path.join(export_dir, 'jsons', dir_suffix, shard, ref_value)
    return p if os.path.isfile(p) else None
