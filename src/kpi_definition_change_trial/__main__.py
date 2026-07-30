from __future__ import annotations

import argparse
from pathlib import Path

from .runner import execute


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the frozen canonical golden bundle")
    parser.add_argument("command", choices=("golden",))
    parser.add_argument("--fixtures", type=Path, default=Path("fixtures"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/golden"))
    parser.add_argument("--schemas", type=Path, default=Path("schemas"))
    args = parser.parse_args()
    execute(args.fixtures, args.output, args.schemas)
    print("PASS: deterministic canonical golden evidence written")


if __name__ == "__main__":
    main()
