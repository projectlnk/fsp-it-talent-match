# Журнал изменений

## 2026-10-09 — последнее Code Review 

### 1. Итог ревью

В `New_README.md`: 1 — основа, 2 — регистрация/права, 3 — профили, 4 — тестирование, 5 — поиск, 6 — предложения. В другой части `README.md`: 4–5 — мок и импорт ФСП, 6 — поиск. Проверены обе группы: основа, auth, профили, тестирование, поиск, предложения; ФСП также проверена как источник данных поиска. PDF и новые функции вне этих требований не реализовывались.

**Исходное состояние.** Ветка `dev/cheykdop`, HEAD `924f869` («Подгрузил последние изменение»).  Оба README сохранены побайтно относительно начала ревью.

| Пункт | Что проверено | Найдено и исправлено | Ограничения / остаток |
| --- | --- | --- | --- |
| 1. Основа, модели, схема, запуск | 18 таблиц, связи/FK/уникальность, агрегатор моделей, цепочка Alembic, startup, отдельный Compose | Добавлена новая миграция снятия default `answered_at`; исходные ответы не меняются. На пустом банке startup загружает вопросы; при повторном запуске сохраняет отредактированные задания. Добавлена защита тестов от записи в неподтверждённый внешний стек | Старая миграция snapshot не обновляет БД с ответами до этой ревизии. Это воспроизведённый блокер, а не успешно пройденный upgrade. Без исходных параметров заданий способ переноса требует решения. Переход с удалённой `0001_initial` не проверен |
| 2. Регистрация и права | HTML/API, роль из БД, Bearer/cookie, inactive, пароль, подтверждение и повторное письмо, доступ к чужим данным | HTML-регистрация использует `UserRegister`; ошибочные email/пароль/роль не создают пользователя. Потребление verification token защищено блокировкой строки. Ужесточен локальный `next`; описание API приведено к фактическому входу без обязательного подтверждения | Обязательность подтверждения email не согласована и не менялась. Согласие при регистрации в БД не сохраняется, хотя `docs/architecture.md` его заявляет. Реальный open redirect в исходном браузерном маршруте не доказан: `RedirectResponse` кодирует спецсимволы; изменение `next` устраняет неоднозначные значения на уровне валидатора |
| 3. Профили кандидата и работодателя | API/HTML, сохранение, валидация, принадлежность навыков/опыта, частичный PATCH, ошибки и rollback | Отклоняются `null`/пробелы обязательных полей. PATCH зарплаты и дат проверяет итоговое состояние вместе с сохранёнными значениями. HTML перестал превращать неверные числа/даты/формат работы в `None`. Email работодателя проверяется схемой. Дублирующее переименование навыка даёт 409 с rollback; сохранение нулевых чисел в форме исправлено | Формы возвращают сохранённый профиль при ошибке, поэтому несохранённый ввод не восстанавливается. Расширенное редактирование навыка/опыта есть в API; UI по-прежнему предлагает добавление/удаление — новая функция редактирования в рамках ревью не добавлялась |
| 4. Тестирование и категории | Пул, snapshot, ответ, продолжение, расчёт, история, current, ограничения, повторные/конкурентные запросы | Исправлен `sql_group_by`: правильное объяснение присутствует в вариантах. Ответ должен соответствовать типу/вариантам вопроса. Старт/ответ/завершение сериализуются по профилю; двойной старт возвращает одну попытку, двойной finish создаёт одну категорию. Cooldown опирается на последнее подтверждение, поэтому провал текущей категории не снимает ограничение. Убрано неверное обещание «попытка не сгорает» | Провал по-прежнему заменяет текущую категорию; правило не менялось. Нужно согласовать сброс 60 дней при повторном подтверждении того же грейда, подсчёт провалов по всей истории и допустимость одновременных попыток разных категорий. UI обслуживает single_choice; другие типы перечислены в модели/API, но в текущем банке их нет |
| 5 по New_README / 6 по заданию. Поиск и просмотр | Общий сервис HTML/API, актуальная подтверждённая категория, публикация, активная роль, DTO, контакты, навыки ANY/ALL, сочетания фильтров, уникальность строк, SQL-сортировка, страницы, отсутствие ФСП, HTMX/history restore | Основная реализация уже существовала до ревью. В этом ревью исправлено отображение ошибок HTML/HTMX: JSON больше не появляется вместо страницы, ошибка HTMX видима в целевом блоке. Подготовка integration-данных использует отдельный сервис публикации вместо произвольного PATCH профиля | Контакты исключены из DTO и типовые контакты в свободном тексте маскируются. Это не гарантия распознавания любых обфусцированных контактов в произвольном тексте. Приглашение в новой карточке намеренно отключено до этапа 7. Нет произвольного общего Score; `ranking.py` остался неиспользуемым наследием |
| 6 по New_README. Предложения | API/HTML списков и ответа, участники, зарплата, статусы, повторный ответ, раскрытие контактов | Конкурентные просмотр/принятие/отказ блокируют строку и перечитывают состояние; конечное решение одно. Пробельный заголовок не принимается. Контакты в свободном `full_name` скрываются и в DTO предложения. Выбор текущей категории в brief стал детерминированным | Создание предложения через новую карточку поиска не подключено; два старых UI E2E остаются пропущенными. API создания допускает существующий профиль без публикации/подтверждения: нужно согласовать правило адресного приглашения после отзыва публикации; произвольно менять его в ревью не стали |
| ФСП: пункты 4–5 другой версии плана | HTTPX, реальный тестовый mock, link/import/unlink, уникальность, повторный импорт, пустая история, ошибки | Перед записью проверяются контракт всего пакета и `participant_id` каждого достижения; чужое достижение отклоняется. Некорректные даты/числа/длины не записываются. Конфликты link/import откатываются, HTTP/JSON-ошибки реестра получают контролируемый ответ. Импорт и unlink блокируют профиль | Это демонстрационная привязка, не доказательство владения реальным ФСП ID. Мок не содержит соревнования, membership и участие команды в конкретном соревновании; проверка командного права невозможна по одному `team_name`. Новые предметные функции мока не добавлялись |


Миграционный diagnostic `test_legacy_populated_snapshot_migration_reports_known_blocker` **ожидает отказ старого upgrade** и сохранение старой строки/ревизии. Его прохождение не означает, что перенос старых ответов исправлен. Новая схема отдельно сравнивается с ORM, включая server defaults.

**Где документы расходятся с кодом.** `README.md` содержит неразрешённые маркеры конфликта и одновременно разные снимки состояния; его таблица «нет поиска/предложений/импорта» относится к `cade45e`. `New_README.md` полезен как требования и архитектура, но описывает старую пустую заготовку: предметные модули, модели, миграции и Git уже существуют. `docs/architecture.md` всё ещё описывает Python-ranking и `ranking_reasons`, тогда как рабочий поиск использует SQL-сортировку и `match_reasons`; утверждение о сохранённом согласии регистрации не подтверждается моделью/формой. `docs/fsp-integration.md` обещает влияние достижений на ranking, отсутствующее в согласованном этапе 6. `docs/testing.md`, на который ссылается README, отсутствует. Эти документы не переписывались поверх пользовательских изменений.

**Непроверенное и вопросы, которые нельзя решить произвольно:**

- Как переносить ответы из БД до snapshot, если исходные случайные параметры не сохранены? Нельзя подставлять новый случайный вопрос и выдавать его за исходный. Что делать с незавершёнными такими попытками?
- Должен ли провал новой попытки лишать уже подтверждённой категории? Нужно ли продлевать cooldown после подтверждения того же грейда?
- Обязателен ли verified email до входа/публикации, и какое согласие нужно сохранять при регистрации?
- Разрешены ли прямые предложения непубликованному кандидату, уже найденному ранее, и какова связь отзыва публикации с новыми приглашениями?
- Командное достижение требует новых данных participation/membership в мок-контракте; текущая проверка подтверждает только participant_id ответа.
- Не проверялись рабочая БД, её данные, переход с удалённой ревизии, production TLS/cookie secure, полноценный Keycloak/OIDC, PDF и окончательная форма отправки приглашения. Эти проверки не выдаются за успешные.

#### `app/modules/candidates/models.py` — CandidateProfile

Добавлено отдельное согласие публикации для поиска, без изменения чужих моделей категории/достижений.

**Было:**

```python
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

**Стало:**

```python
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
```

Публикация opt-in: новые и существующие профили по умолчанию скрыты. Поле `test_score` и миграция `8f70f2f704de` уже принадлежали реализации разработчика.

#### `migrations/versions/75c8b36a9021_candidate_search_consent.py` — upgrade

Поддержка публикации в PostgreSQL.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def upgrade():
    op.add_column("candidate_profiles", sa.Column("is_searchable", sa.Boolean(), nullable=False, server_default=sa.false()))

```

