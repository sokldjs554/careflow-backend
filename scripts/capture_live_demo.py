from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE_URL = "https://careflow-demo.onrender.com"
OUTPUT_DIR = Path("artifacts/demo")


async def hold(seconds: float) -> None:
    await asyncio.sleep(seconds)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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
    require(asset_loaded, "D hero room visual did not decode in the browser")


async def wait_for_live_release(page: Page) -> None:
    """Allow Render auto-deploy to converge before the browser contract is evaluated."""
    last_error: Exception | None = None
    for attempt in range(12):
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
            await page.locator("#system-status").wait_for(state="attached")
            await wait_for_d_home(page)
            await page.locator("#service-intro-section").wait_for(state="attached")
            return
        except Exception as exc:  # noqa: BLE001 - release convergence retry
            last_error = exc
            if attempt == 11:
                break
            await hold(10)
    raise RuntimeError(f"Live Render release did not converge: {last_error}")


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


async def wait_for_operations(page: Page) -> tuple[str, str]:
    await page.locator("#view-operations").wait_for(state="visible")
    await page.wait_for_function(
        """
        () => {
          const db = document.getElementById('op-db')?.textContent?.trim();
          const store = document.getElementById('op-store')?.textContent?.trim();
          const dbHealth = document.getElementById('op-db-health')?.textContent?.trim();
          const storeHealth = document.getElementById('op-store-health')?.textContent?.trim();
          return Boolean(
            db && db !== '-' && store && store !== '-'
            && dbHealth === 'healthy' && storeHealth === 'healthy'
          );
        }
        """,
        timeout=20_000,
    )
    return (
        (await page.locator("#op-db").inner_text()).strip(),
        (await page.locator("#op-store").inner_text()).strip(),
    )


async def switch_view(page: Page, view: str) -> None:
    await page.locator(f"[data-view='{view}']").click()
    await hold(1.0)


