# ФСП IT Карьера

Веб-сервис прямого подбора ИТ-специалистов: кандидат подтверждает категорию тестированием, работодатель находит подходящие профили и направляет адресное приглашение с зарплатой. Достижения ФСП дополняют профиль через демонстрационный реестр. Дополнительно доступны вакансии, самостоятельные отклики, чаты, встречи и рейтинг работодателей.

Основная документация: [Documentation.md](Documentation.md). В ней описаны бизнес-правила, формулы, доступ к данным, API, демонстрационный ФСП ID, выполненные проверки и ограничения. Текущая документация соответствует исходникам на 11.10.2026, включая незакоммиченные изменения после `ac8cf7e`. Новый презентационный набор и серверное обновление описаны в [Change_log13.md](Change_log13.md).

## Возможности

- Кандидат: профиль, навыки и опыт, одна фотография, стандартизированное PDF-резюме, тесты и история, публикация и согласия, ФСП-достижения, вакансии и отклики, приглашения, переписка и встречи.
- Работодатель: компания и фотография, вакансии/архив и отклики, «Потребность команды» с несколькими позициями и сохранёнными фильтрами, поиск с объяснениями, приглашения без вакансии, чаты/календарь и лидерборд.
- Активность вакансии и рейтинг компании рассчитываются отдельно. Просмотр резюме не даёт баллов компании; взаимная переписка и встречи учитываются по действующей формуле.
- Реального Keycloak и официального API ФСП пока нет. Импорт PDF, ежедневные задачи и тестовые задания работодателей не реализованы. Подготовлены модели внешней личности и интеграционные интерфейсы.

## Локальный запуск в Docker Compose

Нужны Git, Docker Engine с Compose или Docker Desktop с Linux-контейнерами. Python на хосте для обычного запуска не нужен. Ниже команды PowerShell; в Linux/macOS используйте `cp .env.example .env` вместо `Copy-Item`.

```powershell
git clone https://github.com/projectlnk/fsp-it-talent-match.git
cd fsp-it-talent-match
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

В `.env` задайте локальные параметры. Сгенерируйте секрет подписи, например командой `python -c "import secrets; print(secrets.token_urlsafe(48))"`, если Python установлен, и вставьте результат в `JWT_SECRET_KEY`.

```dotenv
POSTGRES_DB=project
POSTGRES_USER=project
POSTGRES_PASSWORD=local-dev-password
JWT_SECRET_KEY=вставьте-сгенерированный-случайный-секрет
APP_PORT=8000
APP_BASE_URL=http://localhost:8000
FSP_PORT=8001
MAILPIT_PORT=8025
MAILPIT_BIND_HOST=127.0.0.1
MAILPIT_SMTP_PORT=1025
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=noreply@example.com
SMTP_FROM_NAME=ФСП IT Карьера
SMTP_STARTTLS=false
SMTP_SSL=false
```

Значения приведены для локального стенда. `.env` не коммитьте. `DATABASE_URL` и `FSP_BASE_URL` для контейнера app задаются в `compose.yaml` из конфигурации Compose; внутренние адреса — `db:5432` и `mini-fsp-id:8000`.

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail=60 app
```

`app/start.py` ждёт PostgreSQL, выполняет `alembic upgrade head` и загружает банк вопросов, только если он пуст. Миграция справочников создаёт Backend/Frontend, четыре грейда и восемь категорий. Пользователи автоматически не создаются. Текущий migration head — `c25e_needs`.

| Сервис | Адрес на компьютере |
| --- | --- |
| Сайт | http://localhost:8000 |
| Health / readiness | http://localhost:8000/health / http://localhost:8000/readiness |
| Swagger / ReDoc / OpenAPI | http://localhost:8000/docs / http://localhost:8000/redoc / http://localhost:8000/openapi.json |
| ФСП-мок / Swagger | http://localhost:8001/participants / http://localhost:8001/docs |
| Mailpit — письма | http://localhost:8025 |
| Mailpit — SMTP с хоста | localhost:1025 |

При изменении `APP_PORT` обновите `APP_BASE_URL`: именно он используется в ссылке подтверждения email. После входа `/` открывает профиль текущей роли; логотип ведёт на публичную главную `/?public=1`.

### Как открыть Mailpit вне Docker

**Из браузера на этом компьютере:** откройте `http://localhost:8025`. Порт контейнера 8025 опубликован на хосте; внутреннее имя `mailpit` в браузер вводить не нужно. Для другого порта задайте `MAILPIT_PORT=8026`.

**С другого компьютера в локальной сети:** в `.env` задайте `MAILPIT_BIND_HOST=0.0.0.0`, затем:

```powershell
docker compose up -d mailpit
```

