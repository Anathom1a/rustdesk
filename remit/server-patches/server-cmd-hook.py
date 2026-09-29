#!/usr/bin/env python3
"""Открывает командный интерфейс hbbs и hbbr для админки сайта.

hbbs (порт 21115) и hbbr (порт 21117) принимают служебные команды —
relay-servers, ip-blocker, always-use-relay, blacklist, limit-speed и другие, —
но только с 127.0.0.1. Сайт работает в соседнем контейнере, поэтому после
патча команда принимается и по сети, если она начинается с
`REMIT-CMD <REMIT_SERVICE_TOKEN>\\n`. Без токена всё работает как раньше.

Использование:
    python3 server-cmd-hook.py path/to/rustdesk-server/src

Скрипт идемпотентен и завершается с ошибкой, если исходник изменился и
точки вставки не найдены.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "remit_is_cmd"

HELPER = """

// --- RemIT: команды из админки сайта по сервисному токену ---
//
// Формат: "REMIT-CMD <токен>\\n<команда> [аргументы]". Токен — REMIT_SERVICE_TOKEN.
// Пустой токен в окружении — команды по сети не принимаются.
const REMIT_CMD_PREFIX: &[u8] = b"REMIT-CMD ";

async fn remit_is_cmd(stream: &TcpStream) -> bool {
    let mut prefix = [0u8; 10];
    match timeout(1000, stream.peek(&mut prefix)).await {
        Ok(Ok(n)) => n == REMIT_CMD_PREFIX.len() && &prefix[..] == REMIT_CMD_PREFIX,
        _ => false,
    }
}

async fn remit_read_cmd(stream: &mut TcpStream) -> Option<String> {
    let expected = std::env::var("REMIT_SERVICE_TOKEN").unwrap_or_default();
    if expected.is_empty() {
        return None;
    }
    let mut buffer = [0u8; 2048];
    let n = match timeout(1000, stream.read(&mut buffer[..])).await {
        Ok(Ok(n)) => n,
        _ => return None,
    };
    let data = std::str::from_utf8(&buffer[..n]).ok()?;
    let rest = data.strip_prefix("REMIT-CMD ")?;
    let (token, cmd) = rest.split_once('\\n')?;
    let token = token.trim().as_bytes();
    let expected = expected.as_bytes();
    // Сравнение без раннего выхода: время не выдаёт, сколько символов совпало.
    let mut diff = (token.len() ^ expected.len()) as u8;
    for (i, byte) in expected.iter().enumerate() {
        diff |= byte ^ token.get(i).copied().unwrap_or(0);
    }
    if diff != 0 {
        log::warn!("remit: команда с неверным токеном отклонена");
        return None;
    }
    Some(cmd.trim().to_owned())
}
"""

HBBS_ANCHOR = """        let mut rs = self.clone();
        let ip = try_into_v4(addr).ip();
        if ip.is_loopback() {"""

HBBS_CHECK = """        let mut rs = self.clone();
        let ip = try_into_v4(addr).ip();
        // RemIT: команда из админки сайта.
        if !ip.is_loopback() && remit_is_cmd(&stream).await {
            tokio::spawn(async move {
                let mut stream = stream;
                if let Some(cmd) = remit_read_cmd(&mut stream).await {
                    let res = rs.check_cmd(&cmd).await;
                    stream.write(res.as_bytes()).await.ok();
                }
            });
            return;
        }
        if ip.is_loopback() {"""

HBBR_ANCHOR = """    let ip = hbb_common::try_into_v4(addr).ip();
    if !ws && ip.is_loopback() {"""

HBBR_CHECK = """    let ip = hbb_common::try_into_v4(addr).ip();
    // RemIT: команда из админки сайта.
    if !ws && !ip.is_loopback() && remit_is_cmd(&stream).await {
        let limiter = limiter.clone();
        tokio::spawn(async move {
            let mut stream = stream;
            if let Some(cmd) = remit_read_cmd(&mut stream).await {
                let res = check_cmd(&cmd, limiter).await;
                stream.write(res.as_bytes()).await.ok();
            }
        });
        return;
    }
    if !ws && ip.is_loopback() {"""


def patch(path: Path, anchor: str, check: str) -> None:
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print(f"{path.name}: патч уже применён — пропускаем.")
        return
    if source.count(anchor) != 1:
        raise SystemExit(f"{path.name}: не найдена точка вставки. Исходник изменился — обновите патч.")
    backup = path.with_suffix(path.suffix + ".bak-cmd")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(anchor, check, 1).rstrip("\n") + HELPER, encoding="utf-8")
    print(f"Готово: {path}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    patch(src / "rendezvous_server.rs", HBBS_ANCHOR, HBBS_CHECK)
    patch(src / "relay_server.rs", HBBR_ANCHOR, HBBR_CHECK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
