"""Allow ``python3 -m shealth_export`` as an alternative entry point."""

from .cli import main

if __name__ == '__main__':
    raise SystemExit(main())
