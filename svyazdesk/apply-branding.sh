#!/usr/bin/env bash
# Накатывает фирменные правки СвязьDesk на дерево исходников RustDesk.
# Запускается из GitHub Actions (.github/workflows/svyazdesk-build.yml) сразу
# после checkout, поэтому в форке лежат чистые исходники апстрима, а брендирование
# появляется только в собранном клиенте.
#
# Настройки берутся из переменных окружения (в Actions — из Variables и Secrets):
#   SVYAZDESK_PUBLIC_KEY   открытый ключ hbbs, обязателен
#   SVYAZDESK_SITE         адрес сайта и API, по умолчанию https://svyazdesk.ru
#   SVYAZDESK_APP_NAME     название продукта, по умолчанию SvyazDesk
#   SVYAZDESK_ID_SERVER    сервер идентификации, по умолчанию id.svyazdesk.ru
#   SVYAZDESK_RELAY_SERVER ретранслятор, по умолчанию relay.svyazdesk.ru
#   SVYAZDESK_TEST_BUILD   true — собрать без ключа, только чтобы посмотреть
#                          (то же самое — слово test в файле .build-trigger)

set -Eeuo pipefail

# Windows-раннер по умолчанию отдаёт Python консоль в cp1252.
export PYTHONIOENCODING=utf-8

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

SITE="${SVYAZDESK_SITE:-https://svyazdesk.ru}"
APP_NAME="${SVYAZDESK_APP_NAME:-SvyazDesk}"
ID_SERVER="${SVYAZDESK_ID_SERVER:-id.svyazdesk.ru}"
RELAY_SERVER="${SVYAZDESK_RELAY_SERVER:-relay.svyazdesk.ru}"
PUBLIC_KEY="${SVYAZDESK_PUBLIC_KEY:-}"

# Режим сборки. При ручном запуске приходит галочкой, при запуске через
# .build-trigger берётся из самого файла: слово test в нём означает
# «собрать посмотреть, без ключа сервера».
TEST_BUILD="${SVYAZDESK_TEST_BUILD:-}"
if [[ -z "$TEST_BUILD" || "$TEST_BUILD" == "false" ]]; then
    if [[ -f "${ROOT}/.build-trigger" ]] && grep -qiw test "${ROOT}/.build-trigger"; then
        TEST_BUILD=true
    fi
fi

if [[ -z "$PUBLIC_KEY" && "$TEST_BUILD" == "true" ]]; then
    # Ключ ещё не выпущен: собираем «посмотреть, как выглядит».
    # Такой клиент запускается и показывает интерфейс, но к серверу не
    # подключится — раздавать его нельзя.
    PUBLIC_KEY="TESTBUILD0000000000000000000000000000000000="
    echo "::warning::Тестовая сборка без ключа сервера: клиент не подключится."
fi

if [[ -z "$PUBLIC_KEY" ]]; then
    echo "::error::Не задан открытый ключ сервера." >&2
    echo "Добавьте в настройках репозитория переменную SVYAZDESK_PUBLIC_KEY" >&2
    echo "(Settings -> Secrets and variables -> Actions -> Variables)." >&2
    echo "Значение лежит на сервере: /opt/svyazdesk/server/data/rustdesk/id_ed25519.pub" >&2
    exit 1
fi

echo "==> Брендирование: ${APP_NAME}, ${SITE}, ${ID_SERVER} / ${RELAY_SERVER}"
python3 "${HERE}/patches/brand-client.py" "$ROOT" \
    --app-name "$APP_NAME" \
    --id-server "$ID_SERVER" \
    --relay-server "$RELAY_SERVER" \
    --api-server "$SITE" \
    --update-url "${SITE%/}/api/version/latest" \
    --public-key "$PUBLIC_KEY" \
    --brand-dir "${HERE}/brand"


echo "==> Готово"
