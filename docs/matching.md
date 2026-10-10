# Поиск и просмотр кандидата — этап 6

## Правила

Поиск и прямой просмотр доступны только активному пользователю с ролью employer через существующие JWT/Bearer или cookie. Candidate ID означает ID CandidateProfile, не User.

Профиль доступен, если кандидат явно включил публикацию (`is_searchable=true`), пользователь активен и имеет роль candidate, а последняя запись среди `is_current=true` имеет статус CONFIRMED. Историческая подтверждённая категория не заменяет текущую неподтверждённую. При нескольких текущих записях выбирается наибольший ID, как в assessments.current_category; это защита чтения, не исправление конкурентных записей assessments.

Публикация по умолчанию выключена, включая существующие профили после новой миграции. Кандидат управляет ей на `/candidate/search-publication` и через GET/PATCH `/api/v1/candidates/me/search-publication`. PATCH принимает `{"is_searchable": true}`. Формы и изменения через cookie защищены CSRF-токеном; для cookie PATCH нужен `X-CSRF-Token` со страницы публикации. Bearer использует существующую авторизацию.

Контакты в search/detail не возвращаются даже при наличии принятого предложения: раскрытие конкретному участнику относится к этапу 7 и его отдельным маршрутам. DTO исключают email, phone, user_id, внешние ID, ответы и snapshot тестов. Все публикуемые свободные строки проходят скрытие стандартных email, телефонов, URL и @имён; шаблоны экранируют HTML. Произвольную запись контакта словами автоматически распознать невозможно: на странице согласия явно запрещено помещать контакты в профессиональные поля.

## Контракт

- GET `/api/v1/matching/candidates`: specialization, grade, повторяемый skills, all_skills (boolean, по умолчанию false), location (буквальное подстрочное совпадение), work_format (office/remote/hybrid), page (1..100000), page_size (1..50, по умолчанию 20).
- Навыки: по умолчанию любой из указанных (IN); all_skills=true требует все указанные, разрешая дополнительные навыки кандидата. Точное совпадение после trim/lower, не более 20, до 100 символов каждый. Неизвестная специализация/грейд даёт пустую выдачу. Неизвестные параметры API отклоняются с 422.
- Ответ: items и meta {total, page, page_size, total_pages}. Страница за пределами выдачи пуста; total не меняется.
- GET `/api/v1/matching/candidates/{candidate_id}`: подробный профиль или одинаковый 404 для отсутствующего, скрытого, неактивного или неподтверждённого кандидата.
- HTML: `/employer/search`, `/employer/candidates/{candidate_id}`. HTMX заменяет только результаты, сохраняет URL и фильтры; обычный GET работает без JS. Восстановление истории отдаёт полный документ.

Порядок задаётся в SQL: lower(full_name), profile ID. Пагинация выполняется SQL LIMIT/OFFSET, без пересортировки отдельных страниц. В обычном режиме используется один EXISTS с IN; при all_skills=true — EXISTS для каждого навыка. Выбор одной текущей категории и EXISTS исключают дубли. Достижения не обязательны, не фильтруют и не повышают позицию. Общего Score нет: match_reasons описывают категорию, matched_skills и сохранённый test_score. Подробный профиль содержит до 20 последних завершённых результатов без вопросов/ответов, опыт и реальные сохранённые достижения с is_demo. Если баллы подтверждения не сохранены, это прямо обозначено.

Кнопка «Пригласить» отключена до этапа 7. Ранее добавленные маршруты предложений сохранены, но не расширялись этой задачей. Старый ranking.py не используется новым поиском.

## Схема и проверки

Новая миграция: `75c8b36a9021`, после `8f70f2f704de`. Добавляет NOT NULL boolean с server default false. Рабочая БД не обновлялась. Новая схема и миграция публикации проверены на отдельной PostgreSQL 17: с нуля, повторным upgrade и обновлением заполненной схемы 8f70f2f704de. Старый риск snapshot-миграции на более ранних заполненных схемах остаётся отдельной задачей.

Безопасный набор: `pytest tests/backend tests/matching -q`. Для браузера: установить Chromium и RUN_E2E=1. `tests/matching/conftest.py` создаёт отдельную SQLite в памяти, заменяет get_session, запускает временный Uvicorn для браузера и очищает overrides; app SessionLocal не используется. В SQLite зарегистрирован Unicode lower для проверки кириллических фильтров. Это не подтверждение PostgreSQL collation или применения миграций.

Проверяются сочетания фильтров, все навыки, отсутствие дублей, стабильная пагинация, пустые страницы, история категорий, отсутствие ФСП, видимость, 401/403/404, контакты во всех представлениях, даты достижений, сохранение публикации и CSRF, HTMX, fallback без JS, JavaScript и переполнение на 1440/390/320 px. Скриншоты по умолчанию сохраняются вне проекта; путь можно задать MATCHING_SCREENSHOTS.

Прежние integration matching-тесты адаптированы к новому контракту, но всё ещё требуют подтверждённого отдельного app/PostgreSQL. Не запускать RUN_INTEGRATION=1 на рабочем окружении.

Для запуска устранены существовавшие конфликтные маркеры в app/web/router.py, base.html, main.css и candidates/profile.html; сохранены формы ФСП и маршруты предложений. README с предшествующим конфликтом не изменялся.


## Docker-проверка 09.10.2026

Использован `compose.test.yaml`, отдельный проект `fsp-matching-check-20261009`, собственный `postgres_test_data`, PostgreSQL 17 и явно заданные тестовые настройки. Обычный compose.yaml, .env и рабочие volumes не использовались. Порты выдаются динамически; после restart адреса нужно получать заново через `docker compose ... port`.

