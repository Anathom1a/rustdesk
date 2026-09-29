#!/usr/bin/env python3
"""Ближайший ретранслятор по географии для hbbs.

Стоковый hbbs раздаёт ретрансляторы по кругу, не глядя, где стороны
соединения. После патча hbbs выбирает узел, до которого в сумме ближе всего
обоим участникам: управляющему и управляемому компьютеру.

- Координаты узлов приходят вместе со списком: `rs адрес@широта/долгота,…`
  (без координат — узел участвует только в круговой раздаче). Клиенты
  по-прежнему получают чистый адрес.
- Где находится IP, hbbs узнаёт из файла `REMIT_GEO_FILE` (по умолчанию
  geo.csv в рабочем каталоге): строки `начало,конец,широта,долгота`, IPv4
  числами, по возрастанию. Файл готовит server/geo/update-geo.sh из DB-IP
  City Lite. hbbs перечитывает его сам, когда файл меняется, и по команде
  `reload-geo` (`rg`); `geo-status` (`gs`) — сколько диапазонов загружено
  (по ответу сайт понимает, что hbbs умеет координаты).
- Нет файла, нет координат у узлов, адрес не нашёлся (локальная сеть,
  IPv6) — работает прежняя раздача по кругу среди живых узлов.

Использование:
    python3 relay-geo-hook.py path/to/rustdesk-server/src/rendezvous_server.rs

Скрипт идемпотентен и падает, если исходник изменился и точки вставки не
найдены.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "remit_geo_relay"

HELPER = r'''

// --- RemIT: ближайший ретранслятор по географии ---------------------------

lazy_static::lazy_static! {
    /// Координаты ретрансляторов: адрес → (широта, долгота).
    static ref REMIT_RELAY_COORDS: std::sync::RwLock<HashMap<String, (f64, f64)>> = Default::default();
    /// Диапазоны IPv4 → координаты; отсортированы по началу диапазона.
    static ref REMIT_GEO: std::sync::RwLock<Vec<(u32, u32, f32, f32)>> = Default::default();
    /// Когда файл был прочитан и его время изменения.
    static ref REMIT_GEO_STATE: std::sync::Mutex<(Option<Instant>, Option<std::time::SystemTime>)> = Default::default();
}

fn remit_geo_path() -> String {
    std::env::var("REMIT_GEO_FILE").unwrap_or_else(|_| "geo.csv".to_owned())
}

/// Читает файл GeoIP. Возвращает число диапазонов или ошибку.
fn remit_geo_load() -> Result<usize, String> {
    let path = remit_geo_path();
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{path}: {e}"))?;
    let mut ranges: Vec<(u32, u32, f32, f32)> = Vec::new();
    for line in text.lines() {
        let mut it = line.split(',');
        let (Some(a), Some(b), Some(lat), Some(lon)) = (it.next(), it.next(), it.next(), it.next()) else {
            continue;
        };
        if let (Ok(a), Ok(b), Ok(lat), Ok(lon)) = (a.parse(), b.parse(), lat.parse(), lon.parse()) {
            ranges.push((a, b, lat, lon));
        }
    }
    ranges.sort_by_key(|r| r.0);
    let n = ranges.len();
    *REMIT_GEO.write().unwrap() = ranges;
    log::info!("remit: GeoIP {path}: {n} диапазонов");
    Ok(n)
}

/// Перечитывает файл, если он изменился; проверяет не чаще раза в минуту.
fn remit_geo_refresh() {
    let mut state = REMIT_GEO_STATE.lock().unwrap();
    if let Some(at) = state.0 {
        if at.elapsed().as_secs() < 60 {
            return;
        }
    }
    state.0 = Some(Instant::now());
    let modified = std::fs::metadata(remit_geo_path()).and_then(|m| m.modified()).ok();
    if modified.is_some() && modified != state.1 {
        state.1 = modified;
        drop(state);
        if let Err(e) = remit_geo_load() {
            log::warn!("remit: GeoIP не прочитан: {e}");
        }
    }
}

fn remit_geo_lookup(ip: IpAddr) -> Option<(f64, f64)> {
    let v4 = match ip {
        IpAddr::V4(v4) => v4,
        IpAddr::V6(v6) => v6.to_ipv4_mapped()?,
    };
    let n = u32::from(v4);
    let geo = REMIT_GEO.read().unwrap();
    let i = geo.partition_point(|r| r.0 <= n);
    if i == 0 {
        return None;
    }
    let r = geo[i - 1];
    (n <= r.1).then_some((r.2 as f64, r.3 as f64))
}

/// Расстояние по поверхности Земли, км.
fn remit_distance(a: (f64, f64), b: (f64, f64)) -> f64 {
    let (la1, lo1, la2, lo2) = (a.0.to_radians(), a.1.to_radians(), b.0.to_radians(), b.1.to_radians());
    let h = ((la2 - la1) / 2.0).sin().powi(2) + la1.cos() * la2.cos() * ((lo2 - lo1) / 2.0).sin().powi(2);
    2.0 * 6371.0 * h.sqrt().asin()
}

/// Разбирает `адрес@широта/долгота` из списка ретрансляторов: координаты
/// запоминает, возвращает список чистых адресов через запятую.
fn remit_split_relay_coords(list: &str) -> String {
    let mut coords = REMIT_RELAY_COORDS.write().unwrap();
    coords.clear();
    let mut plain = Vec::new();
    for item in list.split(',') {
        let item = item.trim();
        if item.is_empty() {
            continue;
        }
        match item.split_once('@') {
            Some((addr, pos)) => {
                if let Some((lat, lon)) = pos.split_once('/') {
                    if let (Ok(lat), Ok(lon)) = (lat.parse::<f64>(), lon.parse::<f64>()) {
                        coords.insert(addr.to_owned(), (lat, lon));
                    }
                }
                plain.push(addr.to_owned());
            }
            None => plain.push(item.to_owned()),
        }
    }
    plain.join(",")
}

/// Узел для пары сторон: минимум суммы расстояний до обеих (или до той,
/// чьё положение известно). None — выбрать не из чего, раздаём по кругу.
fn remit_geo_relay(relays: &[String], pa: IpAddr, pb: IpAddr) -> Option<String> {
    remit_geo_refresh();
    let (a, b) = (remit_geo_lookup(pa), remit_geo_lookup(pb));
    if a.is_none() && b.is_none() {
        return None;
    }
    let coords = REMIT_RELAY_COORDS.read().unwrap();
    let mut best: Option<(f64, &String)> = None;
    for relay in relays {
        let Some(&pos) = coords.get(relay) else { continue };
        let score = a.map_or(0.0, |a| remit_distance(a, pos)) + b.map_or(0.0, |b| remit_distance(b, pos));
        if best.map_or(true, |(s, _)| score < s) {
            best = Some((score, relay));
        }
    }
    best.map(|(_, relay)| relay.clone())
}
'''


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1])
    src = path.read_text()
    if MARKER in src:
        print(f"{path}: уже пропатчен")
        return

    replacements = [
        # Выбор узла: сначала ближайший, иначе — как было, по кругу.
        (
            "    fn get_relay_server(&self, _pa: IpAddr, _pb: IpAddr) -> String {\n"
            "        if self.relay_servers.is_empty() {",
            "    fn get_relay_server(&self, _pa: IpAddr, _pb: IpAddr) -> String {\n"
            "        // remit_geo_relay: ближайший к обеим сторонам узел.\n"
            "        if let Some(relay) = remit_geo_relay(&self.relay_servers, _pa, _pb) {\n"
            "            return relay;\n"
            "        }\n"
            "        if self.relay_servers.is_empty() {",
        ),
        # Координаты из списка — отдельно, в список идут чистые адреса.
        (
            "    fn parse_relay_servers(&mut self, relay_servers: &str) {\n"
            "        let rs = get_servers(relay_servers, \"relay-servers\");",
            "    fn parse_relay_servers(&mut self, relay_servers: &str) {\n"
            "        let relay_servers = &remit_split_relay_coords(relay_servers);\n"
            "        let rs = get_servers(relay_servers, \"relay-servers\");",
        ),
        # Список узлов показываем с координатами — по нему сайт сверяет настройку.
        (
            "                    for ip in self.relay_servers.iter() {\n"
            "                        let _ = writeln!(res, \"{ip}\");\n"
            "                    }",
            "                    let coords = REMIT_RELAY_COORDS.read().unwrap();\n"
            "                    for ip in self.relay_servers.iter() {\n"
            "                        match coords.get(ip) {\n"
            "                            Some((lat, lon)) => {\n"
            "                                let _ = writeln!(res, \"{ip}@{lat}/{lon}\");\n"
            "                            }\n"
            "                            None => {\n"
            "                                let _ = writeln!(res, \"{ip}\");\n"
            "                            }\n"
            "                        }\n"
            "                    }",
        ),
        # Команда перечитать файл GeoIP.
        (
            "            Some(\"test-geo\" | \"tg\") => {",
            "            Some(\"geo-status\" | \"gs\") => {\n"
            "                remit_geo_refresh();\n"
            "                res = format!(\"geo: {}\\n\", REMIT_GEO.read().unwrap().len());\n"
            "            }\n"
            "            Some(\"reload-geo\" | \"rg\") => {\n"
            "                res = match remit_geo_load() {\n"
            "                    Ok(n) => format!(\"geo: {n}\\n\"),\n"
            "                    Err(e) => format!(\"geo: {e}\\n\"),\n"
            "                };\n"
            "            }\n"
            "            Some(\"test-geo\" | \"tg\") => {",
        ),
    ]
    for old, new in replacements:
        if src.count(old) != 1:
            sys.exit(f"{path}: точка вставки не найдена или неоднозначна:\n{old}")
        src = src.replace(old, new)

    src = src.rstrip("\n") + "\n" + HELPER
    path.write_text(src)
    print(f"{path}: ближайший ретранслятор включён")


if __name__ == "__main__":
    main()