Откройте `http://<адрес-компьютера-в-локальной-сети>:8025`. Это интерфейс тестового почтового стенда без настроенной авторизации: используйте его в доверенной сети. Если порт блокирует локальный firewall, проверьте доступ для выбранной сети. В данной задаче firewall не изменяется. Для открытия самого приложения с другого компьютера одного `APP_BASE_URL` недостаточно: bind приложения в `compose.yaml` остаётся `127.0.0.1`.

**Если Python-приложение работает на хосте:** задайте `SMTP_HOST=localhost` и `SMTP_PORT` равным `MAILPIT_SMTP_PORT`. В Docker сохраняйте `SMTP_HOST=mailpit` и `SMTP_PORT=1025`. Изменение внешнего порта не меняет внутренний SMTP-порт контейнера. SMTP с хоста опубликован только на loopback.

### Подготовка пользователей и подтверждение почты

Зарегистрируйте кандидата и работодателя на `/auth/register`. Пароль — 8–128 символов; согласие на обработку обязательно. Откройте Mailpit, выберите письмо для тестового адреса и перейдите по ссылке подтверждения. Mailpit сохраняет письма локально и не доставляет их реальным адресатам. При ошибке отправки используйте `/auth/check-email` для повторной попытки.

Для повторяемой локальной демонстрации можно явно запустить имеющийся seed:

```powershell
docker compose exec -T app python -m app.scripts.seed_employer_workspace --password LocalDemo2026Only
```

Это пример пароля только для создаваемых локальных тестовых пользователей. Скрипт создаёт `workspace-hr-a@example.invalid`, `workspace-hr-b@example.invalid` и кандидатов `workspace-candidate-1@example.invalid` … `workspace-candidate-6@example.invalid`, а также синтетические взаимодействия. Повторный запуск при наличии первого работодателя ничего не меняет и не обновляет пароль. Скрипт разрешён только при локальном `APP_BASE_URL`; не используйте его на production. Отдельного seed новых шаблонов потребностей нет: создайте их через интерфейс.

В профиле кандидата на вкладке ФСП доступны тестовые ID `demo-1`, `demo-2`, `demo-3`; у `demo-2` нет достижений. Ввод такого ID не доказывает владение реальной учётной записью ФСП.

## Изменения, обновление и данные

`compose.override.yaml` подключает исходники app, migrations и tests и включает reload. Изменения Python/шаблонов/статики доступны локальному контейнеру; при изменении зависимостей или Dockerfile нужна пересборка. Новые миграции применяются при запуске app; в уже работающем контейнере выполните:

```powershell
docker compose exec -T app alembic upgrade head
docker compose exec -T app alembic current
```

Перед изменением схемы сохраните резервную копию своей БД. Не переписывайте применённые миграции. Для остановки без удаления данных — `docker compose stop`, для продолжения — `docker compose start`. `docker compose up --build -d` обновляет контейнеры, сохраняя PostgreSQL volume. Команда `docker compose down -v` удаляет данные; для обычного обновления она не нужна.

Письма Mailpit не имеют отдельного постоянного тома в основном Compose и могут исчезнуть после пересоздания контейнера. PostgreSQL хранится в `postgres_data`. Мок использует SQLite; подробности сохранности при разных режимах — в Documentation.md.

За HTTPS reverse proxy необходимо настроить внешний `APP_BASE_URL`, реальный SMTP и собственные секреты, исключить dev override и сохранить постоянный том БД. Nginx и сертификаты в проекте автоматически не настраиваются. Локальные настройки отличаются от серверных; production-конфигурация сохраняется при обновлении. Результат последнего обновления — в Change_log13.md.

## Структура проекта

```text
app/
  main.py, start.py        HTTP-приложение; ожидание БД, миграции, запуск
  api/, web/              сборка JSON API и HTML-маршрутов, фотографии
  core/                   настройки, отправка email
  db/                     SQLAlchemy Base, сессии, агрегатор моделей
  modules/auth/           аккаунты, JWT, подтверждение email
  modules/candidates/     профиль, ФСП, приглашения, PDF
  modules/employers/      компания, создание и состояния приглашений
  modules/assessments/    банк вопросов, попытки, категории, ограничения
  modules/matching/       фильтры, выдача, объяснения, шаблоны потребностей
  modules/career/         вакансии, отклики, сообщения, встречи, активность, demo
  integrations/fsp/       клиенты профиля и реестра достижений
  templates/, static/    Jinja2, CSS, JavaScript, HTMX, шрифты, изображения
  scripts/                явные локальные фикстуры и обработка событий
mock_fsp/                 FastAPI-мок; JSON-исходники и SQLite-хранилище
migrations/versions/      добавочные миграции Alembic
tests/                   backend, matching, integration, e2e
docs/api/                экспорт OpenAPI приложения и мока
Documentation.md          основная сопроводительная документация
compose*.yaml             обычный, dev, изолированный test и demo запуск
pyproject.toml, uv.lock   диапазоны и точные версии Python-зависимостей
```

