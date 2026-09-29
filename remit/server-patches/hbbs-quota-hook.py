#!/usr/bin/env python3
"""Встраивает проверку суточного лимита в hbbs (lejianwen/rustdesk-server, ветка forapi).

После патча hbbs перед выдачей punch hole спрашивает службу квот RemIT:
если бесплатные 3 часа в сутки израсходованы, клиент получает отказ с
понятным русским текстом вместо молчаливого таймаута.

В запрос уходит и токен входа из punch hole: по нему сайт узнаёт аккаунт
того, кто подключается, и проверяет лимит по его тарифу. Проверка стоит до
блока MUST_LOGIN, потому что там токен забирается из запроса.

Ещё уходит признак ws: запрос пришёл по WebSocket, то есть из веб-клиента.
Веб-клиент есть только на платных тарифах, и сайт пускает такие запросы
лишь с токеном подписчика или гостевой ссылки.

Использование:
    python3 hbbs-quota-hook.py path/to/rustdesk-server/src/rendezvous_server.rs

Скрипт идемпотентен и завершается с ошибкой, если исходник изменился и
точки вставки не найдены — молча пропустить патч он не может.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "remit_check_quota"

ANCHOR = """        // if secret is not empty check token by jwt
        if MUST_LOGIN.load(Ordering::SeqCst) {"""

CHECK = """        // RemIT: суточный лимит бесплатного использования.
        if let Some(text) = remit_check_quota(&ph.id, &ph.token, ws).await {
            let mut msg_out = RendezvousMessage::new();
            msg_out.set_punch_hole_response(PunchHoleResponse {
                other_failure: text,
                ..Default::default()
            });
            return Ok((msg_out, None));
        }

"""

HELPER = """

// --- RemIT: контроль суточного лимита бесплатного использования ---
//
// Адрес службы и токен задаются переменными окружения:
//   REMIT_QUOTA_URL     — например http://web:3000/api/v1/quota/check
//   REMIT_SERVICE_TOKEN — тот же токен, что и у сайта
//
// Если переменная не задана или служба недоступна, подключения не блокируются:
// отказ в обслуживании из-за сбоя биллинга хуже, чем неучтённая сессия.
async fn remit_check_quota(host_id: &str, login_token: &str, ws: bool) -> Option<String> {
    let url = std::env::var("REMIT_QUOTA_URL").unwrap_or_default();
    if url.is_empty() {
        return None;
    }
    let token = std::env::var("REMIT_SERVICE_TOKEN").unwrap_or_default();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build()
        .ok()?;

    let response = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", token))
        .json(&serde_json::json!({ "id": host_id, "token": login_token, "ws": ws }))
        .send()
        .await
        .ok()?;

    let body = response.json::<serde_json::Value>().await.ok()?;
    if body["allowed"].as_bool().unwrap_or(true) {
        return None;
    }

    let message = body["message"]
        .as_str()
        .unwrap_or("Лимит бесплатного использования исчерпан. Оформите подписку на remit.su");
    log::info!("remit: подключение к {} отклонено по квоте", host_id);
    Some(message.to_string())
}
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"Файл не найден: {path}", file=sys.stderr)
        return 1

    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print("Патч уже применён — пропускаем.")
        return 0

    if source.count(ANCHOR) != 1:
        print(
            "Не найдена единственная точка вставки в handle_punch_hole_request. "
            "Исходник изменился — обновите патч.",
            file=sys.stderr,
        )
        return 1

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")

    patched = source.replace(ANCHOR, CHECK + ANCHOR, 1).rstrip("\n") + HELPER
    path.write_text(patched, encoding="utf-8")
    print(f"Готово: {path} (резервная копия: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
