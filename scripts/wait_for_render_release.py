"""Wait until Render serves the exact Git commit that triggered this workflow."""

import json
import os
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "https://careflow-demo.onrender.com").rstrip("/")
EXPECTED_COMMIT = os.environ.get("EXPECTED_GIT_COMMIT", "").strip()
ATTEMPTS = 72
RETRY_SECONDS = 5


def fetch_json(path: str) -> dict[str, object]:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=20) as response:  # noqa: S310
        return json.load(response)


def main() -> None:
    if not EXPECTED_COMMIT:
        raise RuntimeError("EXPECTED_GIT_COMMIT is required")

    last_state = "not checked"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            release = fetch_json("/v1/release")
            served_commit = str(release.get("commit", ""))
            if served_commit != EXPECTED_COMMIT:
                last_state = f"serving {served_commit or 'unknown'}"
            else:
                ready = fetch_json("/health/ready")
                if ready == {"status": "ready"}:
                    print(f"Render is serving expected commit {EXPECTED_COMMIT} and is ready")
                    return
                last_state = f"expected commit served but readiness={ready!r}"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_state = f"endpoint not ready: {exc}"

        if attempt < ATTEMPTS:
            print(f"waiting for Render release ({attempt}/{ATTEMPTS}): {last_state}")
            time.sleep(RETRY_SECONDS)

    raise RuntimeError(
        f"Render did not serve expected commit {EXPECTED_COMMIT}: {last_state}"
    )


if __name__ == "__main__":
    main()
