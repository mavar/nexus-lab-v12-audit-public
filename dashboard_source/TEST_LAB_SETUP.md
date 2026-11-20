# Установка, запуск и восстановление

## На рабочем компьютере владельца

Двойной клик по `E:\Трейдинг\Nexus_MEXC_Hypothesis_Lab\research\dashboard_week\START_LAB.bat`. Откроется `http://127.0.0.1:8767/`. Обычный запуск занимает несколько секунд. После выключения компьютера запуск нужен снова.

## Из закрытого репозитория

Потребуются Python 3.12, Node.js 24 LTS, npm и Git. Установщики находятся на [python.org](https://www.python.org/downloads/), [nodejs.org](https://nodejs.org/en/download) и [git-scm.com](https://git-scm.com/downloads). При установке включите добавление команд в PATH.

Адрес репозитория — [mavar/nexus-mexc-label-dashboard](https://github.com/mavar/nexus-mexc-label-dashboard), ветка `main`. Нужен авторизованный доступ владельца. Команда `gh repo clone` использует уже настроенный доступ GitHub CLI. Другой способ — `git clone` через авторизованную среду.

```powershell
gh repo clone mavar/nexus-mexc-label-dashboard
Set-Location nexus-mexc-label-dashboard
.\SETUP_LAB.bat -Demo
.\START_LAB.bat
```

Первый запуск установки скачивает библиотеки Python в `.venv`, зависимости сайта через `npm ci`, создаёт демонстрационные данные, собирает сайт и выполняет проверки. Время зависит от сети, обычно несколько минут. На Windows скрипт вызывает `npm.cmd` и не требует менять глобальную политику PowerShell.

Без генерации демонстрации используйте `SETUP_LAB.bat`. Затем подключите свои данные и запустите `START_LAB.bat`. Повторная установка с `-Demo` сохраняет ранее выбранные реальные пути и завершится с понятной ошибкой, если текущий конфиг относится к другому набору. Сначала скопируйте свой конфиг в резервный файл вне репозитория и выберите нужный набор явно.

Демонстрация содержит семь искусственных суток и явно подписана на экране. Проверка её прогонов подтверждает работу интерфейса и расчёта. Для выводов о торговле подключите реальные записи. Данные и готовая сборка исключены из Git. В чистом клоне все необходимые демонстрационные записи создаёт `prepare_demo.py`.

## Реальные данные

В корне создайте `local-config.json`. Он исключён из Git и содержит только пути. Пример структуры:

```json
{
  "quoteRoot": "G:/mexc_base/exchange=MEXC/stream=book_ticker",
  "tradeRoot": "G:/mexc_base/exchange=MEXC/stream=trades",
  "labelHtml": "C:/work/nexus-mexc-label-dashboard/dist/review.html",
  "rulesPath": "C:/work/nexus-mexc-label-dashboard/lab_rules.json"
}
```

Для владельца используются первые два пути из примера. Сохранённый недельный HTML находится в `E:\YandexDisk\ИИ\Артефакты\Nexus_MEXC_Hypothesis_Lab\sol_label_week_dashboard\review.html`. При переносе страницы на другую машину исправьте `labelHtml`.

Внутри каждого потока должны лежать семь папок `symbol=SOLUSDT/date=2026-06-14` … `date=2026-06-20`, в каждой ровно один Parquet. Котировки имеют столбцы `recv_ts_ms`, `best_bid`, `best_ask`, `bid_qty`, `ask_qty`. Сделки — `recv_ts_ms`, `price`, `quantity`, `trade_time_ms`. Время в миллисекундах UTC, цены в USDT, количество в SOL. Наличие файла ещё не доказывает отсутствие пропусков.

Для обучения с окном объёма 0 нужны только котировки. Для положительного окна объёма нужны записи сделок. Чтобы получить вкладку разметки на своих котировках, соберите её:

```powershell
.venv\Scripts\python.exe -X utf8 build.py --root "G:/mexc_base/exchange=MEXC/stream=book_ticker" --pair SOLUSDT --start 2026-06-14 --output dist
```

Альтернатива конфигу — переменные `NEXUS_QUOTE_ROOT`, `NEXUS_TRADE_ROOT`, `NEXUS_LABEL_HTML`, `NEXUS_RULES_PATH`. Они имеют приоритет над файлом. Для совместимости можно задать `NEXUS_LAB_ROOT`, тогда правила по умолчанию читаются оттуда. Самостоятельный клон использует свой `lab_rules.json`. После смены путей перезапустите сервис, чтобы очистились старые кэши.

## Ручная установка и сборка

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-api.txt -c requirements-lock.txt
.venv\Scripts\python.exe -X utf8 prepare_demo.py
.venv\Scripts\python.exe -X utf8 -c "import json; from pathlib import Path; from lab_api import app; Path('web/openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False),encoding='utf-8')"
Set-Location web
npm.cmd ci
npx.cmd --no-install openapi-typescript openapi.json -o src/lib/api.d.ts
npm.cmd run build
Set-Location ..
.venv\Scripts\python.exe -X utf8 -m unittest test_learning test_timed
node test_engine.js
.\START_LAB.bat
```

Для реальных данных вместо `prepare_demo.py` создайте конфиг с путями.

На Linux или macOS та же ручная последовательность использует `python3.12 -m venv .venv`, затем `.venv/bin/python` вместо `.venv\Scripts\python.exe`, и `npm` вместо `npm.cmd`. Сервер запускается командой `.venv/bin/python -m uvicorn lab_api:app --host 127.0.0.1 --port 8767`. Автоматические BAT/PowerShell-скрипты рассчитаны на Windows. Полное восстановление этой поставки проверяется на Windows владельца.

## Если страница не открывается

1. Запустите `START_LAB.bat`. Старое окно браузера само сервер не включает.
2. Проверьте `http://127.0.0.1:8767/api/v1/health`. Поля `pageBuilt` и `labelPageAvailable` показывают наличие собранных страниц, `projectRoot` — какую копию открыли.
3. Выполните `.venv\Scripts\python.exe -X utf8 doctor.py`. Получите список библиотек, путей и файлов на каждый день.
4. Логи находятся в `%LOCALAPPDATA%\NexusLabelLab\lab-out.log` и `lab-error.log`. Если занята сеть 8767, выясните, какой процесс там работает. Запуск не выключает неизвестный процесс.
5. Если фронтенд меняли, пересоберите `web`. После обновления Python-кода остановите именно свой uvicorn-процесс и запустите снова. Для ручного запуска в консоли используйте `.venv\Scripts\python.exe -X utf8 -m uvicorn lab_api:app --host 127.0.0.1 --port 8767`; Ctrl+C штатно завершит этот экземпляр.

При ошибке скачивания npm установщик пробует скачать большой архив Next.js небольшими частями с официального registry.npmjs.org. Перед добавлением в кэш проверяется SHA512 из package-lock.json. Затем установка один раз повторяется из кэша. Если сети всё ещё недостаточно, восстановите соединение и повторите установку. Архив исторических данных для этой ошибки повторно скачивать не требуется.

Скрипт запуска сначала выбирает `.venv\Scripts\python.exe`. На исходной машине также поддерживается прежний каталог библиотек `%LOCALAPPDATA%\NexusLabelLab\python-deps`. Для чистого восстановления используйте `.venv`.

## Что обязательно проверить после переноса

Откройте страницу и обе вкладки. Запустите один прогон дерева, затем автоподбор, проверьте прогресс, итоговые числа, рейтинг, количество зелёных и красных меток и одну сделку крупно. Для демонстрационных данных проверьте жёлтую подпись и отказ фиксации модели для будущей недели. В отдельном клоне команды тестов должны проходить без папки основной лаборатории.

Подробное описание поведения и ограничений находится в [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md).
