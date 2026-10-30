"""The standalone build's entry point: the `dogear` command itself.

The frozen program takes the same arguments as `dogear` (`dogear make ...`). `dogear
serve` relies on that: when frozen, it runs each book as `[sys.executable, "make", ...]`.
"""

from dogear.cli import main

raise SystemExit(main())
