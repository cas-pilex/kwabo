"""Wipe the LLM response cache."""
from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    from kwabo.config import settings

    d = Path(settings.llm_cache_dir)
    if not d.exists():
        print(f"(geen cache-dir: {d})")
        return
    n = sum(1 for _ in d.glob("*.json"))
    shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    print(f"Wiped {n} cache entries at {d}")


if __name__ == "__main__":
    main()
