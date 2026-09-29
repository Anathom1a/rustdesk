# Патчи сервера RemIT (hbbs и hbbr)

Изменения, которые RemIT вносит в сервер RustDesk. Сервер — сборка
[lejianwen/rustdesk-server](https://github.com/lejianwen/rustdesk-server),
ветка `forapi` (AGPL-3.0). Здесь опубликованы все наши изменения его кода,
как того требует AGPL-3.0; лицензия изменённых файлов та же.

| Патч | Что делает |
| --- | --- |
| `hbbs-quota-hook.py` | Перед соединением hbbs спрашивает сайт, не исчерпан ли суточный лимит и разрешено ли подключение (`REMIT_QUOTA_URL`), и передаёт токен входа клиента. |
| `server-cmd-hook.py` | Служебные команды hbbs/hbbr (порты 21115 и 21117) принимаются не только с 127.0.0.1, но и по сети — если строка начинается с `REMIT-CMD <REMIT_SERVICE_TOKEN>`. Без токена поведение прежнее. |
| `relay-geo-hook.py` | Выбор ретранслятора, ближайшего к обеим сторонам соединения, по базе GeoIP (`REMIT_GEO_FILE`); координаты узлов — в списке `адрес@широта/долгота`. Без базы — раздача по кругу, как в оригинале. |

## Как собрать

```bash
git clone --recursive --branch forapi https://github.com/lejianwen/rustdesk-server
python3 hbbs-quota-hook.py rustdesk-server/src/rendezvous_server.rs
python3 server-cmd-hook.py rustdesk-server/src
python3 relay-geo-hook.py rustdesk-server/src/rendezvous_server.rs
cargo build --manifest-path rustdesk-server/Cargo.toml --release --bin hbbs --bin hbbr
```

Скрипты идемпотентны и останавливаются с ошибкой, если исходник изменился и
точка вставки не найдена.
