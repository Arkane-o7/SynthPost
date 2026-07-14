#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from pipeline.diagnostics import exit_code, run_diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check SynthPost configuration and local dependencies."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--config-only", action="store_true", help="Validate configuration only."
    )
    parser.add_argument(
        "--strict-features",
        action="store_true",
        help="Treat unavailable feature dependencies/providers as failures.",
    )
    args = parser.parse_args()
    checks = run_diagnostics(config_only=args.config_only)
    if args.json:
        print(json.dumps([check.as_dict() for check in checks], indent=2))
    else:
        for check in checks:
            marker = "OK" if check.ok else "FAIL"
            print(
                f"[{marker}] {check.name:<16} {check.status:<16} "
                f"({check.requirement}) {check.detail}"
            )
            if check.remedy and not check.ok:
                print(f"       remedy: {check.remedy}")
    return exit_code(checks, strict_features=args.strict_features)


if __name__ == "__main__":
    raise SystemExit(main())