Добавлена только колонка false NOT NULL; данные профиля и ответы не меняются.

#### `app/modules/matching/queries.py` — visible_candidates, count_candidates, page_candidates

Выделены SQL-запросы фильтрации и пагинации.

**Было:**

Файл отсутствовал.

**Стало:**

```python
    latest = select(func.max(history.id)).where(
        history.candidate_profile_id == CandidateProfile.id,
        history.is_current.is_(True),
    ).correlate(CandidateProfile).scalar_subquery()
    stmt = (select(CandidateProfile, CandidateCategory, Specialization, Grade)
```

MAX(id) среди current убирает дубли категории; фильтры EXISTS не размножают строки. Дополнительно проверяются active user, candidate role, opt-in и confirmed.

#### `app/modules/matching/queries.py` — visible_candidates: навыки ANY/ALL

ANY через IN уже существовал у разработчика. По последнему указанию пользователя добавлена галочка ALL при сохранении ANY по умолчанию.

Исходный код до выделения файла — `app/modules/matching/service.py`:

```python
                .where(func.lower(CandidateSkill.skill).in_(normalized))
                .scalar_subquery()
            )
```

**Было:**

Файл отсутствовал.

**Стало:**

```python
        if filters.all_skills:
            for skill in filters.skills:
                stmt = stmt.where(exists(select(CandidateSkill.id).where(
                    CandidateSkill.candidate_profile_id == CandidateProfile.id,
                    skill_name == skill)))
        else:
            stmt = stmt.where(exists(select(CandidateSkill.id).where(
                CandidateSkill.candidate_profile_id == CandidateProfile.id,
                skill_name.in_(filters.skills))))
    if filters.location:
```

ANY требует хотя бы одно совпадение. ALL требует каждый указанный навык; дополнительные навыки кандидата допустимы. Точные промежуточные незакоммиченные варианты прежнего ALL-only не сохранены и не выдумываются.

#### `app/modules/matching/queries.py` — page_candidates / count_candidates

Стабильная SQL-пагинация вместо пересортировки ограниченного окна.

Исходный код до выделения файла — `app/modules/matching/service.py`:

```python
    items.sort(key=lambda c: (-c.ranking_score, c.profile_id))
    items = items[query.offset : query.offset + query.limit]
```

**Было:**

Файл отсутствовал.

**Стало:**

```python
def page_candidates(filters):
    return visible_candidates(filters).options(
        selectinload(CandidateProfile.skills), selectinload(CandidateProfile.fsp_achievements)
    ).order_by(func.lower(CandidateProfile.full_name), CandidateProfile.id).offset(
        (filters.page - 1) * filters.page_size).limit(filters.page_size)
```

Сортировка по lower(full_name), затем ID; LIMIT/OFFSET применяются после всех фильтров. COUNT использует те же условия, без Python Score. Старый сервис существовал, это его изменение.

#### `app/modules/matching/schemas.py` — CandidateSearchQuery, CandidateCardRead, CandidateDetailRead, SearchMeta

Безопасные DTO, page/page_size и объяснение совпадений.

**Было:**

```python
    ranking_score: float
    ranking_reasons: list[str]

    skills: list[CandidateSkillBrief] = Field(default_factory=list)
```

**Стало:**

```python
    matched_skills: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    skills: list[CandidateSkillBrief] = Field(default_factory=list)
    fsp_has_achievements: bool = False
```

Общий рейтинг удалён из рабочего контракта; карточка и детали разделены. Query запрещает неизвестные параметры, навыки нормализуются. page_size ограничен 50.

#### `app/modules/matching/schemas.py` — FspAchievementBrief.competition_date

Дата достижения должна соответствовать Date модели, а не datetime.

**Было:**

```python
    competition_date: datetime | None = None
```

**Стало:**

```python
    competition_date: date | None = None
```

Устранено несоответствие типа даты в публичном DTO.

#### `app/modules/matching/service.py` — search_candidates, _card, get_candidate_card

Один сервис видимости/поиска/карточки для HTML и API.

**Было:**

```python
def _base_query(query: CandidateSearchQuery) -> Select:
    """Строит SELECT по текущим категориям с фильтрами.

    Использует JOIN к категории, специализации и грейду. Профиль
    присоединяется через candidate_profile_id. Скрывает:
```

**Стало:**

```python
def search_candidates(session, query):
    total = session.scalar(queries.count_candidates(query)) or 0
    rows = session.execute(queries.page_candidates(query)).all()
    return CandidateSearchResult(items=[_card(row, query) for row in rows],
        meta=SearchMeta(total=total, page=query.page, page_size=query.page_size,
```

Исходный matching и его категории/навыки сохранены как предметная основа. В выдаче новый безопасный DTO; подробности получают только видимый профиль и до 20 завершённых результатов.

#### `app/modules/matching/service.py` — public_text / _card

Свободный текст может содержать контакты при отсутствии phone/email в DTO.

**Было:**

```python
full_name=profile.full_name
```

**Стало:**

```python
def public_text(value):
    return _CONTACT.sub('[контакт скрыт]', value) if value else value
```

Перед отдачей маскируются типовые email, телефоны, URL и @handles; HTML дополнительно экранируется Jinja. Это защита типовых форматов, не доказанная универсальная очистка произвольного текста.

#### `app/modules/matching/router.py` — search_candidates, get_candidate

Рабочие employer-only API и единая модель query.

**Было:**

```python
def search_candidates(
    specialization: str | None = Query(default=None, max_length=100),
    grade: str | None = Query(default=None, max_length=50),
```

**Стало:**

```python
def search_candidates(filters: Annotated[CandidateSearchQuery, Query()],
    user: User = Depends(_EMPLOYER_ONLY), session: Session = Depends(get_session)):
    return service.search_candidates(session, filters)
```

Сохранены URL /api/v1/matching/candidates и карточки; роль проверяется существующим require_role. Детальный response_model теперь CandidateDetailRead; добавлено no-store.

#### `app/modules/matching/publication.py` — read_publication, update_publication, csrf_token/check_csrf

Владелец управляет публикацией через отдельный маршрут.

**Было:**

Файл отсутствовал.

**Стало:**

```python
@router.patch('', response_model=SearchPublication)
def update_publication(payload: SearchPublication, request: Request,
    user: User = Depends(CANDIDATE_ONLY), session: Session = Depends(get_session),
    x_csrf_token: str | None = Header(None)):
    if not request.headers.get('authorization', '').lower().startswith('bearer '):
```

PATCH cookie-запросов требует CSRF; Bearer работает через прежнюю авторизацию. Работодатель не меняет согласие кандидата. HMAC использует настройку секрета; значение секрета здесь не приводится.

#### `app/modules/matching/web.py` — search, detail, publication, save_publication

Подключены реальные страницы и HTMX к общему сервису.

**Было:**

Файл отсутствовал.

**Стало:**

```python
    partial = request.headers.get('hx-request') == 'true' and request.headers.get('hx-history-restore-request') != 'true'
    response = templates.TemplateResponse(request=request,
        name='matching/_results.html' if partial else 'matching/search.html', context=context)
    response.headers['Vary'] = 'HX-Request, HX-History-Restore-Request'
    response.headers['Cache-Control'] = 'no-store'
```

HTMX получает только результаты, history restore — полную страницу; query сохраняется в ссылках страниц. Настройки публикации принадлежат кандидату и защищены CSRF.

#### `app/api/router.py` — api_v1 / include_router

Исправлен порядок подключения роутеров, уже добавленных разработчиком.

**Было:**

```python
router.include_router(api_v1)
api_v1.include_router(matching_router)
api_v1.include_router(candidates_router)
```

**Стало:**

```python
api_v1.include_router(employer_offers_router)
api_v1.include_router(publication_router)
router.include_router(api_v1)
```

FastAPI копирует маршруты при include_router: раньше matching/offers добавлялись после подключения api_v1 к корню. Теперь все добавлены до него, кандидаты/работодатели не дублируются.

#### `app/web/router.py` — подключения HTML-роутеров

Разрешён конфликт с сохранением реальных модулей, дизайна и предложений.

**Было:**

```python
<<<<<<< Updated upstream
from app.modules.employers.web import router as employers_web_router
```

**Стало:**

```python
router.include_router(matching_web_router)
router.include_router(candidates_offers_web_router)
```

Подключён matching.web; конфликтные маркеры и повторные подключения удалены. Создание auth, profiles, assessments и offers не приписывается этой правке.

#### `app/modules/employers/web.py` — прежние search_page / candidate_page; сохранён offer_create

Удалены дублирующие обработчики поиска из employers.web.

