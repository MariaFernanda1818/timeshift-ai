"""Capture the dashboard replaying a recorded run at several viewport widths.

    python scripts/screenshot_ui.py --replay solar_cascade --out docs/screenshots
"""

from __future__ import annotations

import argparse
import pathlib

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080/")
    ap.add_argument("--replay", default="solar_cascade")
    ap.add_argument("--branch", default=None, help="branch card to click, e.g. B3")
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--widths", default="1920,1440,390")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader"])
        for w in [int(x) for x in a.widths.split(",")]:
            page = browser.new_page(viewport={"width": w, "height": 1080 if w > 600 else 844})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(a.url)
            page.wait_for_selector("select[aria-label='Recorded runs'] option[value='%s']" % a.replay,
                                   state="attached")
            page.select_option("select[aria-label='Replay speed']", "4")
            page.select_option("select[aria-label='Recorded runs']", a.replay)
            page.wait_for_selector("text=COMPLETE", timeout=120000)
            page.wait_for_timeout(2500)
            if a.branch:
                page.locator(f"button:has-text('{a.branch} ·')").first.click()
                page.wait_for_timeout(800)
            suffix = f"-{a.branch}" if a.branch else ""
            path = out / f"{a.replay}{suffix}-{w}.png"
            page.screenshot(path=str(path), full_page=True)
            scroll_w = page.evaluate("document.documentElement.scrollWidth")
            print(f"{path}  scrollWidth={scroll_w} (viewport {w})  console errors: {errors[:3]}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
