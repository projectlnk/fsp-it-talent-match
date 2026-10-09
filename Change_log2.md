# Пункт 7 — предложения работодателя и ответы кандидата

Дата: 10.10.2026.

- [x] Пункт 7: карточка кандидата → отправка предложения → исходящие работодателя → входящие кандидата → принятие или отказ.

## Что уже было

В проекте существовали модель `Offer`, схемы, сервис создания и обработки предложений, API, HTML-обработчики, списки и страницы ответов кандидата. Контакты уже раскрывались только работодателю, отправившему принятое предложение. Это существующая реализация команды; новый механизм приглашений не создавался.

В новой карточке `app/templates/matching/detail.html` кнопка была отключена. HTML-обработчик терял введённые поля при ошибке. Сервис разрешал новые предложения скрытым кандидатам, а повтор любого окончательного ответа возвращал конфликт.

## Что изменено

### 1. Форма в новой карточке

Файл: `app/templates/matching/detail.html`.

Было:

```html
<button type="button" disabled title="Подключение на этапе 7">Пригласить</button>
```

Стало:

```html
<form method="post" action="/employer/offers" class="form" id="offer-form">
  <input type="hidden" name="candidate_profile_id" value="{{ card.profile_id }}">
```

Форма использует существующий POST. В ней есть заголовок, описание, зарплата от–до в рублях, отметка «До вычета НДФЛ» и способ связи работодателя. Зарплата не подставляется автоматически. Стили используются существующие.

### 2. Ошибки формы и сохранение ввода

Файл: `app/modules/employers/web.py`, функция `offer_create`.

Было:

```python
salary_from: int = Form(...),
salary_to: int = Form(...),
```

Стало:

```python
salary_from: str = Form(""),
salary_to: str = Form(""),
```

Числа проверяет существующая схема `OfferCreate`. Раньше отсутствующие или не приводимые к целому значения отклонялись FastAPI до входа в обработчик с JSON-ошибкой 422. Отрицательные суммы и неверный диапазон уже отклонялись схемой внутри обработчика и возвращали HTML, но введённые поля терялись. Теперь пустые, отрицательные, нечисловые значения и числа с ненулевой дробной частью обрабатываются внутри `offer_create`: возвращается HTML с ошибкой и кодом 400.

Было:

```python
{"card": card, "error": str(exc)},
```

Стало:

```python
{"card": card, "error": error, "offer_form": form},
```

В шаблоне сохранённые значения берутся из `offer_form`, например:

```jinja2
{{ f.get('salary_from', '') }}
```

При ошибке сервер передаёт обратно заголовок, описание, обе суммы, способ связи и состояние галочки НДФЛ. Браузерный сценарий подтвердил сохранение корректно записанных чисел при ошибочном диапазоне. Нечисловая строка передаётся в атрибут `value`, но поле HTML `type="number"` может показывать её пустой; визуальное сохранение такого ввода не гарантируется. Блок ошибки получил `role="alert"`.

### 3. Запрет новых приглашений скрытым кандидатам

Файл: `app/modules/employers/service.py`, функция `create_offer`.

Было:

```python
candidate = session.get(CandidateProfile, payload.candidate_profile_id)
if candidate is None:
    raise CandidateNotFound("Кандидат не найден")
```

Стало:

```python
candidate = session.scalar(
    select(CandidateProfile)
    .where(CandidateProfile.id == payload.candidate_profile_id)
    .with_for_update().execution_options(populate_existing=True)
)
from app.modules.auth.models import User, UserRole
candidate_user = session.get(User, candidate.user_id) if candidate else None
if (candidate is None or not candidate.is_searchable or candidate_user is None
        or not candidate_user.is_active or candidate_user.role != UserRole.CANDIDATE):
    raise CandidateNotFound("Кандидат не найден")
```

Проверка находится в общем сервисе: её нельзя обойти прямым HTML POST или JSON API. Новое предложение доступно только опубликованному активному кандидату. Скрытый профиль не раскрывается через сообщение ошибки.

Создание предложения читает профиль с блокировкой:

```python
.with_for_update().execution_options(populate_existing=True)
```

В `app/modules/matching/service.py`, функции `set_publication`, чтение также изменено.

Было:

```python
profile = session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
```

Стало:

```python
profile = session.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id)
                         .with_for_update().execution_options(populate_existing=True))
```

На PostgreSQL обе операции блокируют одну строку профиля. Это обеспечивает последовательность отправки и отзыва публикации; отдельный конкурентный тест именно этой пары операций не запускался. Последовательный случай «отзыв завершён → новая отправка» проверен тестами.

**Правило:** отзыв публикации запрещает новые приглашения, но не отменяет уже отправленные. Участники по-прежнему могут открыть старое предложение и ответить на него. Правило записано в `docs/matching.md`.

### 4. Повтор ответа