**Было:**

```python
def search_page(
    request: Request,
    specialization: str = "",
```

**Стало:**

```python
            "matching/detail.html",
            {"card": card, "error": str(exc)},
            status_code=status.HTTP_400_BAD_REQUEST,
```

Рабочими стали маршруты matching.web. Код отправки предложений разработчика сохранён; его ошибка рендерит актуальный шаблон. Это перенос подключения, не создание employer-профиля/предложений.

#### `app/templates/matching/search.html` — форма поиска

Фильтры, реальные GET/HTMX, галочка всех навыков.

**Было:**

Файл отсутствовал.

**Стало:**

```html
<form class="card form" method="get" action="/employer/search" hx-get="/employer/search" hx-target="#matching-results" hx-swap="outerHTML" hx-push-url="true">
<div class="form-row"><label>Специализация<select name="specialization"><option value="">Все</option>{% for s in specializations %}<option value="{{ s.code }}" {% if filters.specialization == s.code %}selected{% endif %}>{{ s.name }}</option>{% endfor %}</select></label>
```

Шаблон создан для работающего маршрута и реальных данных, без замены ими /design-preview.

#### `app/templates/matching/_results.html` — выдача / pagination

Карточки, empty state и ссылки страниц.

**Было:**

Файл отсутствовал.

**Стало:**

```html
<section id="matching-results" class="stack" aria-live="polite" style="margin-top:24px"><h2>Найдено: {{ result.meta.total }}</h2>
{% for c in result.items %}<article class="card"><div class="candidate-head"><h3><a href="/employer/candidates/{{ c.profile_id }}">{{ c.full_name }}</a></h3><span class="tag tag-purple">{{ c.specialization_name }} / {{ c.grade_name }}</span></div>
```

Шаблон создан для работающего маршрута и реальных данных, без замены ими /design-preview.

#### `app/templates/matching/detail.html` — профиль кандидата

Подробные разрешённые данные; кнопка приглашения оставлена для следующего этапа.

**Было:**

Файл отсутствовал.

**Стало:**

```html
{% extends 'base.html' %}{% block title %}{{ card.full_name }} · FSP IT Talent Match{% endblock %}{% block content %}
<a class="text-link" href="/employer/search">← Поиск кандидатов</a><div class="page-heading"><p class="eyebrow">Профиль кандидата</p><h1>{{ card.full_name }}</h1><p>{{ card.desired_role or 'ИТ-специалист' }}{% if card.location %} · {{ card.location }}{% endif %}</p></div>
```

Шаблон создан для работающего маршрута и реальных данных, без замены ими /design-preview.

#### `app/templates/matching/publication.html` — настройка публикации

Реальная форма opt-in с CSRF вместо демо-настройки.

**Было:**

Файл отсутствовал.

**Стало:**

```html
{% extends 'base.html' %}{% block content %}<div class="page-heading"><p class="eyebrow">Кабинет кандидата / Приватность</p><h1>Публикация в поиске</h1><p>Вы решаете, доступен ли ваш профиль работодателям.</p></div>
{% if request.query_params.get('saved') == '1' %}<div class="notice" role="status">Настройка сохранена.</div>{% endif %}
```

Шаблон создан для работающего маршрута и реальных данных, без замены ими /design-preview.

#### `app/templates/base.html` — навигация / разрешение конфликта

Согласованы ссылки дизайна с реальными search/publication/offers.

**Было:**

```html
<<<<<<< Updated upstream
```

**Стало:**

```html
<a href="/employer/search">Поиск кандидатов</a>
```

Прежний дизайн и формы сохранялись. Наличие отдельных ссылок работодателя у разработчика не выдаётся за создание новой бизнес-функции.

#### `app/templates/components/sidebar.html` — навигация / разрешение конфликта

Согласованы ссылки дизайна с реальными search/publication/offers.

**Было:**

```html
{% if preview_mode %}Демонстрация{% elif user.role.value == 'candidate' %}Кабинет кандидата{% else %}Кабинет работодателя{% endif %}</p><nav aria-label="Разделы кабинета">
{% if preview_mode %}{% for href,label,mark in [('/design-preview','Обзор экра
```

**Стало:**

```html
/employer/search
```

Прежний дизайн и формы сохранялись. Наличие отдельных ссылок работодателя у разработчика не выдаётся за создание новой бизнес-функции.

#### `app/templates/candidates/profile.html` — навигация / разрешение конфликта

Согласованы ссылки дизайна с реальными search/publication/offers.

**Было:**

```html
<<<<<<< Updated upstream
```

**Стало:**

```html
/candidate/search-publication
```

Прежний дизайн и формы сохранялись. Наличие отдельных ссылок работодателя у разработчика не выдаётся за создание новой бизнес-функции.

#### `app/static/css/main.css` — разрешение конфликтов и matching layout

Убраны маркеры; добавлены перенос текста и гибкая пагинация.

**Было:**

```css
<<<<<<< Updated upstream
```

**Стало:**

```css
#matching-results .card,.matching-text{overflow-wrap:anywhere} .matching-text{white-space:pre-wrap} .matching-pagination{flex-wrap:wrap} #matching-results .tag-row{flex-wrap:wrap}
```

Обе нужные части прежнего дизайна сохранены; карточки и страницы не создают горизонтального переполнения.

#### `tests/backend/test_working_form_contracts.py` — test_working_form_contract_unchanged

Добавление ФСП-форм разработчиком не должно разрушать проверку старых полей.

**Было:**

```python
    assert parser.forms == CONTRACTS[name]
```

**Стало:**

```python
    original = CONTRACTS[name]
    actions = {(f['method'], f['action']) for f in original}
    assert [f for f in parser.forms if (f['method'], f['action']) in actions] == original
```

Проверяются неизменные исходные формы; наличие новых действий разрешено. Это проверка контрактов шаблона, а не успешного сохранения — реальный путь проверяется отдельными тестами.

#### `tests/e2e/test_design_preview.py` — SCREENSHOTS

Результаты тестов можно хранить вне проекта.

**Было:**

```python
SCREENSHOTS = Path(__file__).resolve().parents[2] / "docs" / "design-preview" / "screenshots"
```

**Стало:**

```python
SCREENSHOTS = Path(os.getenv("E2E_SCREENSHOTS", str(Path(__file__).resolve().parents[2] / "docs" / "design-preview" / "screenshots")))
```

Добавлена E2E_SCREENSHOTS; исходные визуальные тесты сохранены.

#### `tests/e2e/test_working_template_rendering.py` — SCREENSHOTS

Результаты тестов можно хранить вне проекта.

**Было:**

```python
SCREENSHOTS = Path(__file__).resolve().parents[2] / "docs/design-preview/screenshots"
```

**Стало:**

```python
SCREENSHOTS = Path(os.getenv("E2E_SCREENSHOTS", str(Path(__file__).resolve().parents[2] / "docs/design-preview/screenshots")))
```

Добавлена E2E_SCREENSHOTS; исходные визуальные тесты сохранены.

#### `tests/e2e/test_matching_flow.py` — pytestmark / _test_compose

Старый E2E предложений не соответствует новой отключённой форме.

**Было:**

```python
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
```

**Стало:**

```python
pytestmark = [
    pytest.mark.skipif(os.getenv("RUN_OFFER_E2E") != "1", reason="Stage 7 invitation form is not connected; set RUN_OFFER_E2E=1 only after that stage"),
    pytest.mark.e2e,
```

Две проверки явно пропускаются до этапа 7. Подготовка данных требует отдельного compose.test.yaml и проекта fsp-matching-check-; не выполняется в рабочем Compose.

#### `tests/integration/test_matching_service.py` — фильтры, пагинация, explain

Прежние тесты адаптированы к реальному opt-in и новому контракту, не создан поиск разработчика заново.

**Было:**

```python
CandidateSearchQuery(limit=2, offset=0)
```

**Стало:**

```python
CandidateSearchQuery(page_size=2, page=1)
```

Проверяются page/page_size, match_reasons и кандидат без ФСП; arbitrary ranking и only_confirmed=false перестали быть рабочим контрактом.

#### `tests/integration/test_matching_api.py` — подготовка профиля и ответы

Подготовка published-профиля и новый response contract.

**Было:**

```python
        profile = session.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
```

**Стало:**

```python
        profile.is_searchable = True
        s = session.scalar(select(Specialization).where(Specialization.code == spec))
```

Старые API tests сохранены и адаптированы к opt-in, page и объяснимым причинам. Подробные новые проверки дополняют их.

#### `tests/matching/conftest.py` — database / matching_server

Добавлены независимые проверки реального поведения этапа 6.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def database():
    admin = None
    database_name = None
    test_url = os.getenv('MATCHING_TEST_DATABASE_URL')
