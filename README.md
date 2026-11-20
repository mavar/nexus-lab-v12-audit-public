# NEXUS LAB V12 — открытый комплект независимой проверки

Владелец разрешил эту отдельную публичную копию. Основной репозиторий дашборда остаётся закрытым. Здесь нет его Git-истории, токенов и рабочего local-config. Автоматического срока закрытия у этой копии нет.

## Начать с нужного документа

- [Промпт для независимого ИИ-чата](CHATGPT_HANDOFF_PROMPT.md).
- [Короткий результат аудита](audit/AUDIT_SUMMARY_RU.md).
- [Все 10 завершённых опытов](audit/COMPLETED_RUN_REVIEW.md).
- [Настоящий повтор ошибки старых оценок](CACHE_PROOF.md).
- [Разные условия обучения и риски](audit/COMPARISON_CONDITIONS.md).
- [16 задач разработчику, JSON](audit/AUDIT_TASKS.json).
- [Данные: как читать, качество, разметка](DATASET_README.md).
- [Восстановление дашборда в другом чате](DASHBOARD_HANDOFF_PROMPT.md).

Исходники V12 лежат в v12_source. Исходники отдельного сайта — в dashboard_source, снимок 9515e54. Не считать их одним уже объединённым приложением. Старые отчёты владельца: [автономный HTML](v12_completed_report/NEXUS_DASHBOARD.html), [ZIP итогов](v12_completed_report/NEXUS_V12_REPORT.zip). HTML нужно скачать и открыть в браузере, а не читать его исходник как обычный отчёт.

## Готовые рыночные файлы

| Инструмент | Реальный минутный CSV, менее 7MB каждый | Короткий пример |
|---|---|---|
| SOLUSDT | [CSV](data/crypto_1m/SOLUSDT_1m.csv) | [JSON](data/crypto_1m/SOLUSDT_example.json) |
| BTCUSDT | [CSV](data/crypto_1m/BTCUSDT_1m.csv) | [JSON](data/crypto_1m/BTCUSDT_example.json) |
| ETHUSDT | [CSV](data/crypto_1m/ETHUSDT_1m.csv) | [JSON](data/crypto_1m/ETHUSDT_example.json) |
| XRPUSDT | [CSV](data/crypto_1m/XRPUSDT_1m.csv) | [JSON](data/crypto_1m/XRPUSDT_example.json) |
| DOGEUSDT | [CSV](data/crypto_1m/DOGEUSDT_1m.csv) | [JSON](data/crypto_1m/DOGEUSDT_example.json) |

40320 строк календаря на пару, 3–30 июня 2026UTC. Примерно 26430 минут имеют наблюдавшиеся сделки. Пустоты отмечены и не заполнены. Это спот, не фьючерсы. Дневные таблицы качества и хэши рядом. Готовые 26-признаковые таблицы для 1/5/10/15/30 минут — [data/prepared_crypto](data/prepared_crypto). Finam/SBRF — [v12_source/prepared](v12_source/prepared).

Данные можно сократить до дня для отладки. По одному дню нельзя доказывать переносимость сигнала. Все опубликованные CHECK уже просмотрены; после изменения метода требуется новый закрытый финальный период. Движение цены 0.25% до расходов не означает чистую прибыль 0.25%.

## Скачать одним файлом

- [Обновлённый аудит, код, данные пяти пар и SBRF](https://github.com/mavar/nexus-lab-v12-audit-public/releases/download/review-2026-11-19-v2/NEXUS_V12_AUDIT_FULL_v2.zip).
- [Реальные тики SOL за две недели для сайта](https://github.com/mavar/nexus-lab-v12-audit-public/releases/download/review-2026-11-19-v2/SOLUSDT_two_weeks_ticks_20260614_27.zip).
- [Один день пяти пар, маленький пример](https://github.com/mavar/nexus-lab-v12-audit-public/releases/download/review-2026-11-19-v2/CRYPTO_FIVE_PAIRS_ONE_DAY.zip).

Можно также клонировать репозиторий без авторизации:

```sh
git clone https://github.com/mavar/nexus-lab-v12-audit-public.git
cd nexus-lab-v12-audit-public
```

## Проверка исследовательского формата

Нужны Python3.12, numpy, pandas, scikit-learn и PyTorch. Фактически проверены torch2.14.1+cu126, numpy2.2.3, pandas2.3.3, sklearn1.8.0. Точное окружение — audit/AUDIT_TEST_RESULTS.md. Новый независимый install этих версий в рамках обновления не выполнялся; использовалось существующее проверенное окружение.

```sh
python -m venv .venv
# Activate .venv for your operating system before installing.
python -m pip install -r requirements-research.txt
# Pick a CPU or CUDA torch build using https://pytorch.org/get-started/locally/
python -m pip install torch
python tools/smoke_multi_market.py --crypto data/prepared_crypto --sbrf v12_source/prepared/SBRF_1m_research.csv.gz --output local_checks/multi_market.json
python tools/verify_cache_definitively.py
```

Обычная техническая проверка шести инструментов — примерно 1–3 минуты после установки на машине владельца, 3 эпохи, не полный поиск. Читай цель/ограничения в JSON: это не доказательство хорошей торговли. Видеокарта для неё не обязательна.

Не запускай исходный START.py с криптой без адаптации: даты и имя SBRF зашиты, score имеет фиксированную границу августа. Подтверждённая задача 016. Для старого SBRF технический smoke:

```sh
python v12_source/START.py --smoke --cpu
```

Публичные исходники и таблицы имеют назначение проверки. Нет live-торговли, ключей и автоматической отправки результатов владельцу. Если среда ИИ не умеет скачивать файлы или исполнять код, она должна сообщить это и попросить приложить открытый ZIP, а не выдумывать выполненные тесты.