Результаты отдельных прогонов:

| Проверка | Результат |
|---|---|
| Существующий backend-набор | 114 passed |
| Все существующие integration-тесты через Docker app и его PostgreSQL | 116 passed |
| Matching на отдельных PostgreSQL-базах, включая 5 Playwright-тестов | 43 passed |
| Alembic с нуля, повторный upgrade, публикация на заполненной схеме с ответами | 2 passed |
| Применимые E2E через Docker app | 21 passed (18 существующих и 3 новых поиска) |
| Два старых E2E предложений | Исключены из этапа 6; требуют RUN_OFFER_E2E=1 и актуализации UI на этапе 7 |
| SMTP в Mailpit и подтверждение по ссылке из полученного письма | Успешно |
| Seed-loader повторно | 101 вопрос, 0 дублей |
| Restart PostgreSQL и app | Readiness восстановился, количества записей сохранились |

Первый полный E2E-прогон выявил, что старые tests/e2e/test_matching_flow.py используют обычный Compose без выбора проекта и ожидают прежний UI с рейтингом/формой предложения. Им добавлена явная привязка к тестовому проекту и отдельный флаг этапа 7. Новый tests/e2e/test_matching_search.py проверяет рабочий этап 6 через app-контейнер: кандидат публикует профиль, работодатель находит его, контакты скрыты, отзыв согласия закрывает прямой просмотр. Новая проверка входа использует форму по action, а не прежнее название кнопки.

MATCHING_TEST_DATABASE_URL включает PostgreSQL-режим tests/matching/: для каждого теста создаётся собственная случайно названная база, удаляемая после теста. Основная тестовая база не очищается этим набором. Миграционные тесты тоже используют собственные новые базы. Схему обычного приложения эти проверки не изменяют.

### Повторение в PowerShell

```powershell
$env:TEST_COMPOSE_PROJECT = "fsp-matching-check-" + (Get-Date -Format yyyyMMddHHmmss)
$stack = $env:TEST_COMPOSE_PROJECT
docker compose -f compose.test.yaml -p $stack up -d --build --wait --wait-timeout 120
$testDbAddress = (docker compose -f compose.test.yaml -p $stack port db 5432).Trim()
$env:DATABASE_URL = "postgresql+psycopg://fsp_test:fsp_test_only@$testDbAddress/fsp_matching_test"
$env:MATCHING_TEST_DATABASE_URL = $env:DATABASE_URL
$env:APP_BASE_URL = "http://" + (docker compose -f compose.test.yaml -p $stack port app 8000).Trim()
$env:FSP_BASE_URL = "http://" + (docker compose -f compose.test.yaml -p $stack port mini-fsp-id 8000).Trim()
$env:MAILPIT_BASE_URL = "http://" + (docker compose -f compose.test.yaml -p $stack port mailpit 8025).Trim()
$env:SMTP_HOST = "127.0.0.1"
$env:SMTP_PORT = (docker compose -f compose.test.yaml -p $stack port mailpit 1025).Trim().Split(':')[-1]
$env:RUN_INTEGRATION = "1"
$env:RUN_E2E = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:E2E_SCREENSHOTS = Join-Path $env:TEMP "fsp-docker-e2e-screenshots"
$env:MATCHING_SCREENSHOTS = Join-Path $env:TEMP "fsp-docker-matching-screenshots"
$env:DOCKER_SCREENSHOTS = Join-Path $env:TEMP "fsp-docker-app-screenshots"
Remove-Item Env:RUN_OFFER_E2E -ErrorAction SilentlyContinue
docker compose -f compose.test.yaml -p $stack exec -T app python -m app.modules.assessments.seed_loader
uv run --locked playwright install chromium
uv run --locked pytest tests/backend tests/integration tests/matching tests/e2e -q -p no:cacheprovider --output="$env:TEMP/fsp-docker-playwright"
```

При обычной остановке использовать `docker compose -f compose.test.yaml -p $stack stop`: тестовый volume сохранится. Рабочий проект не останавливать и команду с `-v` не использовать.


## Выбор режима навыков

По запросу работодателя режим по умолчанию возвращён к любому совпадению: один EXISTS с IN. Галочка «Все указанные навыки» передаёт all_skills=true и включает отдельный EXISTS для каждого запрошенного навыка. Кандидат может иметь дополнительные навыки — равенство полного набора не требуется. Без списка навыков оба режима не ограничивают выдачу. Параметр сохраняется в URL, пагинации и после перезагрузки; сброс фильтров выключает галочку. Объяснение карточки различает совпавшие навыки и совпадение всех запрошенных.

Проверки изменения: 52 локальных теста, 24 целевых проверки на отдельной PostgreSQL (включая браузер), 3 E2E через обновлённый Docker app на 1440/390/320 px — успешно. Проверен кандидат с дополнительными навыками. Модели и миграции для этого изменения не требуются.


## Предложения и отзыв публикации

Новые приглашения можно отправлять только опубликованным активным кандидатам, в том числе через прямой POST. Сервис проверяет это при создании предложения. Изменение публикации и создание предложения блокируют одну строку профиля: после завершённого отзыва новая отправка запрещена. Ранее отправленные предложения остаются доступны своим участникам для просмотра и ответа независимо от публикации.

Кандидат может принять или отклонить предложение. Повтор того же ответа возвращает сохранённый результат без изменения даты; противоположный ответ после конечного статуса запрещён. Email и телефон кандидата доступны только работодателю, отправившему принятое предложение.