```

Тесты покрывают роль, opt-in, фильтры ANY/ALL, категории/history, отсутствие дублей и контактов, страницы и mobile. Наличие файла не заменяет результат запуска; результаты прежних запусков не суммируются с текущими.

#### `tests/matching/test_search.py` — API, пагинация и приватность

Добавлены независимые проверки реального поведения этапа 6.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_pagination(client,headers):
    first=client.get(API+'?page_size=3',headers=headers).json();last=client.get(API+'?page_size=3&page=2',headers=headers).json()
    assert first==client.get(API+'?page_size=3',headers=headers).json()
    assert first['meta']=={'total':4,'page':1,'page_size':3,'total_pages':2}
```

Тесты покрывают роль, opt-in, фильтры ANY/ALL, категории/history, отсутствие дублей и контактов, страницы и mobile. Наличие файла не заменяет результат запуска; результаты прежних запусков не суммируются с текущими.

#### `tests/matching/test_browser.py` — реальный HTML/HTMX

Добавлены независимые проверки реального поведения этапа 6.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_search_navigation_htmx_mobile(page,matching_server,headers,width):
    page.set_extra_http_headers(headers);page.set_viewport_size({'width':width,'height':1000})
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(matching_server+'/employer/search?page_size=2')
```

Тесты покрывают роль, opt-in, фильтры ANY/ALL, категории/history, отсутствие дублей и контактов, страницы и mobile. Наличие файла не заменяет результат запуска; результаты прежних запусков не суммируются с текущими.

#### `tests/matching/test_migrations.py` — Alembic на собственной БД

Добавлены независимые проверки реального поведения этапа 6.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_fresh_migrations_and_repeat_upgrade(migration_database):
    engine,upgrade=migration_database
    upgrade('head');upgrade('head')
    with engine.connect() as conn:
```

Тесты покрывают роль, opt-in, фильтры ANY/ALL, категории/history, отсутствие дублей и контактов, страницы и mobile. Наличие файла не заменяет результат запуска; результаты прежних запусков не суммируются с текущими.

#### `tests/e2e/test_matching_search.py` — поиск на изолированном Docker app

Добавлены независимые проверки реального поведения этапа 6.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def actors(app_base_url):
    project=os.environ['TEST_COMPOSE_PROJECT']
    assert project.startswith('fsp-matching-check-')
    command=['docker','compose','-f','compose.test.yaml','-p',project]
```

Тесты покрывают роль, opt-in, фильтры ANY/ALL, категории/history, отсутствие дублей и контактов, страницы и mobile. Наличие файла не заменяет результат запуска; результаты прежних запусков не суммируются с текущими.

#### `compose.test.yaml` — отдельный стек app/db/mini-fsp-id/mailpit

Изолированная инфраструктура для проверок с записью.

**Было:**

Файл отсутствовал.

**Стало:**

```yaml
services:
  app:
    build: .
    image: fsp-matching-check:local
```

Используются отдельная тестовая БД, отдельный volume и случайные localhost-порты; .env рабочего проекта не подключается. Параметры доступа не цитируются.

#### `docs/matching.md` — правила и команды этапа 6

Документация заменена фактическим контрактом поиска.

**Было:**

```markdown
# Механика подбора и ранжирования
```

**Стало:**

```markdown
# Поиск и просмотр кандидата — этап 6
```

Отдельно описаны opt-in, confirmed, ANY/ALL, безопасные DTO, стабильная SQL-пагинация, отсутствие общего Score и запуск изолированных проверок.


### 3. Новые исправления по результатам последнего Code Rewiev

В этом разделе «Было» — точные фрагменты сохранённых рабочих файлов, включая существующие изменения пользователя; «Стало» — файлы после текущего ревью. Фрагменты намеренно короткие, полные версии доступны в исходном снимке и текущих файлах. Отсутствовавшие функции внутри существующего файла отмечены отдельно от отсутствовавших файлов.

#### `app/modules/auth/web.py` — register_submit

HTML обходил EmailStr и ограничения пароля/имени.

**Было:**

```python
    role_enum: UserRole | None = None
    try:
        role_enum = UserRole(role)
    except ValueError:
        error = "Некорректная роль"
```

**Стало:**

```python
        payload = UserRegister(email=email, password=password, role=role,
                               full_name=full_name or None)
        service.register_user(session, **payload.model_dump())
        return RedirectResponse("/auth/check-email", status_code=status.HTTP_303_SEE_OTHER)
    except ValidationError:
```

Неверная регистрация возвращает HTML 400, данные не записываются. API и форма используют один UserRegister.

#### `app/modules/auth/web.py` — _safe_next

Локальный redirect допускает неоднозначные обратные слеши и управляющие символы.

**Было:**

```python
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value
```

**Стало:**

```python
    if (not value or not value.startswith("/") or value.startswith("//")
            or "\\" in value or any(ord(char) < 32 for char in value)):
        return "/"
```

Такие next приводят на /. Существовавшая защита от // сохраняется. Эксплойт перенаправления на чужой origin через RedirectResponse не заявляется: это уточнение валидации входного значения.

#### `app/modules/auth/service.py` — verify_email

Два параллельных запроса могли потребить один token.

**Было:**

```python
        select(EmailVerificationToken).where(EmailVerificationToken.token == token)
```

**Стало:**

```python
        select(EmailVerificationToken).where(EmailVerificationToken.token == token).with_for_update()
