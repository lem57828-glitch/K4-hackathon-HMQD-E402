#!/usr/bin/env python3
"""Run all unit tests for the Discord QA Assistant project."""

import os
import sys
import unittest
from pathlib import Path

# Ensure codebase directory is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
CODEBASE_DIR = ROOT_DIR / "codebase"
TESTS_DIR = ROOT_DIR / "tests"

if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 60)
    print("  Discord QA Assistant — Unit Test Suite Runner")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(TESTS_DIR), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"✅ SUCCESS: Ran {result.testsRun} tests cleanly without failures.")
        print("=" * 60)
        return 0
    else:
        print(
            f"❌ FAILURES: Ran {result.testsRun} tests with {len(result.failures)} failures "
            f"and {len(result.errors)} errors."
        )
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
