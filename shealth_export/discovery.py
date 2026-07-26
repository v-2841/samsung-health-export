"""Find the export folder to parse.

A Samsung Health export folder is named ``samsunghealth_v-<ver>_<timecode>``
(e.g. ``samsunghealth_v-2841_20260722105897``). We pick the one with the
newest ``timecode`` inside the given data directory.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

_NAME_RE = re.compile(r"^samsunghealth_.*?_(\d{8,})$")


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
            candidates.append(Export(path=full, name=name, timecode=m.group(1)))
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.timecode)


def as_export(folder: str) -> Export | None:
    """Wrap an explicit ``--folder`` path as an :class:`Export`."""
    folder = folder.rstrip("/")
    if not os.path.isdir(folder):
        return None
    name = os.path.basename(folder)
    m = _NAME_RE.match(name)
    timecode = m.group(1) if m else ""
    return Export(path=folder, name=name, timecode=timecode)
