from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Page, async_playwright

BASE_URL = os.environ.get("BASE_URL", "https://careflow-demo.onrender.com").rstrip("/")
EXPECTED_DATABASE_BACKEND = os.environ.get("EXPECTED_DATABASE_BACKEND", "sqlite").upper()
EXPECTED_TRANSCRIPT_STORE_BACKEND = os.environ.get(
    "EXPECTED_TRANSCRIPT_STORE_BACKEND", "memory"
).upper()
EXPECTED_ENVIRONMENT = os.environ.get("EXPECTED_ENVIRONMENT", "render-demo")
OUTPUT_DIR = Path("artifacts/demo")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def hold(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def switch_view(page: Page, view: str) -> None:
    await page.locator(f"[data-view='{view}']").click()
    await page.wait_for_function(f"document.body.dataset.view === '{view}'", timeout=20_000)
    await hold(0.8)


async def wait_for_d_home(page: Page) -> dict[str, object]:
    """Assert the selected D home and its sharp hero asset are painted by Chromium."""
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
          const visualStyle = getComputedStyle(heroVisual);
          const overlay = getComputedStyle(heroVisual, '::after').content || '';
          const railLabel = getComputedStyle(rail, '::after').content || '';
          const navLabels = [...document.querySelectorAll('.nav button')].map(
            (node) => getComputedStyle(node, '::after').content || ''
          );
          return title.includes('오늘도')
            && title.includes('누군가의 마음이 조금 더 가벼워집니다.')
            && titleStyle.fontSize === '32px'
            && copy.includes('의료진의 소중한 시간을 지켜주고')
            && copy.includes('더 깊은 대화에 집중할 수 있도록')
            && getComputedStyle(rail).display === 'flex'
            && getComputedStyle(topbar).display === 'none'
            && (visualStyle.backgroundImage || '').includes('images.unsplash.com')
            && overlay.includes('Listen')
            && overlay.includes('Understand')
            && overlay.includes('Care')
            && overlay.includes('Together')
            && railLabel.includes('데모 환경')
            && !railLabel.includes('김의사')
            && ['홈', '상담 기록', '검토 대기', '분석'].every(
              (label) => navLabels.some((value) => value.includes(label))
            );
        }
        """,
        timeout=20_000,
    )
    asset = await page.evaluate(
        """
        async () => {
          const heroVisual = document.querySelector('.hero-flow');
          if (!heroVisual) return {ok:false,width:0,height:0,src:''};
          const background = getComputedStyle(heroVisual).backgroundImage || '';
          const match = background.match(/^url\\(["']?(.*?)["']?\\)$/);
          if (!match) return {ok:false,width:0,height:0,src:''};
          const image = new Image();
          return await new Promise((resolve) => {
            image.onload = () => resolve({
              ok:image.naturalWidth >= 1200 && image.naturalHeight > 0,
              width:image.naturalWidth,
              height:image.naturalHeight,
              src:match[1]
            });
            image.onerror = () => resolve({ok:false,width:0,height:0,src:match[1]});
            image.src = match[1];
          });
        }
        """
    )
    require(bool(asset.get("ok")), "D hero visual did not decode at high resolution")
    return asset


async def wait_for_service_intro(page: Page) -> None:
    """Verify that '서비스 소개 보기' opens a real product story section."""
    await page.wait_for_function(
        """
        () => {
          if (document.body.dataset.view !== 'overview') return false;
          const section = document.getElementById('service-intro-section');
          const heading = section?.querySelector('h2');
          const copy = section?.querySelector('p');
          const grid = section?.nextElementSibling;
          if (!section || !heading || !copy || !grid?.classList.contains('feature-grid')) return false;

          const headingText = getComputedStyle(heading, '::after').content || '';
          const bodyText = getComputedStyle(copy, '::after').content || '';
          const cards = [...grid.querySelectorAll('.feature-card')];
          const cardTitles = cards.map((card) => {
            const title = card.querySelector('h3');
            return title ? (getComputedStyle(title, '::after').content || '') : '';
          });
          const gridLead = getComputedStyle(grid, '::before').content || '';
          const preview = getComputedStyle(grid, '::after').content || '';
          const rect = section.getBoundingClientRect();

          return getComputedStyle(section).display === 'block'
            && getComputedStyle(copy).display === 'block'
            && headingText.includes('상담에 집중하세요')
            && headingText.includes('CareFlow가 연결합니다')
            && bodyText.includes('대화의 흐름을 끊지 않도록')
            && bodyText.includes('의료진의 검토로 넘깁니다')
            && gridLead.includes('상담 시작부터 검토·삭제까지')
            && preview.includes('원문 발화')
            && preview.includes('S/O/P 기록 초안')
            && ['상담을 시작합니다', '대화를 흐름대로 기록합니다', '기록과 원문을 연결합니다', '확인이 필요하면 사람이 검토합니다'].every(
              (label) => cardTitles.some((value) => value.includes(label))
            )
            && rect.top < window.innerHeight
            && rect.bottom > 0;
        }
        """,
        timeout=20_000,
    )


async def wait_for_light_workspace(page: Page) -> None:
    await page.wait_for_function(
        """
        () => {
          if (document.body.dataset.view !== 'console') return false;
          const main = document.querySelector('.main');
          const rail = document.querySelector('.rail');
          const transcript = document.querySelector('.transcript');
          if (!main || !rail || !transcript) return false;
          return getComputedStyle(main).backgroundColor !== 'rgb(15, 23, 34)'
            && getComputedStyle(rail).backgroundColor !== 'rgb(10, 18, 28)'
            && getComputedStyle(transcript).backgroundColor !== 'rgb(17, 26, 37)';
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


async def wait_for_operations(page: Page) -> tuple[str, str, str]:
    await page.locator("#view-operations").wait_for(state="visible")
    await page.wait_for_function(
        """
        () => {
          const db = document.getElementById('op-db')?.textContent?.trim();
          const store = document.getElementById('op-store')?.textContent?.trim();
          const dbHealth = document.getElementById('op-db-health')?.textContent?.trim();
          const storeHealth = document.getElementById('op-store-health')?.textContent?.trim();
          const env = document.getElementById('op-environment')?.textContent?.trim();
          return Boolean(db && db !== '-' && store && store !== '-'
            && dbHealth === 'healthy' && storeHealth === 'healthy'
            && env && env.startsWith('environment:'));
        }
        """,
        timeout=20_000,
    )
    return (
        (await page.locator("#op-db").inner_text()).strip(),
        (await page.locator("#op-store").inner_text()).strip(),
        (await page.locator("#op-environment").inner_text()).strip(),
    )


async def capture() -> None:
    await asyncio.to_thread(OUTPUT_DIR.mkdir, parents=True, exist_ok=True)
    raw_dir = OUTPUT_DIR / "raw"
    await asyncio.to_thread(raw_dir.mkdir, parents=True, exist_ok=True)
    verification: dict[str, object] = {
        "base_url": BASE_URL,
        "checked_at": datetime.now(UTC).isoformat(),
        "expected_database_backend": EXPECTED_DATABASE_BACKEND,
        "expected_transcript_store_backend": EXPECTED_TRANSCRIPT_STORE_BACKEND,
        "expected_environment": EXPECTED_ENVIRONMENT,
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
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60_000)
        await page.locator("#system-status").wait_for(state="attached")
        hero_asset = await wait_for_d_home(page)
        await page.screenshot(path=str(OUTPUT_DIR / "careflow-d-home.png"), full_page=False)
        verification["d_home_rendered"] = True
        verification["hero_asset_decoded"] = True
        verification["hero_asset_width"] = hero_asset["width"]
        verification["hero_asset_height"] = hero_asset["height"]
        verification["hero_asset_is_high_resolution"] = int(hero_asset["width"]) >= 1200
        verification["hero_identity_is_neutral_demo_label"] = True

        # Home intro stays on Home, creates no data, and explains the product in depth.
        posts_before_intro = len(session_posts)
        await page.locator('[data-intro="features"]').click()
        await wait_for_service_intro(page)
        require(len(session_posts) == posts_before_intro, "Service intro created a session")
        await page.screenshot(
            path=str(OUTPUT_DIR / "careflow-service-intro.png"), full_page=False
        )
        verification["service_intro_stays_on_home"] = True
        verification["service_intro_creates_session"] = False
        verification["service_intro_has_problem_value_copy"] = True
        verification["service_intro_has_four_step_workflow"] = True
        verification["service_intro_has_product_preview_copy"] = True
        await hold(4)

        # Opening the consultation workspace must still be an empty state.
        posts_before_entry = len(session_posts)
        await page.locator("#guided-demo").click()
        await wait_for_light_workspace(page)
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('0 utterances')",
            timeout=20_000,
        )
        require(len(session_posts) == posts_before_entry, "Workspace entry created a session")
        require(
            (await page.locator("#draft-status").inner_text()).strip() == "미생성",
            "Workspace entry prefilled a draft",
        )
        verification["consultation_entry_creates_session"] = False
        verification["consultation_entry_prefills_transcript"] = False
        await hold(3)

        # Explicit normal scenario: exactly one session, 3/3 evidence, raw transcript purged.
        posts_before_normal = len(session_posts)
        await page.locator("[data-scenario='normal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('4 utterances')",
            timeout=20_000,
        )
        require(
            len(session_posts) == posts_before_normal + 1,
            "Normal scenario session count mismatch",
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
        await hold(5)

        # Safety signal: explicit review state and retained transcript before approval.
        posts_before_safety = len(session_posts)
        await page.locator("[data-scenario='safety_signal']").click()
        await page.wait_for_function(
            "document.getElementById('transcript-count')?.textContent?.includes('3 utterances')",
            timeout=20_000,
        )
        require(
            len(session_posts) == posts_before_safety + 1,
            "Safety scenario session count mismatch",
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
            "Safety review banner missing",
        )
        require(
            await page.locator("#approve-review").is_enabled(),
            "Safety review approval disabled",
        )
        verification["safety_flow_routes_to_review"] = True
        verification["safety_flow_transcript_retained_until_approval"] = True
        await hold(5)

        # Review Queue exposes the pending work.
        await switch_view(page, "queue")
        await page.wait_for_function(
            "document.querySelectorAll('#queue-list .queue-card').length > 0",
            timeout=20_000,
        )
        verification["review_queue_surfaces_pending_session"] = True
        await hold(4)

        # AI validation view must present decisions and the persisted selection path.
        await switch_view(page, "quality")
        await page.locator("#quality-grid").wait_for(state="visible")
        await page.get_by_text("검색 품질 비교", exact=True).wait_for(state="visible")
        quality_text = await page.locator("#view-quality").inner_text()
        selection_tokens = (
            "0.0648",
            "0.1244",
            "0.1093",
            "개선안 · 채택",
            "추가 후보 · 미채택",
        )
        for token in selection_tokens:
            require(token in quality_text, f"Quality selection evidence missing: {token}")
        stack_labels = (
            "FastAPI",
            "PostgreSQL",
            "Redis",
            "WebSocket",
            "Qdrant",
            "LangGraph",
            "PyTorch",
        )
        leaked = [label for label in stack_labels if label in quality_text]
        require(not leaked, f"Quality view reads like a stack list: {leaked}")
        verification["quality_view_is_decision_focused"] = True
        verification["quality_selection_metrics"] = [0.0648, 0.1244, 0.1093]
        await hold(5)

        # Public runtime is SQLite + memory; CI proves PostgreSQL + Redis separately.
        await switch_view(page, "operations")
        (
            database_backend,
            transcript_store_backend,
            environment_text,
        ) = await wait_for_operations(page)
        require(
            database_backend == EXPECTED_DATABASE_BACKEND,
            "Unexpected public database backend: "
            f"{database_backend} != {EXPECTED_DATABASE_BACKEND}",
        )
        require(
            transcript_store_backend == EXPECTED_TRANSCRIPT_STORE_BACKEND,
            "Unexpected public transcript-store backend: "
            f"{transcript_store_backend} != {EXPECTED_TRANSCRIPT_STORE_BACKEND}",
        )
        require(
            environment_text == f"environment: {EXPECTED_ENVIRONMENT}",
            f"Unexpected public environment label: {environment_text}",
        )
        operations_text = await page.locator("#view-operations").inner_text()
        require("postgresql://" not in operations_text.lower(), "Database credential URL leaked")
        require("redis://" not in operations_text.lower(), "Redis credential URL leaked")
        verification["database_backend"] = database_backend
        verification["transcript_store_backend"] = transcript_store_backend
        verification["runtime_data_layers_healthy"] = True
        verification["credentials_exposed"] = False
        await hold(5)

        await switch_view(page, "overview")
        await wait_for_d_home(page)
        await hold(3)

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
