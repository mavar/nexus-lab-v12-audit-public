# Карта кода

Интерфейс — web/src/app/page.tsx, подписи — web/src/lib/learning-controls.ts.

API — lab_api.py, конфигурация — dashboard_config.py и lab_rules.json.

Модели и перебор — learn_jobs.py, учебные признаки и метки — learn_labels.py, объём — learn_volume.py, исполнение — harness_timed.py.

Сборка разметки — build.py с engine.js, app.js, charts.js, lab.js и index.html.

Установка — setup_lab.ps1, запуск — start_lab.ps1, диагностика — doctor.py, демонстрация — prepare_demo.py.

fetch_next.py восстанавливает скачивание большого архива Next.js с официального registry.npmjs.org по частям и сверяет SHA512 с package-lock.json. requirements-lock.txt фиксирует проверенную Python-среду.
