# Default runtime packaging check

CareFlow의 기본 설정은 `sqlite+aiosqlite:///./careflow.db`를 사용하므로, 일반 배포 환경에서 `pip install .`만 실행해도 SQLite async driver가 반드시 함께 설치되어야 합니다.

이번 검증에서 Render의 첫 기동이 `ModuleNotFoundError: No module named 'aiosqlite'`로 실패하면서 `aiosqlite`가 개발용 extra에만 들어 있던 패키징 결함을 발견했습니다.

수정 원칙:

- `aiosqlite`를 기본 runtime dependency로 둡니다.
- `uv.lock`도 같은 dependency 관계를 반영합니다.
- `tests/test_runtime_packaging.py`가 기본 `DATABASE_URL`과 runtime dependency를 함께 확인합니다.
- PostgreSQL 운영 경로는 `asyncpg`, Redis 경로는 `redis` dependency와 별도로 유지합니다.

이 문서는 Render를 SQLite 운영 아키텍처로 권장한다는 뜻이 아닙니다. 공개 포트폴리오 데모는 비용과 외부 credential 제약 때문에 SQLite + memory transcript store로 실행하며, PostgreSQL 16 + Redis 7 경로는 GitHub Actions integration job에서 별도로 실제 검증합니다.
