#!/usr/bin/env python3
"""Optional browser test for the V17 handoff.

Requires Playwright and a Chromium executable. The script does not alter browser
policies. Set CHROMIUM_PATH if Chromium is not at /usr/bin/chromium.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium")
URL = os.environ.get("PANTA_URL", f"file://{ROOT / 'app' / 'index.html'}?mode=demo")


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROMIUM, args=["--no-sandbox", "--allow-file-access-from-files"])
        for width, height in [(1280, 720), (1440, 900), (1920, 1080)]:
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(URL, wait_until="load")
            page.wait_for_timeout(500)
            results.append(page.evaluate("""({
                viewport:[innerWidth,innerHeight],
                selftest:PantaSelfTest.run(),
                scrollWidth:document.documentElement.scrollWidth,
                scrollHeight:document.documentElement.scrollHeight
            })""" ) | {"errors": errors})
            page.close()
        browser.close()
    (ROOT / "tests" / "BROWSER_TEST_RESULTS.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if any(item["errors"] or item["selftest"]["passed"] != item["selftest"]["total"] for item in results):
        raise SystemExit(1)
    print("PANTA V17 browser smoke test passed at three resolutions.")


if __name__ == "__main__":
    main()
