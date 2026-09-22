#!/usr/bin/env bash
# Накатывает фирменные правки RemIT на дерево исходников RustDesk.
# Запускается из GitHub Actions (.github/workflows/remit-build.yml) сразу
# после checkout, поэтому в форке лежат чистые исходники апстрима, а брендирование
# появляется только в собранном клиенте.
#
# Настройки берутся из переменных окружения (в Actions — из Variables и Secrets):
#   REMIT_PUBLIC_KEY   открытый ключ сервера; по умолчанию боевой
#   REMIT_SITE         адрес сайта и API, по умолчанию https://remit.su
#   REMIT_APP_NAME     название продукта, по умолчанию RemIT
#   REMIT_ID_SERVER    сервер идентификации, по умолчанию remit.su
#   REMIT_RELAY_SERVER ретранслятор, по умолчанию remit.su
#   REMIT_SUPPORT_URL  форма поддержки, по умолчанию <сайт>/kabinet/podderzhka
#   REMIT_SOURCE_URL   исходники клиента, по умолчанию адрес самого форка
#   REMIT_TEST_BUILD   true — собрать без ключа, только чтобы посмотреть
#                          (то же самое — слово test в файле .build-trigger)

set -Eeuo pipefail

# Windows-раннер по умолчанию отдаёт Python консоль в cp1252.
export PYTHONIOENCODING=utf-8

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

SITE="${REMIT_SITE:-https://remit.su}"
APP_NAME="${REMIT_APP_NAME:-RemIT}"
ID_SERVER="${REMIT_ID_SERVER:-remit.su}"
RELAY_SERVER="${REMIT_RELAY_SERVER:-remit.su}"
PUBLIC_KEY="${REMIT_PUBLIC_KEY:-0rexVZoXqaUjnIooWsmVscaVgkfLuxlpY7LN73X4UA0=}"
# Куда ведёт приглашение написать в поддержку под главным окном.
SUPPORT_URL="${REMIT_SUPPORT_URL:-${SITE%/}/kabinet/podderzhka}"
# Ссылка на исходники в окне «О программе»: требование AGPL-3.0. В Actions
# адрес самого форка известен, вне CI — берём наш репозиторий.
SOURCE_URL="${REMIT_SOURCE_URL:-${GITHUB_SERVER_URL:+${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}}}"
SOURCE_URL="${SOURCE_URL:-https://github.com/Anathom1a/rustdesk}"

# Режим сборки. При ручном запуске приходит галочкой, при запуске через
# .build-trigger берётся из самого файла: слово test в нём означает
# «собрать посмотреть, без ключа сервера».
TEST_BUILD="${REMIT_TEST_BUILD:-}"
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
    echo "Добавьте в настройках репозитория переменную REMIT_PUBLIC_KEY" >&2
    echo "(Settings -> Secrets and variables -> Actions -> Variables)." >&2
    echo "Значение лежит на сервере: /opt/remit/server/data/rustdesk/id_ed25519.pub" >&2
    exit 1
fi

echo "==> Брендирование: ${APP_NAME}, ${SITE}, ${ID_SERVER} / ${RELAY_SERVER}"
echo "==> Поддержка: ${SUPPORT_URL}; исходники: ${SOURCE_URL}"
python3 "${HERE}/patches/brand-client.py" "$ROOT" \
    --app-name "$APP_NAME" \
    --id-server "$ID_SERVER" \
    --relay-server "$RELAY_SERVER" \
    --api-server "$SITE" \
    --update-url "${SITE%/}/api/version/latest" \
    --support-url "$SUPPORT_URL" \
    --source-url "$SOURCE_URL" \
    --public-key "$PUBLIC_KEY" \
    --brand-dir "${HERE}/brand"


echo "==> Готово"
