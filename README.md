# Минимальный шаблон

Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Alembic, Jinja2, локальные CSS/JS/HTMX. Backend и frontend работают в одном app; остальные сервисы: db, mini-fsp-id, mailpit. Предметные пакеты пока пусты.

## Запуск

На хосте нужен только Docker с Compose v2 и поддержкой Linux-контейнеров. Из этой папки:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build
```

Linux/macOS: `cp .env.example .env`. Не перезаписывайте уже настроенный .env. Пример содержит только локальные тестовые параметры. Для пароля в DATABASE_URL используйте URL-безопасные символы либо задайте DATABASE_URL с URL-кодированным паролем в Compose.

- Страница: http://localhost:8000/
- Swagger приложения: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- PostgreSQL readiness (SELECT 1, при отказе 503): http://localhost:8000/readiness
- Swagger мока: http://localhost:8001/docs
- Почта Mailpit: http://localhost:8025/; SMTP внутри сети: mailpit:1025.

Compose ждёт healthcheck БД; app дополнительно проверяет соединение, выполняет `alembic upgrade head` и только затем запускает Uvicorn. Начальная миграция создаёт историю alembic_version без предметных таблиц. Данные PostgreSQL сохраняются в именованном volume. Исходники app/migrations/mock_fsp подключены volumes; reload включён автоматически через compose.override.yaml. Зависимости в контейнере находятся в /opt/venv. Для запуска без dev override: `docker compose -f compose.yaml up --build`.

`docker compose down` останавливает сервисы и сохраняет БД. `docker compose down -v` удаляет данные БД.

## Мок и интеграции

GET /participants — тестовые профили; GET /participants/demo-1 — профиль; GET /participants/demo-1/achievements — достижения. demo-2 имеет пустой список достижений, неизвестный id возвращает 404. Данные читаются из mock_fsp/data/*.json. Это локальный контракт, не официальный API ФСП ID.

IdentityProvider и AchievementRegistry — интерфейсы; HTTPX-клиенты принимают AsyncClient с base_url и timeout. Обработку авторизации реального провайдера следует добавить позже.

Будущий вход: Keycloak как OIDC-провайдер, Authlib для authorization code flow, discovery, проверки state/nonce и токенов; конфигурация issuer/client_id/client_secret через окружение, пользовательские сессии и права в модуле auth. Keycloak, Authlib и полноценная авторизация сейчас не подключены.

## Проверки

Тестовые зависимости не входят в runtime-образ. Для тестов на хосте нужны uv и Python (uv может загрузить Python):

```powershell
uv sync --locked --python 3.12
uv run --locked pytest tests/backend -q
uv run --locked playwright install chromium
$env:RUN_E2E="1"
uv run pytest tests/e2e -q
```

Проверки реальной БД и миграции через сеть Compose без установки Python на хост:

```powershell
docker compose exec app uv run --locked --group dev python -c "from sqlalchemy import text; from app.db.session import engine; c=engine.connect(); print(c.execute(text('SELECT 1')).scalar_one()); print(c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()); c.close()"
docker compose exec app alembic current
```

Полный integration-прогон внутри app:

```powershell
docker compose exec -e RUN_INTEGRATION=1 -e APP_BASE_URL=http://localhost:8000 -e FSP_BASE_URL=http://mini-fsp-id:8000 app uv run --locked --group dev pytest tests/integration -q
```

Для integration-тестов на хосте БД должна быть доступна по DATABASE_URL; Compose по умолчанию не публикует её порт. Можно выполнять тесты внутри app, указав APP_BASE_URL/FSP_BASE_URL для сервисных проверок (см. tests/integration).

.env, секреты, окружения, кэш, логи и результаты тестов исключены из Git и Docker build context. uv.lock включён в проект; после изменения зависимостей выполните uv lock и пересоберите образ. Git remote, коммиты и push не настроены.

HTMX 2.0.11 хранится локально; источник: https://htmx.org/docs/ и https://cdn.jsdelivr.net/npm/htmx.org@2.0.11/dist/htmx.min.js (Zero-Clause BSD).
Справка по установке зависимостей в образ: https://docs.astral.sh/uv/guides/integration/docker/.

## Локальная разработка в этом окружении

Python, uv, кэш и браузеры находятся на E:/codex-tools; .venv — в проекте.
uv.exe добавлен в пользовательский PATH (доступен в новом терминале).
Браузерный тест самостоятельно запускает временный Uvicorn на свободном порту и останавливает его после проверки.
БД для него не нужна. Для проверки внешнего сервера задайте APP_BASE_URL.
Backend smoke дополнительно проверяет HTTPX-клиенты через ASGI мок.
Проверка lock-файла: uv lock --check. Генерация SQL без БД: uv run --locked alembic upgrade head --sql.

## Проверки Docker после перезагрузки

Проверено 2026-10-07: Docker Engine и Compose доступны, конфигурация корректна,
`docker compose up --build -d` успешно собирает и запускает все четыре сервиса.
Существующий `.env` сохранён. `app`, `db` и `mailpit` healthy; мок отвечает на HTTP-запросы.
После запуска Docker Desktop повторить проверки можно так:

```powershell
docker compose up --build -d --wait
uv run --locked pytest tests/backend -q
docker compose exec app alembic current
docker compose exec -e RUN_INTEGRATION=1 -e APP_BASE_URL=http://localhost:8000 -e FSP_BASE_URL=http://mini-fsp-id:8000 app uv run --locked --group dev pytest tests/integration -q
$env:RUN_E2E="1"
$env:APP_BASE_URL="http://localhost:8000"
uv run --locked pytest tests/e2e -q
```

Integration-тесты проверяют SELECT 1, соответствие миграций heads Alembic, оба Swagger/OpenAPI, readiness, API мока и Mailpit.
Тестовые зависимости не входят в runtime-образ; uv run в контейнере устанавливает их только для проверки.
.env в этом окружении уже подготовлен, копировать поверх него не нужно.
Лицензия HTMX находится в app/static/vendor/HTMX-LICENSE.txt.

## Результаты проверок после перезагрузки

Backend: 4 passed; integration на сервисах Compose: 4 passed; Playwright на запущенном приложении: 2 passed.
Проверены страница, локальные CSS/JS/HTMX, работа JavaScript и HTMX, Swagger в браузере,
оба OpenAPI, health/readiness, профили и достижения мока, UI и API Mailpit.
SQLAlchemy подключился к настоящему PostgreSQL и выполнил SELECT 1.
Alembic current/heads/history показывают единственную ревизию 0001_initial, применённую до head.
Повторные upgrade head завершились успешно; схема и строка alembic_version (включая xmin) не изменились.
После restart app автоматические миграции и Uvicorn запустились успешно, readiness вернулся к 200.
uv lock --check выполнен успешно. В рабочем журнале сервисов ошибок нет;
при первичной инициализации postgres:17-alpine есть предупреждение об отсутствии системных локалей
и сообщение о завершении временного сервера инициализации. Основной PostgreSQL работает успешно.
Есть предупреждение зависимости Starlette о будущем переходе TestClient с HTTPX; тесты проходят.
Заблокированных или невыполненных проверок из этого прогона нет. Volumes и данные не удалялись,
секреты не перезаписывались, downgrade, commit и push не выполнялись.
