"""Samsung Health export -> single doctor-facing JSON.

A small, dependency-free toolkit that reads a Samsung Health data export
and produces one self-describing JSON file containing every medical data
type, filtered to the last N days, with an embedded legend and a coverage
manifest so nothing is ever dropped silently.

See INSTRUCTIONS_FOR_AI.md for how to read the produced file.
"""

__version__ = "1.0.0"