```

Строка блокируется FOR UPDATE; второй запрос видит used_at и получает InvalidVerificationToken.

#### `app/modules/auth/router.py` — register: описание

Комментарий обещал обязательную проверку email, которой authenticate_user не требует.

**Было:**

```python
    Отправляет письмо с подтверждением email. Токен доступа не выдаётся:
    сначала нужно подтвердить адрес, потом войти.
    """
```

**Стало:**

```python
    Отправляет письмо с подтверждением email. Токен доступа не выдаётся.
    Вход пока разрешён и без подтверждения; обязательность подтверждения
    требует отдельного согласования.
```

Исправлено описание, а не неоднозначное правило входа.

#### `app/modules/candidates/schemas.py` — CandidateSkillCreate/Update, CandidateExperienceCreate/Update, CandidateProfileUpdate

Обязательные поля допускали null/пробелы; при PATCH is_current:null нарушал NOT NULL.

**Было:**

```python
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
```

**Стало:**

```python
    @field_validator('full_name', mode="before")
    @classmethod
    def _required_value(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("Поле не может быть пустым")
        return value.strip() if isinstance(value, str) else value

```

field_validator запускается для явно переданного значения. Отсутствующее поле PATCH по-прежнему допустимо; explicit null для обязательного поля — 422. Аналогичный валидатор добавлен skill, company_name, position, is_current; строки нормализуются до проверки длины.

#### `app/modules/candidates/service.py` — _validate / _lock_profile / update_profile

PATCH проверял только присланные поля, HTML обходил схемы; конкурентный PATCH мог проверять устаревшие границы.

**Было:**

```python
    profile = get_profile_by_user_id(session, user_id)
    for key, value in changes.items():
        setattr(profile, key, value)
    session.commit()
```

**Стало:**

```python
    profile = _lock_profile(session, user_id)
    changes = _validate(CandidateProfileUpdate, changes)
    _validate(CandidateProfileUpdate, {
        key: changes.get(key, getattr(profile, key))
        for key in ('desired_salary_from', 'desired_salary_to')
    })
    for key, value in changes.items():
        setattr(profile, key, value)
```

Один слой валидации для HTML и сервиса; profile блокируется и перечитывается. Зарплата проверяется вместе с сохранённой второй границей до setattr/commit. Сервис принимает поля схемы профиля; публикация управляется через отдельный сервис, не произвольный setattr.

#### `app/modules/candidates/service.py` — add_skill / update_skill / _commit_skill

Пробельный навык и конфликт переименования приводили к пустой строке либо IntegrityError.

**Было:**

```python
    normalized = skill.strip()
    existing = session.scalar(
```

**Стало:**

```python
    normalized = _validate(CandidateSkillCreate, {"skill": skill, "level": level})["skill"]
    existing = session.scalar(
```

Проверяются схемы create/update, profile lock сериализует добавления. Уникальный конфликт uq_candidate_skills_profile_skill либо соответствующий SQLite UNIQUE преобразуется в SkillAlreadyExists после rollback; другие IntegrityError не маскируются.

#### `app/modules/candidates/service.py` — _commit_skill

Точная обработка уникального конфликта вместо необработанного commit.

**Было:**

```python
    for key, value in changes.items():
        setattr(record, key, value)
    session.commit()
```

**Стало:**

```python
def _commit_skill(session):
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        sqlite_duplicate = "UNIQUE constraint failed: candidate_skills.candidate_profile_id, candidate_skills.skill" in str(exc.orig)
        if constraint == "uq_candidate_skills_profile_skill" or sqlite_duplicate:
            raise SkillAlreadyExists() from exc
        raise

```

API переименования возвращает 409, прежний навык остаётся сохранённым, сессия пригодна для дальнейшего чтения. Новый helper отсутствовал внутри существовавшего файла.

#### `app/modules/candidates/service.py` — add_experience / update_experience

Не проверялся итоговый порядок дат PATCH.

**Было:**

```python
    session.add(CandidateExperience(candidate_profile_id=profile.id, **data))
    session.commit()
    return get_profile_by_user_id(session, user_id)


def update_experience(
    session: Session,
    *,
```

**Стало:**

```python
    changes = _validate(CandidateExperienceUpdate, changes)
    _validate(CandidateExperienceCreate, {
        key: changes.get(key, getattr(record, key))
        for key in ('company_name', 'position', 'started_at', 'ended_at', 'description', 'is_current')
    })
    for key, value in changes.items():
        setattr(record, key, value)
    session.commit()
```

Create использует CandidateExperienceCreate; update сначала объединяет сохранённые поля с изменениями, валидирует их и только затем изменяет запись. Ошибка не записывает новые даты.

#### `app/modules/candidates/web.py` — profile_update

isdigit превращал неверные/отрицательные числа в None, неизвестный формат работы также обнулялся.

**Было:**

```python
    def _int_or_none(value: str) -> int | None:
        value = value.strip()
        return int(value) if value.isdigit() else None

    changes: dict = {
        "full_name": full_name.strip(),
        "phone": phone.strip() or None,
        "location": location.strip() or None,
```

**Стало:**

```python
    changes = {
        "full_name": full_name.strip(), "phone": phone.strip() or None,
        "location": location.strip() or None, "about": about.strip() or None,
        "desired_role": desired_role.strip() or None,
        "desired_salary_from": desired_salary_from.strip() or None,
        "desired_salary_to": desired_salary_to.strip() or None,
        "experience_years": experience_years.strip() or None,
        "work_format": work_format or None,
```

Пустое значение остаётся очисткой optional поля; непустое передаётся в серверную схему и при ошибке возвращается HTML 400, сохранённый профиль не меняется.

#### `app/modules/candidates/web.py` — _parse_date / experience_add / skill_add

Неверная дата игнорировалась; новые навыки/опыт не получали общей валидации.

**Было:**

```python
    except ValueError:
        return None
```

**Стало:**

```python
    except ValueError:
        raise service.CandidateError("Дата должна быть в формате YYYY-MM-DD")
```

Навык и опыт вызывают проверяющий сервис; CandidateError показывает HTML-ошибку без сохранения. Добавлен Request для рендера, действия/методы/имена полей сохранены.

#### `app/modules/employers/schemas.py` — EmployerProfileUpdate / OfferCreate

company_name:null нарушал NOT NULL; пробельный title приглашения сохранялся пустым.

**Было:**

```python
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    industry: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)

```

**Стало:**

```python
    @field_validator('company_name', mode="before")
    @classmethod
    def _required_company(cls, value):
        if value is None or not value.strip():
            raise ValueError("Название компании не может быть пустым")
        return value.strip()

```

Явно пустое/null название компании — 422; title нормализуется и пробельное название отклоняется. Непереданное поле PATCH не изменяется.

#### `app/modules/employers/schemas.py` — OfferCreate._required_title

Пробельное название приглашения проходило min_length и превращалось в пустую строку после strip.

**Было:**

```python
    title: str = Field(min_length=1, max_length=255)
```

**Стало:**

```python
    @field_validator('title', mode="before")
    @classmethod
    def _required_title(cls, value):
        if not value.strip():
            raise ValueError("Название приглашения не может быть пустым")
        return value.strip()
```

Заголовок проверяется и нормализуется до обработки сервисом; новая операция приглашения не добавляется.

#### `app/modules/employers/service.py` — update_profile

HTML мог сохранить email, несовместимый с EmployerProfileRead.

**Было:**

```python
    for key, value in changes.items():
        setattr(profile, key, value)
    session.commit()
    session.refresh(profile)
    return profile

```

**Стало:**

```python
    try:
        changes = EmployerProfileUpdate.model_validate(changes).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise EmployerError("Проверьте название компании, email и длину полей") from exc
    for key, value in changes.items():
        setattr(profile, key, value)
```

Общая схема проверяет изменения до записи; существующий HTML catch EmployerError показывает ошибку 400, API продолжает отклонять неверное значение как 422.

#### `app/templates/candidates/profile.html` — числовые value

`or` скрывал допустимый 0; повторное сохранение превращало его в None.

**Было:**

```html
      <input type="number" name="desired_salary_from" min="0" value="{{ profile.desired_salary_from or '' }}">
```

**Стало:**

```html
      <input type="number" name="desired_salary_from" min="0" value="{{ profile.desired_salary_from if profile.desired_salary_from is not none else '' }}">
```

Исправлены desired_salary_from, desired_salary_to и experience_years: пустая строка только для None, ноль сохраняется при reload и повторном POST. Это реальные формы, не демо.

#### `tests/fixtures/working_form_contracts.json` — снимок числовых полей формы

Обновлён ожидаемый value для намеренного исправления нуля.

**Было:**

```json
{{ profile.desired_salary_from or '' }}",
```

**Стало:**

```json
{{ profile.desired_salary_from if profile.desired_salary_from is not none else '' }}",
```

Три исправленных Jinja-выражения отражены в fixture; методы, actions, имена и min/max не изменены. Браузер проверяет реальное значение 0, поэтому корректность не обосновывается одной строкой fixture.

#### `app/modules/assessments/seed/backend_junior.json` — sql_group_by.variables

Правильный COUNT отсутствовал среди вариантов UI.

**Было:**

```json
          "func": [{"value": "COUNT", "answer": "COUNT"}],
          "col": [{"value": "*", "answer": "COUNT"}],
          "group": [{"value": "role", "answer": "COUNT"}]
```

**Стало:**

```json
          "func": [{"value": "COUNT", "answer": "Количество пользователей в каждой роли"}],
          "col": [{"value": "*", "answer": "Количество пользователей в каждой роли"}],
          "group": [{"value": "role", "answer": "Количество пользователей в каждой роли"}]
```

Все три переменные одного вопроса теперь возвращают «Количество пользователей в каждой роли». Новые попытки можно правильно пройти через UI. Старые snapshot намеренно не переписаны; существующий банк требует отдельного seed_loader.

#### `app/modules/assessments/service.py` — _get_profile, start_attempt, submit_answer, finish_attempt

Одновременные старты/finish/ответ могли прочитать одно незавершённое состояние.

**Было:**

```python
def _get_profile(session: Session, user_id: int) -> CandidateProfile:
    profile = session.scalar(
        select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    )
```

**Стало:**

```python
def _get_profile(session: Session, user_id: int, *, lock: bool = False) -> CandidateProfile:
    query = select(CandidateProfile).where(CandidateProfile.user_id == user_id)
    profile = session.scalar(query.with_for_update() if lock else query)
    if profile is None:
```

В изменяющих операциях lock=True, PostgreSQL FOR UPDATE на профиле удерживается до конца транзакции. Старт создаёт одну попытку; двойной finish — один результат/current. Расчёт и thresholds не менялись.

#### `app/modules/assessments/service.py` — check_can_start_attempt

Провал делал current NOT_CONFIRMED и позволял обойти cooldown.

**Было:**

```python
        current = current_category(session, user_id=user_id)
        if current is not None and current.status == CategoryStatus.CONFIRMED:
            current_cat = session.get(Category, current.category_id)
            if current_cat is not None and current_cat.grade_id != target_grade.id:
```

**Стало:**

```python
        current = session.scalar(select(CandidateCategory).where(
            CandidateCategory.candidate_profile_id == profile.id,
            CandidateCategory.status == CategoryStatus.CONFIRMED,
        ).order_by(CandidateCategory.confirmed_at.desc().nullslast(), CandidateCategory.id.desc()))
        if current is not None:
            current_cat = session.get(Category, current.category_id)
```

Cooldown проверяет грейд последнего датированного подтверждения независимо от текущего статуса. Добавлен NULLS LAST: историческая запись без confirmed_at не перекрывает последнее известное подтверждение. Крайний случай отдельно воспроизведён на PostgreSQL (1 failed до NULLS LAST) и исправлен. Повтор того же грейда разрешён как прежде; другой грейд во время активного ограничения запрещён. Судьба текущей категории после провала не менялась.

#### `app/modules/assessments/service.py` — InvalidAnswer / submit_answer

API позволял сохранить пустой/непредложенный вариант, оба value/values или некорректный тип.

**Было:**

```python
    snapshot = answer.question_snapshot or {}
    answer.answer = answer_payload
    answer.is_correct = is_correct(snapshot, answer_payload)
    answer.answered_at = datetime.now(UTC)

    session.commit()
    session.refresh(answer)
    return answer

# --- Финиш попытки и подсчёт ----------------------------------------------


```

**Стало:**

```python
    snapshot = answer.question_snapshot or {}
    options = snapshot.get("options", [])
    if snapshot.get("type", "single_choice") == "multiple_choice":
        values = answer_payload.get("values")
        valid = (set(answer_payload) == {"values"} and isinstance(values, list)
                 and all(isinstance(value, str) and value in options for value in values)
                 and len(values) == len(set(values)))
    elif snapshot.get("type", "single_choice") == "single_choice":
        valid = set(answer_payload) == {"value"} and answer_payload.get("value") in options
    else:
        valid = set(answer_payload) == {"value"} and isinstance(answer_payload.get("value"), str)
    if not valid:
```

Для single/multiple choice проверяются допустимые варианты и форма payload; multiple не принимает дубликаты. Для text/code сохранён строковый payload без требования options. Нарушение — 400 до записи; finished попытка — 409.

#### `app/templates/assessments/result.html` — текст повторного прохождения

Сообщение обещало, что проваленная попытка не учитывается.

**Было:**

```html
      Вы можете попробовать снова — попытка не сгорает.
```

**Стало:**

```html
      Повторное прохождение доступно с учётом лимита попыток.
```

UI больше не противоречит лимиту провалов. Формула расчёта не изменена.

#### `app/start.py` — main

Свежий Compose получал справочники, но пустой банк вопросов.

**Было:**

```python
    print("Alembic migrations applied; starting Uvicorn", flush=True)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=get_settings().reload)

if __name__ == "__main__":
    main()
```

**Стало:**

```python
    # Bootstrap only an empty question bank; never overwrite edited questions on restart.
    with SessionLocal() as session:
        if session.scalar(select(Question.id).limit(1)) is None:
            load_all_seeds(session)
    print("Alembic migrations applied; starting Uvicorn", flush=True)
```

После миграций пустой банк загружается из seed; при наличии хотя бы одного вопроса автоматическая перезапись не выполняется. Проверено: 101 вопрос после fresh startup, повторный startup сохраняет ручное изменение difficulty.

#### `app/scripts/grant_category.py` — grant

Тестовый helper мог конкурировать с присвоением current в assessments.

**Было:**

```python
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
```

**Стало:**

```python
            select(CandidateProfile).where(CandidateProfile.user_id == user.id).with_for_update()
```

Helper использует тот же профильный FOR UPDATE перед заменой current; назначение категории из UI/API не заменяется этим тестовым инструментом.

#### `migrations/versions/c91d2048a630_answered_at_without_default.py` — upgrade / downgrade (только определение)

Миграционный default answered_at=now() расходился с nullable ORM.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def upgrade():
    op.alter_column("test_answers", "answered_at", server_default=None,
                    existing_type=sa.DateTime(timezone=True), existing_nullable=True)


def downgrade():
    op.alter_column("test_answers", "answered_at", server_default=sa.text("now()"),
                    existing_type=sa.DateTime(timezone=True), existing_nullable=True)
```

Новая последовательная ревизия снимает default, не меняя существующие даты/ответы. Старые уже применённые ревизии не переписаны. downgrade определён для полноты файла, но не выполнялся.

#### `app/modules/candidates/schemas.py` — FspAchievementImport

Внешние dict не проверялись перед записью; неверные даты терялись, неверные числа/длины приводили к DB errors.

**Было:**

Класс FspAchievementImport отсутствовал. Существовала схема чтения:

```python
class FspAchievementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_achievement_id: str
    title: str
```

**Стало:**

```python
class FspAchievementImport(BaseModel):
    """Validate the demo registry contract before any database changes."""
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=255)
    participant_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    discipline_code: str | None = Field(None, max_length=100)
    competition_name: str | None = Field(None, max_length=255)
    competition_date: date | None = None
    place: int | None = None
    rank: str | None = Field(None, max_length=100)
    team_name: str | None = Field(None, max_length=255)
    is_team: bool = False
```

В существующий файл добавлена схема локального mock-контракта: IDs/строки ограничены моделью, дата/число/bool проверяются. Это не новый официальный FSP API.

#### `app/modules/candidates/service.py` — link_and_import_fsp / FspRegistryInvalid

Чужой participant_id достижения фактически не проверялся.

**Было:**

```python
    # Проверим, что participant_id в ответе совпадает с запрошенным.
    # Это защита от подмены ответа.
    response_id = str(profile_data.get("id") or "").strip()
    if response_id != participant_id:
        raise FspParticipantNotFound(
            f"Реестр вернул участника {response_id!r} вместо {participant_id!r}"
        )

    # Проверим, что участник не привязан к другому профилю
```

**Стало:**

```python
    # Validate every achievement before changing a link or flushing any rows.
    try:
        achievements_data = [FspAchievementImport.model_validate(item).model_dump() for item in achievements_data]
    except (ValidationError, TypeError) as exc:
        raise FspRegistryInvalid("Некорректные данные реестра ФСП") from exc
    for item in achievements_data:
        if not isinstance(item, dict) or item.get('participant_id') != participant_id:
            raise FspParticipantNotFound("Реестр вернул достижение другого участника")

```

Весь пакет валидируется до создания/смены link и upsert. Любое чужое достижение отклоняет импорт; malformed пакет даёт FspRegistryInvalid. Дополнительно проверяется тип profile_data и равенство id.

#### `app/modules/candidates/service.py` — link_and_import_fsp / unlink_fsp

Повторные/конкурентные импорты и привязки могли давать неуправляемый IntegrityError.

**Было:**

```python
    created, updated = _upsert_achievements(
        session,
        candidate_profile_id=profile.id,
        achievements_data=achievements_data,
    )

    session.commit()
    session.refresh(link)
```

**Стало:**

```python
    try:
        created, updated = _upsert_achievements(
            session, candidate_profile_id=profile.id, achievements_data=achievements_data,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise FspParticipantNotFound("Участник уже привязан или импорт конфликтует с другим запросом") from exc
    session.refresh(link)
```

Import/unlink блокируют профиль; try покрывает autoflush внутри upsert и commit. Конфликт откатывается и превращается в понятную ошибку; старый link не оставляется частично обновлённым.

#### `app/modules/candidates/fsp_router.py` — _handle / list_available_participants / link_fsp

HTTP error списка и malformed JSON не имели контролируемого ответа.

**Было:**

```python
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис ФСП временно недоступен",
        ) from exc
```

**Стало:**

```python
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Некорректные данные реестра ФСП") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail="Ошибка реестра ФСП") from exc
    except httpx.RequestError as exc:
```

Сбой транспорта — 503; HTTP/JSON/контракт реестра — 502; неизвестный участник link — 404, конфликт — 409. Проверка списка находится внутри try.

#### `app/modules/candidates/web.py` — fsp_link

Malformed JSON/контракт также должен показываться через HTML.

**Было:**

```python
    except httpx.RequestError:
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(
            request,
            user,
```

**Стало:**

```python
    except (ValueError, TypeError):
        profile = service.get_profile_by_user_id(session, user.id)
        return _render_profile(request, user, profile, session,
            fsp_error="Некорректные данные реестра ФСП", status_code=502)
    except httpx.RequestError:
```

HTML возвращает страницу профиля с ошибкой 502, не необработанное исключение. Существующая Form и маршруты привязки/отвязки сохранены.

#### `app/modules/employers/service.py` — mark_offer_viewed / respond_to_offer

Параллельные решения/просмотр могли перезаписать конечный статус.

**Было:**

```python
            Offer.candidate_profile_id == profile.id,
```

**Стало:**

```python
        ).with_for_update().execution_options(populate_existing=True)
```

FOR UPDATE + populate_existing перед проверкой статуса: второй ответ получает InvalidStatusTransition, viewed не откатывает accepted/rejected. Допустимые переходы сохранены.

#### `app/modules/employers/service.py` — _candidate_brief

ФИО в DTO предложения могло содержать контакты даже до принятия.

**Было:**

```python
full_name=profile.full_name
```

**Стало:**

```python
full_name=public_text(profile.full_name)
```

Применена существующая маска matching к обоим путям brief; структурные contacts по-прежнему открываются только accepted. При нескольких current brief выбирает максимальный ID как assessments и matching; это детерминированность чтения, не исправление старых данных.

#### `app/modules/matching/web.py` — search: ValidationError

Обычная форма получала JSON 422, HTMX не показывал ошибку.

**Было:**

```python
    except ValidationError as exc:
        raise HTTPException(422, 'Некорректные фильтры или параметры страницы') from exc
    result = service.search_candidates(session, filters)
    def page_url(page):
        url = request.url.include_query_params(page=page)
        return url.path + '?' + url.query
    context = dict(user=user, filters=filters, result=result, page_url=page_url,
                   **service.reference_filters(session))
    partial = request.headers.get('hx-request') == 'true' and request.headers.get('hx-history-restore-request') != 'true'
```

**Стало:**

```python
    except ValidationError:
        message = 'Некорректные фильтры или параметры страницы. Проверьте количество навыков и размер страницы (1–50).'
        if request.headers.get('hx-request') == 'true':
            # HTMX swaps successful responses; keep the error visible inside its target.
            response = HTMLResponse('<section id="matching-results" role="alert" class="alert alert-error">' + message + '</section>')
        else:
            response = templates.TemplateResponse(request=request, name='matching/invalid_filters.html',
                context={'user': user, 'error': message}, status_code=422)
        response.headers['Cache-Control'] = 'no-store'
```

Обычный запрос — HTML 422; HTMX — успешный HTML-фрагмент с role=alert, который HTMX заменяет в #matching-results. Ошибка не выдаётся за результаты поиска; API остаётся 422.

#### `app/templates/matching/invalid_filters.html` — страница ошибки поиска

Нужна HTML-ошибка с возвратом к поиску.

**Было:**

Файл отсутствовал.

**Стало:**

```html
{% extends 'base.html' %}
{% block content %}<h1>Поиск кандидатов</h1><div role="alert" class="alert alert-error">{{ error }}</div><a class="button" href="/employer/search">Вернуться к поиску</a>{% endblock %}
```

Выводится сообщение и ссылка; сырые введённые данные не вставляются в HTML.

#### `tests/integration/test_assessments_api.py` — _answer_all

Тест подставлял скрытый correct, скрывая отсутствие правильного варианта в UI.

**Было:**

```python
            payload = {"value": snap["correct"]} if correct else {"value": "__wrong__"}
            r = client.post(
                f"/api/v1/assessments/attempts/{attempt_id}/answers/{q['answer_id']}",
```

**Стало:**

```python
            assert snap["correct"] in snap["options"]
            payload = {"value": snap["correct"] if correct else next(value for value in snap["options"] if value != snap["correct"])}
            r = client.post(
```

Сначала проверяется принадлежность correct к options; неверный ответ выбирается из реальных неправильных вариантов. На исходном банке прогон обнаружил COUNT — тест перестал давать ложную уверенность.

#### `tests/integration/test_matching_service.py` — _make_candidate

Новая общая валидация профиля больше не изменяет поле публикации вне своей схемы.

**Было:**

```python
    update_profile(session, user_id=user.id, changes={"is_searchable": True})
```

**Стало:**

```python
    set_publication(session, user.id, True)
```

Fixture явно публикует профиль через правильный сервис; проверка поиска снова использует допустимое состояние. Продуктовая публикация не добавлялась заново.

#### `tests/matching/conftest.py` — database: SQLite schema

Реальная страница профиля обращается к таблице FSP link; старая search fixture её не создавала.

**Было:**

```python
        for model in [User,CandidateProfile,CandidateSkill,CandidateExperience,FspAchievement,Specialization,Grade,Category,CandidateCategory,TestAttempt]:
```

**Стало:**

```python
        for model in [User,CandidateProfile,CandidateSkill,CandidateExperience,FspAchievement,FspRegistryLink,Specialization,Grade,Category,CandidateCategory,TestAttempt]:
```

SQLite создаёт также FspRegistryLink, без mock сервисов/рабочей БД. Это устранение дефекта фикстуры; PostgreSQL создаёт полную metadata как прежде.

#### `tests/matching/test_migrations.py` — fresh/filled migrations; startup; metadata; diagnostic

Нужны проверки нового head, default, fresh bootstrap и старого блокера.

**Было:**

```python
        assert conn.scalar(text('SELECT version_num FROM alembic_version'))=='75c8b36a9021'
        column=conn.execute(text("SELECT is_nullable, column_default FROM information_schema.columns WHERE table_name='candidate_profiles' AND column_name='is_searchable'")).one()
        assert column.is_nullable=='NO' and 'false' in column.column_default
```

**Стало:**

```python
        assert conn.scalar(text('SELECT version_num FROM alembic_version'))=='c91d2048a630'
        assert conn.scalar(text("SELECT column_default FROM information_schema.columns WHERE table_name='test_answers' AND column_name='answered_at'")) is None
        column=conn.execute(text("SELECT is_nullable, column_default FROM information_schema.columns WHERE table_name='candidate_profiles' AND column_name='is_searchable'")).one()
```

Ожидается c91d2048a630; добавлены проверки отсутствия default, полного совпадения schema/ORM, сохранения данных, bootstrap/restart и явный diagnostic отказа legacy migration. Последний не считается исправленным переносом.

#### `tests/conftest.py` — isolated_external_stack

Предыдущие integration/E2E могли писать в SessionLocal любого приложения.

**Было:**

Файл отсутствовал.

**Стало:**

```python
    project = os.getenv("TEST_COMPOSE_PROJECT", "")
    if not project.startswith("fsp-matching-check-"):
        pytest.fail("Writing checks require an explicit isolated TEST_COMPOSE_PROJECT")
    url = make_url(os.getenv("DATABASE_URL", ""))
    if url.get_backend_name() != "postgresql" or url.database != "fsp_matching_test":
        pytest.fail("Writing checks require DATABASE_URL pointing to fsp_matching_test")
```

Запуск с записью требует test DB name, отдельный Compose project и совпадающие опубликованные app/db порты; readonly локальные тесты с dependency override работают отдельно.

#### `tests/backend/test_review_seed.py` — test_all_seed_variations_have_selectable_correct_answers

Регрессия недоступного правильного ответа.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_all_seed_variations_have_selectable_correct_answers():
    for path in Path("app/modules/assessments/seed").glob("*.json"):
        for item in json.loads(path.read_text(encoding="utf-8"))["questions"]:
            question = SimpleNamespace(id=1, topic=item.get("topic"), difficulty=item["difficulty"],
                                       type=QuestionType(item["type"]), payload=item["payload"], correct_answer=item.get("correct_answer"))
            for seed in range(100):
```

Каждый seed и 100 вариаций проверяются по options; проверка на старом seed действительно падает.

#### `tests/matching/test_review_regressions.py` — HTTP/schema/HTML regressions

Проверки реального отклонения и неизменности сохранённого состояния.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_salary_partial_patch_checks_stored_other_bound(client, candidate_headers):
    endpoint = "/api/v1/candidates/me"
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_from": 100, "desired_salary_to": 200}).status_code == 200
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_from": 300}).status_code == 400
    assert client.get(endpoint, headers=candidate_headers).json()["desired_salary_from"] == 100
    assert client.patch(endpoint, headers=candidate_headers, json={"desired_salary_to": None}).status_code == 200
```

Добавлены next, null/пробелы, зарплата PATCH/очистка, HTML числа/даты, опыт PATCH, конфликт навыка/rollback, invalid registration до записи, employer email, HTML/HTMX ошибка поиска. На исходном коде эти регрессии находят дефекты.

#### `tests/matching/test_review_postgres.py` — PostgreSQL concurrency / privacy regressions

Проверка блокировок в настоящем PostgreSQL, а не SQLite.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_parallel_starts_return_same_attempt(database, question_pool):
    engine, data = database; barrier = threading.Barrier(2)
    def start(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return assessments.start_attempt(session, user_id=data['candidate'].id, specialization_code='backend', grade_code='middle').id
```

Проверяются один старт/finish, cooldown после провала, immutable finished answer, отсутствие записи invalid answer/чужого или malformed достижения, одно конечное решение приглашения, одно потребление token, маска контактов в pending offer.

#### `tests/matching/test_review_browser.py` — test_profile_save_validation_and_resume_test

Сохранение и реальное прохождение вместо подменённых HTML fixtures.

**Было:**

Файл отсутствовал.

**Стало:**

```python
def test_profile_save_validation_and_resume_test(page,matching_server,database,width):
    engine,data=database
    with Session(engine) as session:
        for index in range(10):
            session.add(Question(specialization_id=data['category'].specialization_id,grade_id=data['category'].grade_id,type=QuestionType.SINGLE_CHOICE,difficulty=1,payload={'text':f'Browser question {index}','options':['Yes','No']},correct_answer={'value':'Yes'}))
        session.commit()
```

Desktop 1440 и mobile 390: реальная форма сохраняет 0, плохой опыт 81 отклоняется, тест продолжается со второго вопроса и завершается 100%, reload сохраняет данные; нет JS ошибок/горизонтального переполнения. Снимки вне репозитория.


#### `tests/integration/test_services.py` — test_integration_clients

Общий прогон после Playwright обнаружил ошибку теста: asyncio.run нельзя вызвать на потоке с уже работающим event loop. Отдельный integration-прогон этого не обнаруживал.

**Было:**

```python
    asyncio.run(run())
```

**Стало:**

```python
    # Playwright may keep an event loop running on the pytest main thread.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, run()).result(timeout=20)
```

Реальные асинхронные HTTP-проверки выполняются в отдельном потоке со своим loop; исключения возвращаются через result, а не скрываются. Установлен timeout. Продуктовый async-код не изменён. Перед исправлением объединённый прогон дал 350 passed, 2 skipped, 1 failed именно на этом тесте; это не объявляется успешным общим прогоном.

### 4. Результаты проверок и порядок оставшейся работы

| Набор | Результат | Что подтверждает |
| --- | --- | --- |
| `tests/backend` | 115 passed | Схемы, auth/security, шаблоны/контракты, mock/адаптеры; новый seed-regression |
| `tests/matching` на отдельном PostgreSQL | 100 passed | Поиск/права/приватность/ANY–ALL, реальные HTML/API и browser, профили, concurrency, ФСП, startup и миграции. **Включает один diagnostic ожидаемого отказа legacy upgrade** |
| `tests/integration` через тестовый Docker app/db/mock/mailpit | 116 passed | Реальный HTTP, SMTP-инфраструктура, запись/чтение профиля, цикл теста, поиск и статусы предложений |
| `tests/e2e` через тестовый Docker app | 21 passed, 2 skipped | Навигация, auth, HTML/HTMX, design-preview, рабочий поиск; два старых UI-сценария отправки/ответа приглашения отключены до подключения формы |

Пропущены: `tests.e2e.test_matching_flow.test_full_matching_flow[chromium]`, `tests.e2e.test_matching_flow.test_reject_flow_hides_contacts[chromium]`. Причина — явный `RUN_OFFER_E2E` guard: форма этапа 7 в новой карточке пока не подключена. API статусов/прав/контактов проверен, его успешность не заменяет недоступный UI-сценарий.

Предупреждение одно: Starlette deprecation об HTTPX/TestClient. Это предупреждение зависимости, не ошибка тестов; зависимости не менялись ради него.

Браузерные проверки включают desktop/mobile: поиск 1440/390/320 px, сохранение профиля и прохождение/продолжение теста 1440/390 px, отсутствие JS-ошибок и горизонтального переполнения, reload и HTMX-навигацию. Реальные снимки: `C:/Users/dfkol/AppData/Local/Temp/fsp-review-screenshots/profile-review-1440.png`, `profile-review-390.png`, `assessment-review-1440.png`, `assessment-review-390.png`, `search-1440.png`, `candidate-390.png`; остальные визуальные снимки в той же папке включают явно демонстрационные экраны и template fixtures.

Тестовое приложение оставлено запущенным: **http://127.0.0.1:62910/**; реальные маршруты `/auth/login`, `/candidate/profile`, `/assessments`, `/employer/profile`, `/employer/search`, `/employer/candidates/{id}`. Кабинеты требуют соответствующей роли; детали поиска требуют опубликованного профиля с подтверждённой категорией. `/design-preview` остаётся отдельным прототипом. Динамический порт может измениться при следующем recreation/restart; получать через `docker compose -f compose.test.yaml -p fsp-matching-check-20261009 port app 8000`.

Свежая и заполненная поддерживаемая схема обновлены на **c91d2048a630**, повторный upgrade безопасен. `compare_metadata` с `compare_server_default=True` не нашёл расхождений с ORM. Fresh startup создал 101 вопрос, повторный сохранил ручное изменение. Старый snapshot upgrade с заполненными ответами воспроизводимо отказал без потери данных; он всё ещё требует согласованного решения. Для уже существующего тестового банка отдельно запускался `python -m app.modules.assessments.seed_loader`: 0 создано, 101 обновлён; существующие snapshots не переписывались. Этот запуск был только в тестовом Compose, не в рабочей БД.

Команда общего прогона (из окружения с проверенными адресами отдельного тестового стека):

```powershell
# RUN_INTEGRATION=1, RUN_E2E=1; TEST_COMPOSE_PROJECT=fsp-matching-check-20261009.
# DATABASE_URL и MATCHING_TEST_DATABASE_URL — отдельная fsp_matching_test.
# APP_BASE_URL/FSP_BASE_URL/MAILPIT_BASE_URL/SMTP — порты именно этого Compose.
python -m pytest tests/backend tests/matching tests/integration tests/e2e -q -p no:cacheprovider --tb=short --junitxml="$env:TEMP/fsp-review-final.xml"
```

JUnit: Изменены 22 существующих файлов, добавлены 8, включая этот журнал.

Дополнительно: 115 Python-файлов разобраны AST без создания pyc, `git diff --check` успешен, все цитаты разделов 2–3 автоматически сверены с заявленными исходниками. README/исходное ядро поиска/предшествующий дизайн сохранены относительно исходного снимка. Ветка и HEAD остаются `dev/cheykdop` / `924f869`.


Рабочий Compose не запускался и не изменялся. Все операции с записью выполнялись в `fsp-matching-check-20261009` / `fsp_matching_test` либо в отдельных созданных тестами БД `fsp_matching_case_*`, `fsp_matching_migration_*`. После тестов удалялись только эти новые временные БД, не рабочие данные/volumes. `downgrade` не выполнялся. Секреты не выводились; снимок и цитаты их не содержат.

- [ ] Определить перенос legacy snapshot. Готовность: upgrade с заполненной старой схемы сохраняет ответы и достоверную историю.
  - [ ] Согласовать судьбу исходных параметров и незавершённых попыток; затем исправить путь миграции `migrations/versions/88945e7ea258_add_question_snapshot_to_test_answers.py` и соответствующий diagnostic в `tests/matching/test_migrations.py`.
  - [ ] Отдельно проверить переход с удалённой `0001_initial` на копии старой БД; не применять guessed migration к рабочей БД.
- [ ] Согласовать правила auth и тестирования. Готовность: README, сервис и UI описывают одно поведение.
  - [ ] Уточнить обязательность email, сохранение согласия и правила повторного подтверждения/провала/параллельных категорий — `app/modules/auth/`, `app/modules/assessments/service.py`, `app/templates/assessments/`, `tests/integration/test_assessments_api.py`.
  - [ ] Исправить выбранные правила отдельной задачей и добавить пользовательские сценарии; выполненные проверки сохранения/расчёта повторно не считать недоделкой.
- [ ] Завершить согласованный демо-контракт командных достижений. Готовность: чужое участие в другой команде/соревновании не даёт достижения.
  - [ ] Добавить требуемые связи в `mock_fsp/schemas.py`, `mock_fsp/data/`, `mock_fsp/main.py`; затем использовать их в `app/modules/candidates/service.py` и `app/integrations/fsp/`.
  - [ ] Добавить отрицательные проверки membership/competition в backend/integration и browser-проверку отметки демо; реальная идентификация ФСП не подразумевается.
- [ ] Подключить форму приглашения на следующем этапе. Готовность: опубликованный кандидат найден, реальные условия отправлены, решение сохранено, контакты раскрыты только после принятия.
  - [ ] Сначала согласовать доступ после отзыва публикации; связать `app/templates/matching/detail.html` с уже существующим `app/modules/employers/web.py:offer_create`.
  - [ ] Актуализировать `tests/e2e/test_matching_flow.py`, включить две пропущенные проверки и проверить отказ/повторный ответ. API и блокировки статусов уже реализованы и проверены.
- [ ] Привести документы к одному проверенному снимку. Готовность: нет конфликтов, неверных состояний и небезопасных инструкций тестирования.
  - [ ] С участником, редактирующим README, выбрать актуальную структуру `README.md`/`New_README.md`; обновить `docs/architecture.md` и `docs/fsp-integration.md`, исправить ссылку на отсутствующий `docs/testing.md`.
  - [ ] Добавить указание отдельного Compose и guarded test environment; старые команды integration по умолчанию направлены на SessionLocal приложения.

Новые функции вне MVP и масштабный рефакторинг не добавлены. Неиспользуемые старые search-шаблоны и `matching/ranking.py` оставлены для отдельной согласованной уборки, не выдаются за работающий маршрут.