## Языки, библиотеки и ПО

Python — backend; HTML/Jinja2, CSS и JavaScript — интерфейс; SQL — PostgreSQL и миграции. Отдельного Node/React-сборщика нет. Лицензия кода — [MIT](LICENSE); шрифты и брендовые материалы имеют собственные условия использования.

Версии ниже проверены 11.10.2026. Теги Docker с незакреплённым patch могут дать другую версию при следующей сборке. Диапазоны зависимостей задаёт `pyproject.toml`, точные разрешённые версии — `uv.lock`; `uv sync --locked` сохраняет этот набор.

| Компонент | Зафиксированная / проверенная версия | Назначение |
| --- | --- | --- |
| Python | образ `3.12-slim`, локальный контейнер 3.12.15; проект >=3.12,<3.15 | Backend |
| FastAPI / Uvicorn | 0.142.2 / 0.54.0 | HTTP/API и ASGI |
| Pydantic / pydantic-settings | 2.13.5 / 2.15.0 | Схемы и настройки |
| SQLAlchemy / psycopg | 2.1.3 / 3.3.6 | ORM и PostgreSQL |
| Alembic | 1.20.0 | Миграции |
| Jinja2 / HTMX | 3.1.6 / vendor 2.0.11 | HTML и частичное обновление |
| HTTPX | 0.28.1 | Клиент ФСП |
| bcrypt / PyJWT | 4.3.0 / 2.15.1 | Пароли и токены |
| python-multipart / email-validator | 0.0.32 / 2.3.0 | Формы и email |
| WeasyPrint / Pillow | 65.1 / 12.3.0 | PDF и фотографии |
| pytest / pytest-playwright / Playwright / PyYAML | 9.1.1 / 0.9.0 / 1.63.0 / 6.0.3 | Проверки, Chromium и конфигурация |
| PostgreSQL | тег `17-alpine`, проверено 17.11 | Данные приложения |
| Mailpit | тег `v1.27`, проверено 1.27.11 | Тестовая почта |
| uv | Dockerfile 0.12.23 | Установка lock-зависимостей |
| Docker Engine / Compose | проверено 29.8.2 / v5.5.1 | Локальная контейнеризация |
| Pango, Cairo, GdkPixbuf, DejaVu | системные пакеты из образа, patch не закреплён | Рендеринг PDF с кириллицей |

## Целевые проверки

Для разработки на хосте установите uv и выполните `uv sync --locked`. Для браузерных тестов — `uv run playwright install chromium`. Основное приложение по этим командам не требуется переустанавливать.

```powershell
uv run pytest tests/backend/test_assessment_structure.py tests/backend/test_scoring.py tests/backend/test_matching_ranking.py -q
```

Matching-проверки PostgreSQL создают и удаляют только собственные временные базы. Запустите отдельный тестовый db, получите его динамический порт, затем укажите строго `fsp_matching_test`:

```powershell
docker compose -f compose.test.yaml -p fsp-matching-check-jury up -d db
$testDbPort = (docker compose -f compose.test.yaml -p fsp-matching-check-jury port db 5432).Split(':')[-1]
$env:MATCHING_TEST_DATABASE_URL = "postgresql+psycopg://fsp_test:fsp_test_only@127.0.0.1:$testDbPort/fsp_matching_test"
uv run pytest tests/matching/test_team_needs.py -q
```

Не подставляйте URL рабочей или production-БД. Подробная матрица существующих тестов и результаты ограниченного запуска — в [Documentation.md](Documentation.md#11-проверки-приложения-и-качество-решения).

## Типичные проблемы

| Симптом | Проверка / исправление |
| --- | --- |
| Сайт не отвечает | `docker compose ps`, `docker compose logs --tail=60 app`; проверьте свободный APP_PORT |
| Письмо не видно | откройте Mailpit, проверьте SMTP_HOST/SMTP_PORT, повторите отправку на `/auth/check-email` |
| Ссылка письма ведёт не туда | задайте APP_BASE_URL для браузера, пересоздайте app, запросите новое письмо |
| Mailpit не открывается с другого компьютера | MAILPIT_BIND_HOST, порт хоста и локальная сеть/firewall; `mailpit:8025` — внутренний адрес |
| `relation team_need_templates does not exist` | примените миграции; `alembic current` должен показать `c25e_needs` |
| PDF не работает при Python на Windows | используйте Docker с системными библиотеками WeasyPrint |
| Кандидата нет в поиске | проверьте текущую подтверждённую категорию, публикацию и согласия |
| После смены аккаунта в другой вкладке появляется заглушка | обновите страницу: интерфейс перейдёт в кабинет текущей роли или на главную |
