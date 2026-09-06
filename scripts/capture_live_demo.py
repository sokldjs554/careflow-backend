from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE_URL = "https://careflow-demo.onrender.com"
OUTPUT_DIR = Path("artifacts/demo")


async def hold(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def wait_for_d_home(page: Page) -> None:
    """Verify the selected D reference is what the browser actually paints."""
    await page.wait_for_function(
        """
        () => {
          if (document.body.dataset.view !== 'overview') return false;
          const heroTitle = document.querySelector('.hero h1');
          const heroCopy = document.querySelector('.hero p');
          const heroVisual = document.querySelector('.hero-flow');
          const rail = document.querySelector('.rail');
          const topbar = document.querySelector('.topbar');
          const intro = document.querySelector('[data-intro="features"]');
          if (!heroTitle || !heroCopy || !heroVisual || !rail || !topbar || !intro) return false;

          const titleStyle = getComputedStyle(heroTitle, '::after');
          const title = titleStyle.content || '';
          const copy = getComputedStyle(heroCopy, '::after').content || '';
          const visualStyle = getComputedStyle(heroVisual, '::after');
          const background = visualStyle.backgroundImage || '';
          const cardTitles = [...document.querySelectorAll('.feature-card h3')].map(
            (node) => getComputedStyle(node, '::after').content || ''
          );
          const navLabels = [...document.querySelectorAll('.nav button')].map(
            (node) => getComputedStyle(node, '::after').content || ''
          );

          return title.includes('오늘도')
            && title.includes('누군가의 마음이 조금 더 가벼워집니다.')
            && titleStyle.fontSize === '32px'
            && titleStyle.whiteSpace === 'pre'
            && copy.includes('의료진의 소중한 시간을 지켜주고')
            && copy.includes('더 깊은 대화에 집중할 수 있도록')
            && getComputedStyle(rail).display === 'flex'
            && getComputedStyle(topbar).display === 'none'
            && background.includes('data:image/webp;base64')
            && visualStyle.opacity !== '0'
            && ['상담 내용 기록', '근거 연결 요약', '검토 필요 신호', '원문 수명주기'].every(
              (label) => cardTitles.some((value) => value.includes(label))
            )
            && ['홈', '상담 기록', '검토 대기', '분석'].every(
              (label) => navLabels.some((value) => value.includes(label))
            );
        }
        """,
        timeout=20_000,
    )

    asset_loaded = await page.evaluate(
        """
        async () => {
          const heroVisual = document.querySelector('.hero-flow');
          if (!heroVisual) return false;
          const background = getComputedStyle(heroVisual, '::after').backgroundImage || '';
          const match = background.match(/^url\\(["']?(.*?)["']?\\)$/);
          if (!match) return false;
          const image = new Image();
          return await new Promise((resolve) => {
            image.onload = () => resolve(image.naturalWidth > 0 && image.naturalHeight > 0);
            image.onerror = () => resolve(false);
            image.src = match[1];
          });
        }
        """
    )
    if not asset_loaded:
        raise RuntimeError("D hero room visual did not decode in the browser")


async def wait_for_light_workspace(page: Page) -> None:
    await page.wait_for_function(
        """
        () => {
          if (document.body.dataset.view !== 'console') return false;
          const main = document.querySelector('.main');
          const rail = document.querySelector('.rail');
          const transcript = document.querySelector('.transcript');
          if (!main || !rail || !transcript) return false;
          const mainBg = getComputedStyle(main).backgroundColor;
          const railBg = getComputedStyle(rail).backgroundColor;
          const transcriptBg = getComputedStyle(transcript).backgroundColor;
          return mainBg !== 'rgb(15, 23, 34)'
            && railBg !== 'rgb(10, 18, 28)'
            && transcriptBg !== 'rgb(17, 26, 37)';
        }
        """,
        timeout=20_000,
    )


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
    await hold(1.0)


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
        await page.locator("#system-status").wait_for(state="attached")

        # 1) Product overview and service-intro behavior.
        await wait_for_d_home(page)
        await page.screenshot(path=str(OUTPUT_DIR / "careflow-d-home.png"), full_page=False)
        await page.locator('[data-intro="features"]').click()
        await page.locator("#service-intro-section").wait_for(state="visible")
        await hold(3)

        # 2) Entering consultation must not create or prefill a session.
        await page.locator("#guided-demo").click()
        await wait_for_light_workspace(page)
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('0 utterances')",
            timeout=20_000,
        )
        await page.locator("#workspace-new-session").wait_for(state="visible")
        await hold(4)

        # 3) Explicit demo action creates the session; finalize separately.
        await page.locator("[data-scenario='normal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('4 utterances')",
            timeout=20_000,
        )
        await page.locator("#finalize").click()
        await wait_for_draft(page)
        await page.wait_for_function(
            "document.getElementById('home-coverage')?.textContent?.trim() === '3/3'",
            timeout=20_000,
        )
        await hold(7)

        # 4) Safety signal must go to human review.
        await page.locator("[data-scenario='safety_signal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('3 utterances')",
            timeout=20_000,
        )
        await page.locator("#finalize").click()
        await wait_for_draft(page)
        await hold(7)

        # 5) Review queue.
        await switch_view(page, "queue")
        await hold(5)

        # 6) Validation view: decisions and evidence, not a technology laundry list.
        await switch_view(page, "quality")
        await page.locator("#quality-grid").wait_for(state="visible")
        await page.get_by_text("검증 결과", exact=True).first.wait_for(state="visible")
        await page.get_by_text("검색 품질 비교", exact=True).wait_for(state="visible")
        await hold(6)

        # 7) System state.
        await switch_view(page, "operations")
        await wait_for_operations(page)
        await hold(6)

        # Close on the D overview.
        await switch_view(page, "overview")
        await wait_for_d_home(page)
        await hold(4)

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