async def capture() -> None:
    await asyncio.to_thread(OUTPUT_DIR.mkdir, parents=True, exist_ok=True)
    raw_dir = OUTPUT_DIR / "raw"
    await asyncio.to_thread(raw_dir.mkdir, parents=True, exist_ok=True)

    verification: dict[str, object] = {
        "base_url": BASE_URL,
        "checked_at": datetime.now(UTC).isoformat(),
    }

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(raw_dir),
            record_video_size={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        session_posts: list[str] = []

        def track_session_post(request: object) -> None:
            method = getattr(request, "method", "")
            url = getattr(request, "url", "")
            if method == "POST" and str(url).rstrip("/").endswith("/v1/sessions"):
                session_posts.append(str(url))

        page.on("request", track_session_post)
        await wait_for_live_release(page)

        # 1) Product overview and service-intro behavior.
        await page.screenshot(path=str(OUTPUT_DIR / "careflow-d-home.png"), full_page=False)
        posts_before_intro = len(session_posts)
        await page.locator('[data-intro="features"]').click()
        await page.locator("#service-intro-section").wait_for(state="visible")
        await page.wait_for_function(
            """
            () => {
              const node = document.getElementById('service-intro-section');
              if (!node) return false;
              const box = node.getBoundingClientRect();
              return document.body.dataset.view === 'overview'
                && box.top >= -4 && box.top < window.innerHeight * 0.92;
            }
            """,
            timeout=10_000,
        )
        require(
            len(session_posts) == posts_before_intro,
            "Service intro unexpectedly created a consultation session",
        )
        verification["service_intro_stays_on_home"] = True
        verification["service_intro_creates_session"] = False
        await hold(3)

        # 2) Entering consultation must not create or prefill a session.
        posts_before_entry = len(session_posts)
        await page.locator("#guided-demo").click()
        await wait_for_light_workspace(page)
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('0 utterances')",
            timeout=20_000,
        )
        await page.locator("#workspace-new-session").wait_for(state="visible")
        require(
            len(session_posts) == posts_before_entry,
            "Opening the consultation workspace unexpectedly created a session",
        )
        require(
            (await page.locator("#draft-status").inner_text()).strip() == "미생성",
            "Consultation workspace was prefilled with a draft",
        )
        verification["consultation_workspace_is_light"] = True
        verification["consultation_entry_creates_session"] = False
        verification["consultation_entry_prefills_transcript"] = False
        await hold(4)

        # 3) Explicit demo action creates exactly one session; normal completion purges raw text.
        posts_before_normal = len(session_posts)
        await page.locator("[data-scenario='normal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('4 utterances')",
            timeout=20_000,
        )
        require(
            len(session_posts) == posts_before_normal + 1,
            "Normal demo did not create exactly one explicit session",
        )
        await page.locator("#finalize").click()
        await wait_for_draft(page)
        await page.wait_for_function(
            "document.getElementById('home-coverage')?.textContent?.trim() === '3/3'",
            timeout=20_000,
        )
        await page.wait_for_function(
            "document.getElementById('signal-transcript')?.textContent?.trim() === '삭제 완료'",
            timeout=20_000,
        )
        verification["normal_flow_explicit_session_count"] = 1
        verification["normal_flow_evidence_sections"] = "3/3"
        verification["normal_flow_transcript_purged"] = True
        await hold(7)

        # 4) Safety signal must route to human review and keep the transcript until approval.
        posts_before_safety = len(session_posts)
        await page.locator("[data-scenario='safety_signal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('3 utterances')",
            timeout=20_000,
        )
        require(
            len(session_posts) == posts_before_safety + 1,
            "Safety demo did not create exactly one explicit session",
        )
        await page.locator("#finalize").click()
        await wait_for_draft(page)
        await page.wait_for_function(
            "document.getElementById('signal-review')?.textContent?.trim() === '검토 필요'",
            timeout=20_000,
        )
        await page.wait_for_function(
            "document.getElementById('signal-transcript')?.textContent?.trim() === 'TTL 보존'",
            timeout=20_000,
        )
        require(
            await page.locator("#review-alert").is_visible(),
            "Safety review banner is not visible",
        )
        require(
            await page.locator("#approve-review").is_enabled(),
            "Safety review cannot be explicitly approved",
        )
        verification["safety_flow_routes_to_review"] = True
        verification["safety_flow_transcript_retained_until_approval"] = True
        await hold(7)

        # 5) Review queue must surface the review-required session.
        await switch_view(page, "queue")
        await page.wait_for_function(
            "document.querySelectorAll('#queue-list .queue-card').length > 0",
            timeout=20_000,
        )
        verification["review_queue_surfaces_pending_session"] = True
        await hold(5)

        # 6) Validation view: decisions and evidence, not a technology laundry list.
        await switch_view(page, "quality")
        await page.locator("#quality-grid").wait_for(state="visible")
        await page.get_by_text("검증 결과", exact=True).first.wait_for(state="visible")
        await page.get_by_text("검색 품질 비교", exact=True).wait_for(state="visible")
        quality_text = await page.locator("#view-quality").inner_text()
        forbidden_stack_labels = (
            "FastAPI",
            "PostgreSQL",
            "Redis",
            "WebSocket",
            "Qdrant",
            "LangGraph",
            "PyTorch",
        )
        leaked = [label for label in forbidden_stack_labels if label in quality_text]
        require(not leaked, f"Quality view still reads like a stack list: {leaked}")
        verification["quality_view_is_decision_focused"] = True
        verification["quality_view_stack_labels"] = []
        await hold(6)

        # 7) System state must prove live data layers are healthy without exposing credentials.
        await switch_view(page, "operations")
        database_backend, transcript_store_backend = await wait_for_operations(page)
        require(database_backend == "POSTGRESQL", "Live demo is not using PostgreSQL")
        require(transcript_store_backend == "REDIS", "Live demo is not using Redis")
        operations_text = await page.locator("#view-operations").inner_text()
        require(
            "postgresql://" not in operations_text.lower(),
            "Database credential URL leaked in UI",
        )
        require(
            "redis://" not in operations_text.lower(),
            "Redis credential URL leaked in UI",
        )
        verification["database_backend"] = database_backend
        verification["transcript_store_backend"] = transcript_store_backend
        verification["runtime_data_layers_healthy"] = True
        verification["credentials_exposed"] = False
        await hold(6)

        # Close on the D overview.
        await switch_view(page, "overview")
        await wait_for_d_home(page)
        verification["d_home_rendered"] = True
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
    verification["verified"] = True
    await asyncio.to_thread(
        (OUTPUT_DIR / "careflow-live-verification.json").write_text,
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(capture())
