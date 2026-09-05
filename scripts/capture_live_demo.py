from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE_URL = "https://careflow-demo.onrender.com"
OUTPUT_DIR = Path("artifacts/demo")


async def hold(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def wait_for_draft(page: Page) -> None:
    await page.wait_for_function(
        """
        () => {
          const value = document.getElementById('draft-status')?.textContent?.trim();
          return value && value !== '미생성' && value !== 'processing';
        }
        """,
        timeout=30_000,
    )


async def wait_for_operations(page: Page) -> None:
    """Wait for the visible Operations view and its runtime data, not a CSS-only grid."""
    await page.locator("#view-operations").wait_for(state="visible")
    await page.wait_for_function(
        """
        () => {
          const db = document.getElementById('op-db')?.textContent?.trim();
          const store = document.getElementById('op-store')?.textContent?.trim();
          return Boolean(db && db !== '-' && store && store !== '-');
        }
        """,
        timeout=20_000,
    )


async def switch_view(page: Page, view: str) -> None:
    await page.locator(f"[data-view='{view}']").click()
    await hold(1.5)


async def capture() -> None:
    await asyncio.to_thread(OUTPUT_DIR.mkdir, parents=True, exist_ok=True)
    raw_dir = OUTPUT_DIR / "raw"
    await asyncio.to_thread(raw_dir.mkdir, parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(raw_dir),
            record_video_size={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
        await page.locator("#system-status").wait_for(state="visible")

        # 1) Product overview: give the viewer time to read the workflow and boundaries.
        await hold(7)

        # 2) Run the normal synthetic path all the way through READY + purge.
        await page.locator("#guided-demo").click()
        await wait_for_draft(page)
        await hold(10)

        # 3) Show a safety-signal path that must go to human review.
        await page.locator("[data-scenario='safety_signal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count').textContent.includes('3 utterances')",
            timeout=20_000,
        )
        await hold(3)
        await page.locator("#finalize").click()
        await wait_for_draft(page)
        await hold(9)

        # 4) Review Queue makes the human-in-the-loop decision visible.
        await switch_view(page, "queue")
        await hold(8)

        # 5) AI Quality exposes adopted/rejected experiments rather than model-name decoration.
        await switch_view(page, "quality")
        await page.locator("#quality-grid").wait_for(state="visible")
        await hold(10)

        # 6) Operations shows the truthful public-demo runtime and health state.
        await switch_view(page, "operations")
        await wait_for_operations(page)
        await hold(10)

        # Close on the overview so the final frame returns to the product story.
        await switch_view(page, "overview")
        await hold(5)

        if page.video is None:
            raise RuntimeError("Playwright did not create a video recording")
        video = page.video
        await page.close()
        raw_path = await video.path()
        await context.close()
        await browser.close()

    await asyncio.to_thread(
        shutil.copy2,
        raw_path,
        OUTPUT_DIR / "careflow-live-demo.webm",
    )


if __name__ == "__main__":
    asyncio.run(capture())
