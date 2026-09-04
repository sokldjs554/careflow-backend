from __future__ import annotations

import json
from pathlib import Path

import httpx
from dotenv import dotenv_values

from app.config import Settings


def _load_key() -> tuple[str, str]:
    env_path = Path(".env")
    if env_path.exists():
        value = str(dotenv_values(env_path).get("ANTHROPIC_API_KEY") or "").strip()
        if value:
            return value, ".env"

    settings = Settings()
    if settings.anthropic_api_key is not None:
        value = settings.anthropic_api_key.get_secret_value().strip()
        if value:
            return value, "environment"
    return "", "missing"


def main() -> None:
    settings = Settings()
    api_key, source = _load_key()
    if not api_key:
        print(json.dumps({"status": "missing", "key_source": source}, ensure_ascii=False))
        raise SystemExit(1)

    url = f"{settings.anthropic_base_url.rstrip('/')}/v1/models"
    response = httpx.get(
        url,
        params={"limit": 1},
        headers={
            "x-api-key": api_key,
            "anthropic-version": settings.anthropic_version,
            "accept": "application/json",
        },
        timeout=20,
    )

    result: dict[str, object] = {
        "status": "ok" if response.is_success else "failed",
        "key_source": source,
        "key_length": len(api_key),
        "http_status": response.status_code,
        "request_id": response.headers.get("request-id")
        or response.headers.get("x-request-id"),
    }
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            result["api_error_type"] = error.get("type")
            result["api_error_message"] = error.get("message")
        if response.is_success:
            data = payload.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                result["sample_model"] = data[0].get("id")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not response.is_success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