Файл: `app/modules/employers/service.py`, функция `respond_to_offer`.

Было:

```python
if offer.status in {OfferStatus.ACCEPTED, OfferStatus.REJECTED}:
    raise InvalidStatusTransition("Приглашение уже обработано")
```

Стало:

```python
if offer.status in {OfferStatus.ACCEPTED, OfferStatus.REJECTED}:
    if offer.status.value == decision:
        return _to_offer_read(session, offer, reveal_contacts=False)
    raise InvalidStatusTransition("Приглашение уже обработано")
```

Повторное принятие принятого предложения или отказ от отклонённого возвращает сохранённый статус. Дата ответа не меняется. Противоположный ответ не меняет конечный статус: JSON API возвращает 409, существующий HTML-обработчик перенаправляет на страницу с актуальным состоянием. Существующая блокировка строки предложения сохранена.

Перед этим фрагментом выполняется существующая проверка получателя:

```python
offer = session.scalar(
    select(Offer).where(
        Offer.id == offer_id,
        Offer.candidate_profile_id == profile.id,
    ).with_for_update().execution_options(populate_existing=True)
)
if offer is None:
    raise OfferNotFound("Приглашение не найдено")
```

`profile` выбирается по `candidate_user_id`, который маршруты берут из авторизованного пользователя. Поэтому чужой кандидат не доходит до возврата при одинаковом ответе.

### 5. Навигация и проверки

В `app/templates/components/sidebar.html` добавлены ссылки на реальные входящие кандидата и исходящие работодателя. Страницы списков и ответов используются существующие.

В `tests/integration/test_offers_service.py` и `tests/integration/test_offers_api.py` подготовка кандидата теперь явно включает публикацию через `set_publication`: тесты обычной отправки должны использовать опубликованный профиль.

В `tests/matching/test_browser.py` и `tests/e2e/test_matching_search.py` ожидание отключённой кнопки заменено ожиданием доступной кнопки.

Добавлен `tests/matching/test_offers_completion.py`:

- запрет новых предложений после отзыва публикации через JSON и HTML;
- просмотр и ответ на ранее отправленное предложение после отзыва;
- повтор одинакового ответа без изменения даты и запрет противоположного;
- раскрытие контактов после принятия и запрет просмотра другому работодателю;
- сохранение полей при неверной зарплате;
- один браузерный сценарий: ошибка формы → исправление → отправка → исходящие → входящие → принятие → контакты работодателю.

## Результаты проверок

Использовался существующий отдельный Compose-проект `fsp-matching-check-20261009` и PostgreSQL `fsp_matching_test`. Новые маршрутные и браузерные тесты создавали собственные временные БД через фикстуру `tests/matching/conftest.py`. Рабочая БД и её volumes не затрагивались.

Перед изменениями:

```powershell
python -m pytest tests/backend/test_offer_schemas.py tests/integration/test_offers_service.py tests/integration/test_offers_api.py -q -p no:cacheprovider
```

Результат: **33 passed**. Это исходное состояние, не проверка новых изменений.

После изменений:

```powershell
python -m pytest tests/backend/test_offer_schemas.py tests/integration/test_offers_service.py tests/matching/test_offers_completion.py tests/matching/test_review_postgres.py -k "offer or form_error" -q -p no:cacheprovider
```

Повтор только этих двух случаев:

```powershell
python -m pytest tests/matching/test_offers_completion.py -k revocation -q -p no:cacheprovider --tb=short
```

## Дополнительная проверка владельца и транзакции — 10.10.2026

Ранее были тесты чужого просмотра, но не отдельный тест чужого ответа. Добавлен один `test_foreign_candidate_cannot_answer_or_repeat` в `tests/matching/test_offers_completion.py`: другой кандидат получает 404 как до принятия, так и при попытке повторить уже принятое предложение. Статус и дата в БД остаются прежними; контакты в отказе не возвращаются.

```powershell
python -m pytest tests/matching/test_offers_completion.py::test_foreign_candidate_cannot_answer_or_repeat -q -p no:cacheprovider --tb=short
```

Итог: **1 passed** на отдельной PostgreSQL. Первый запуск выявил ошибку сравнения даты в самом тесте: `Z` и `+00:00` — разные строки одного времени. После сравнения значений `datetime` тест прошёл; бизнес-код не менялся.

В `create_offer` между чтением профиля с `FOR UPDATE` и `session.add(offer)` нет промежуточного `commit` или `rollback`, в том числе во вызываемых функциях. Следующий `session.commit()` записывает предложение и завершает транзакцию, освобождая блокировку. `session.refresh(offer)` выполняется после записи. В `set_publication` блокировка также удерживается до сохранения `is_searchable`. Сессия не настроена на autocommit; при исключении закрытие сессии отменяет незавершённую транзакцию. Это подтверждено анализом кода. Отдельный конкурентный тест отправки и отзыва публикации не проводился.
