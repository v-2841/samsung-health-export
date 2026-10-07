"""Find the export folder to parse.

A Samsung Health export folder is named ``samsunghealth_<account>_<timecode>``
(e.g. ``samsunghealth_<account>_20260722105897``). We pick the one with the
newest ``timecode`` inside the given data directory. A renamed folder still
works: the timecode is then read from the CSV file names inside it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .csvio import detect_timecode

_NAME_RE = re.compile(r'^samsunghealth_.*?_(\d{8,})$')


@dataclass(frozen=True)
class Export:
    path: str
    name: str
    timecode: str


def find_latest_export(data_dir: str) -> Export | None:
    if not os.path.isdir(data_dir):
        return None
    candidates: list[Export] = []
    for name in os.listdir(data_dir):
        full = os.path.join(data_dir, name)
        if not os.path.isdir(full):
            continue
        m = _NAME_RE.match(name)
        if m:
            candidates.append(Export(path=full, name=name,
                                     timecode=m.group(1)))
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.timecode)


def as_export(folder: str) -> Export | None:
    """Wrap an explicit ``--folder`` path as an :class:`Export`.

    Returns None when the folder is missing or contains no Samsung CSVs.
    """
    folder = folder.rstrip('/')
    if not os.path.isdir(folder):
        return None
    name = os.path.basename(folder)
    timecode = detect_timecode(folder)
    if not timecode:
        return None
    return Export(path=folder, name=name, timecode=timecode)
