#!/usr/bin/env python3
"""Превращает исходники RustDesk в фирменный клиент RemIT.

Что делает скрипт в клоне https://github.com/rustdesk/rustdesk:

1. libs/hbb_common/src/config.rs
   - RENDEZVOUS_SERVERS  -> ваш ID-сервер;
   - RS_PUB_KEY          -> ваш публичный ключ;
   - APP_NAME            -> название продукта;
   - DEFAULT_SETTINGS    -> адреса ID-сервера, ретранслятора и API-сервера,
                            чтобы клиент сразу работал с вашей инфраструктурой.
2. libs/hbb_common/src/lib.rs
   - адрес проверки обновлений -> ваш сервер обновлений.
3. src/common.rs и flutter/lib/common.dart
   - снимают запрет на проверку обновлений в фирменной сборке: иначе клиент
     молча перестаёт проверять версии и правки до пользователей не доезжают.
4. flutter/lib/desktop/pages/desktop_home_page.dart
   - показывает карточку «доступна новая версия» и ведёт её ссылки на наш сайт;
   - добавляет карточку с остатком бесплатного времени и сроком подписки.
5. flutter/lib/common.dart
   - логотип в главном окне открывает сайт по нажатию.
6. Заменяет видимые вхождения «RustDesk» в ресурсах сборки и интерфейсе.
7. flutter/lib/desktop/pages/desktop_setting_page.dart
   - окно «О программе»: ссылки ведут на наш сайт, рядом появляются
     «Поддержка» и «Исходный код» (второе требует AGPL-3.0).
8. src/lang/*.rs
   - в переводах меняем только значения: ключ — это английский оригинал,
     по нему translate() ищет строку, и переименование ключа вроде
     «About RustDesk» просто выключило бы перевод.
   - подпись под главным окном (powered_by_me) вместо «Основано на RustDesk»
     зовёт написать в поддержку.

Использование:
    python3 brand-client.py /path/to/rustdesk \
        --app-name RemIT \
        --id-server remit.su \
        --relay-server remit.su \
        --api-server https://remit.su \
        --update-url https://remit.su/api/version/latest \
        --public-key 'БАЗА64_КЛЮЧА_HBBS'

Скрипт падает с ошибкой, если обязательная точка замены не найдена:
незаметно собрать клиент с чужими серверами нельзя.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Windows: консоль раннера работает в cp1252, и русские сообщения скрипта
# роняют его с UnicodeEncodeError ещё до первой правки. Переводим вывод в UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Файлы, в которых заменяем видимое название продукта. Отсутствующие пропускаем:
# набор файлов отличается от версии к версии.
BRAND_FILES = [
    "flutter/lib/common.dart",
    "flutter/lib/desktop/pages/desktop_home_page.dart",
    "flutter/pubspec.yaml",
    "res/setup.nsi",
    "res/msi/Package/Package.wxs",
    "res/rustdesk.desktop",
    "res/rustdesk-link.desktop",
    "flutter/windows/runner/main.cpp",
    "flutter/windows/runner/Runner.rc",
    "Cargo.toml",
]
# flutter/macos/Runner/Configs/AppInfo.xcconfig намеренно не трогаем: PRODUCT_NAME
# задаёт имя бандла RustDesk.app, на которое завязана упаковка dmg в CI.


def patch_config(path: Path, args: argparse.Namespace) -> None:
    source = path.read_text(encoding="utf-8")
    original = source

    replacements: list[tuple[str, str, str]] = [
        (
            "RENDEZVOUS_SERVERS",
            r'pub const RENDEZVOUS_SERVERS: &\[&str\] = &\[[^\]]*\];',
            f'pub const RENDEZVOUS_SERVERS: &[&str] = &["{args.id_server.split(":")[0]}"];',
        ),
        (
            "RS_PUB_KEY",
            r'pub const RS_PUB_KEY: &str = "[^"]*";',
            f'pub const RS_PUB_KEY: &str = "{args.public_key}";',
        ),
        (
            "APP_NAME",
            r'pub static ref APP_NAME: RwLock<String> = RwLock::new\("[^"]*"\.to_owned\(\)\);',
            f'pub static ref APP_NAME: RwLock<String> = RwLock::new("{args.app_name}".to_owned());',
        ),
        (
            "DEFAULT_SETTINGS",
            r'pub static ref DEFAULT_SETTINGS: RwLock<HashMap<String, String>> = [^;]*;',
            (
                "pub static ref DEFAULT_SETTINGS: RwLock<HashMap<String, String>> = "
                "RwLock::new(HashMap::from([\n"
                f'            ("custom-rendezvous-server".to_owned(), "{args.id_server}".to_owned()),\n'
                f'            ("relay-server".to_owned(), "{args.relay_server}".to_owned()),\n'
                f'            ("api-server".to_owned(), "{args.api_server}".to_owned()),\n'
                f'            ("key".to_owned(), "{args.public_key}".to_owned()),\n'
                '            ("enable-check-update".to_owned(), "Y".to_owned()),\n'
                "        ]));"
            ),
        ),
    ]

    for name, pattern, replacement in replacements:
        matches = re.findall(pattern, source)
        if len(matches) != 1:
            raise SystemExit(
                f"{path}: ожидалось одно вхождение {name}, найдено {len(matches)}. "
                "Исходники RustDesk изменились — обновите скрипт."
            )
        source = re.sub(pattern, replacement.replace("\\", "\\\\"), source, count=1)

    if source != original:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(source, encoding="utf-8")
    print(f"Настроены серверы и название в {path}")


def lock_servers(path: Path, args: argparse.Namespace) -> None:
    """Прибивает адреса серверов и ключ намертво.

    RustDesk хранит «неизменяемые» настройки в OVERWRITE_SETTINGS: значения
    оттуда побеждают файл конфигурации, а Config::set_option отказывается их
    перезаписывать. BUILTIN_SETTINGS с hide-server-settings убирает из
    интерфейса сам пункт «ID/Relay Server» — и на компьютере, и на телефоне.

    Вместе это значит: клиент работает только в нашей сети, подменить
    ретранслятор через настройки, ключ командной строки --config или ручную
    правку конфига нельзя.
    """
    source = path.read_text(encoding="utf-8")
    original = source

    replacements: list[tuple[str, str, str]] = [
        (
            "OVERWRITE_SETTINGS",
            r'pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = [^;]*;',
            (
                "pub static ref OVERWRITE_SETTINGS: RwLock<HashMap<String, String>> = "
                "RwLock::new(HashMap::from([\n"
                f'            ("custom-rendezvous-server".to_owned(), "{args.id_server}".to_owned()),\n'
                f'            ("relay-server".to_owned(), "{args.relay_server}".to_owned()),\n'
                f'            ("api-server".to_owned(), "{args.api_server}".to_owned()),\n'
                f'            ("key".to_owned(), "{args.public_key}".to_owned()),\n'
                "        ]));"
            ),
        ),
        (
            "BUILTIN_SETTINGS",
            r'pub static ref BUILTIN_SETTINGS: RwLock<HashMap<String, String>> = [^;]*;',
            (
                "pub static ref BUILTIN_SETTINGS: RwLock<HashMap<String, String>> = "
                "RwLock::new(HashMap::from([\n"
                '            ("hide-server-settings".to_owned(), "Y".to_owned()),\n'
                "        ]));"
            ),
        ),
    ]

    for name, pattern, replacement in replacements:
        matches = re.findall(pattern, source)
        if len(matches) != 1:
            raise SystemExit(
                f"{path}: ожидалось одно вхождение {name}, найдено {len(matches)}. "
                "Исходники RustDesk изменились — обновите скрипт."
            )
        source = re.sub(pattern, replacement.replace("\\", "\\\\"), source, count=1)

    if source != original:
        path.write_text(source, encoding="utf-8")
    print(f"Серверы и ключ закреплены намертво в {path}")


MIGRATE_FN = """
    // RemIT: переносит настройки клиента, который стоял раньше под другим
    // названием. Каталог и имена файлов конфигурации берутся из названия
    // продукта, поэтому без переноса у каждой машины сменился бы ID — он
    // лежит в этом же конфиге.
    //
    // Имён проверяем несколько: у одних машин стоял безымянный RustDesk, у
    // других — уже переименованная сборка. Если своя конфигурация уже есть
    // (в том числе от сборки с тем же именем), не делаем ничего: на Windows
    // имена каталогов и файлов регистронезависимы, старый каталог подхватится
    // сам.
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    pub fn migrate_from_any(legacy_app_names: &[&str]) {
        fn copy_dir(from: &Path, to: &Path, legacy: &str, current: &str) {
            if std::fs::create_dir_all(to).is_err() {
                return;
            }
            let Ok(entries) = std::fs::read_dir(from) else {
                return;
            };
            for entry in entries.flatten() {
                let src = entry.path();
                let name = entry.file_name().to_string_lossy().to_string();
                let name = if name.starts_with(legacy) {
                    format!("{}{}", current, &name[legacy.len()..])
                } else {
                    name
                };
                let dst = to.join(name);
                if src.is_dir() {
                    copy_dir(&src, &dst, legacy, current);
                } else if src.is_file() {
                    let _allow_err = std::fs::copy(&src, &dst);
                }
            }
        }

        fn config_dir_for(app_name: &str, current: &str) -> PathBuf {
            *APP_NAME.write().unwrap() = app_name.to_owned();
            let dir = Config::path("");
            *APP_NAME.write().unwrap() = current.to_owned();
            dir
        }

        let current = APP_NAME.read().unwrap().clone();
        let new_dir = Self::path("");
        if new_dir.as_os_str().is_empty() {
            return;
        }
        // Своя конфигурация уже на месте — переносить нечего.
        if new_dir.join(format!("{}.toml", current)).exists() {
            return;
        }
        for legacy in legacy_app_names {
            if legacy.eq_ignore_ascii_case(&current) {
                continue;
            }
            let legacy_dir = config_dir_for(legacy, &current);
            if legacy_dir == new_dir || !legacy_dir.is_dir() {
                continue;
            }
            if !legacy_dir.join(format!("{}.toml", legacy)).exists() {
                continue;
            }
            log::info!("migrating config from {:?} to {:?}", legacy_dir, new_dir);
            copy_dir(&legacy_dir, &new_dir, legacy, &current);
            return;
        }
    }

"""


def add_config_migration(config_path: Path, core_main_path: Path, legacy: str) -> None:
    """Переносит настройки прошлого клиента при первом запуске.

    Иначе смена названия продукта означает новый каталог конфигурации, новый
    файл — и новый ID у каждой установленной машины.
    """
    source = config_path.read_text(encoding="utf-8")
    anchor = "    pub fn path<P: AsRef<Path>>(p: P) -> PathBuf {"
    if anchor not in source:
        raise SystemExit(f"{config_path}: не найден Config::path — обновите скрипт.")
    if "fn migrate_from(" not in source:
        source = source.replace(anchor, MIGRATE_FN.lstrip("\n") + anchor, 1)
        config_path.write_text(source, encoding="utf-8")

    source = core_main_path.read_text(encoding="utf-8")
    call_anchor = "    crate::load_custom_client();"
    if call_anchor not in source:
        raise SystemExit(
            f"{core_main_path}: не найден вызов load_custom_client — обновите скрипт."
        )
    if "migrate_from_any(" not in source:
        source = source.replace(
            call_anchor,
            call_anchor
            + "\n    #[cfg(not(any(target_os = \"android\", target_os = \"ios\")))]\n"
            + "    hbb_common::config::Config::migrate_from_any(&["
            + ", ".join(f'"{name}"' for name in legacy.split(","))
            + "]);",
            1,
        )
        core_main_path.write_text(source, encoding="utf-8")
    print(f"Перенос настроек из {legacy} включён")


def set_default_theme(path: Path) -> None:
    """Открывает клиент в тёмной теме — той же, что и сайт.

    Это не жёсткая фиксация: пользователь может переключиться в настройках,
    выбор сохранится. Меняется только значение по умолчанию.
    """
    source = path.read_text(encoding="utf-8")
    anchor = (
        "pub static ref DEFAULT_LOCAL_SETTINGS: RwLock<HashMap<String, String>> = "
        "Default::default();"
    )
    if anchor not in source:
        raise SystemExit(
            f"{path}: не найден DEFAULT_LOCAL_SETTINGS — обновите скрипт."
        )
    source = source.replace(
        anchor,
        "pub static ref DEFAULT_LOCAL_SETTINGS: RwLock<HashMap<String, String>> = "
        "RwLock::new(HashMap::from([\n"
        '            ("theme".to_owned(), "dark".to_owned()),\n'
        "        ]));",
        1,
    )
    path.write_text(source, encoding="utf-8")
    print(f"Тёмная тема выбрана по умолчанию в {path}")


def disable_custom_client(path: Path) -> None:
    """Отключает подмену серверов через файл custom.txt рядом с программой.

    Иначе кто угодно с доступом к папке установки подменил бы ретранслятор,
    положив рядом свой custom.txt.
    """
    source = path.read_text(encoding="utf-8")
    anchor = "pub fn read_custom_client(config: &str) {"
    if anchor not in source:
        raise SystemExit(
            f"{path}: не найдена read_custom_client — обновите скрипт."
        )
    marker = "// RemIT: подмена серверов через custom.txt запрещена."
    if marker in source:
        return
    source = source.replace(
        anchor,
        anchor + "\n    " + marker + "\n    // if true — чтобы rustc не ругался на недостижимый код ниже.\n    if true {\n        return;\n    }",
        1,
    )
    path.write_text(source, encoding="utf-8")
    print(f"Подмена серверов через custom.txt отключена в {path}")


# Куда раскладываются фирменные иконки. Слева — файл в каталоге оформления,
# справа — места в дереве RustDesk. Отсутствующие файлы пропускаем.
BRAND_ASSETS: list[tuple[str, list[str]]] = [
    ("icon.png", ["res/icon.png", "flutter/assets/icon.png"]),
    ("32x32.png", ["res/32x32.png"]),
    ("64x64.png", ["res/64x64.png"]),
    ("128x128.png", ["res/128x128.png"]),
    ("128x128@2x.png", ["res/128x128@2x.png"]),
    ("icon.ico", ["res/icon.ico", "flutter/windows/runner/resources/app_icon.ico"]),
    ("tray-icon.ico", ["res/tray-icon.ico"]),
    ("mac-icon.png", ["res/mac-icon.png"]),
    ("mac-tray-dark-x2.png", ["res/mac-tray-dark-x2.png"]),
    ("mac-tray-light-x2.png", ["res/mac-tray-light-x2.png"]),
    ("AppIcon.icns", ["flutter/macos/Runner/AppIcon.icns"]),
    ("icon.svg", ["flutter/assets/icon.svg", "res/logo.svg", "res/logo-header.svg"]),
    ("scalable.svg", ["res/scalable.svg"]),
    ("logo.png", ["flutter/assets/logo.png"]),
]

ANDROID_DENSITIES = ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]
ANDROID_ICONS = ["ic_launcher.png", "ic_launcher_round.png", "ic_launcher_foreground.png"]


def widen_main_window(path: Path) -> None:
    """Увеличивает стартовое окно на Windows.

    У апстрима 800x600. Мы добавили в левую колонку логотип, которого там не
    было, и нижняя карточка — та самая, с кнопкой «Установить», — переставала
    помещаться. Размер всё равно подрезается под рабочую область экрана, так
    что на маленьких мониторах ничего не сломается.
    """
    source = path.read_text(encoding="utf-8")
    anchor = "Win32Window::Size size(800u, 600u);"
    if anchor not in source:
        raise SystemExit(
            f"{path}: не найден размер окна — обновите скрипт."
        )
    source = source.replace(anchor, "Win32Window::Size size(920u, 720u);", 1)
    source = source.replace(
        "// Compute window bounds for default main window position: (10, 10) x(800, 600)",
        "// Compute window bounds for default main window position: (10, 10) x(920, 720)",
        1,
    )
    path.write_text(source, encoding="utf-8")
    print(f"Стартовое окно увеличено до 920x720 в {path}")


def brand_portable_folder(path: Path, app_name: str) -> None:
    """Переименовывает папку, куда распаковывается переносимая сборка.

    Один .exe с сайта — это самораспаковывающаяся оболочка: внутри лежит
    приложение с библиотеками, при запуске оно разворачивается в
    %LOCALAPPDATA%. Папка там называлась rustdesk — теперь по имени продукта.
    """
    source = path.read_text(encoding="utf-8")
    anchor = 'const APP_PREFIX: &str = "rustdesk";'
    if anchor not in source:
        raise SystemExit(
            f"{path}: не найден APP_PREFIX — обновите скрипт."
        )
    folder = app_name.lower()
    source = source.replace(anchor, f'const APP_PREFIX: &str = "{folder}";', 1)
    path.write_text(source, encoding="utf-8")
    print(f"Папка распаковки переименована в {folder}: {path}")


def install_font(root: Path, brand_dir: Path) -> None:
    """Кладёт шрифт в сборку и объявляет его в pubspec и в теме."""
    source_dir = brand_dir / "fonts"
    if not source_dir.is_dir():
        print("Каталог со шрифтом не найден — остаётся системный")
        return

    target_dir = root / "flutter" / "assets" / "fonts"
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name, _weight in FONT_WEIGHTS:
        source = source_dir / f"{FONT_FAMILY}-{name}.ttf"
        if source.is_file():
            shutil.copyfile(source, target_dir / source.name)
            copied += 1
    licence = source_dir / "OFL.txt"
    if licence.is_file():
        shutil.copyfile(licence, target_dir / "OFL.txt")
    if copied == 0:
        print("Файлов шрифта нет — остаётся системный")
        return

    pubspec = root / "flutter" / "pubspec.yaml"
    text = pubspec.read_text(encoding="utf-8")
    if f"family: {FONT_FAMILY}" not in text:
        anchor = "  fonts:\n"
        if anchor not in text:
            raise SystemExit(f"{pubspec}: не найден раздел fonts — обновите скрипт.")
        block = f"    - family: {FONT_FAMILY}\n      fonts:\n"
        for name, weight in FONT_WEIGHTS:
            if (source_dir / f"{FONT_FAMILY}-{name}.ttf").is_file():
                block += (
                    f"        - asset: assets/fonts/{FONT_FAMILY}-{name}.ttf\n"
                    f"          weight: {weight}\n"
                )
        text = text.replace(anchor, anchor + block, 1)
        pubspec.write_text(text, encoding="utf-8")

    common = root / "flutter" / "lib" / "common.dart"
    text = common.read_text(encoding="utf-8")
    changed = 0
    for anchor in ("  static ThemeData lightTheme = ThemeData(\n",
                   "  static ThemeData darkTheme = ThemeData(\n"):
        if anchor not in text:
            raise SystemExit(f"{common}: не найдена тема — обновите скрипт.")
        if text.count(anchor + f"    fontFamily: '{FONT_FAMILY}',\n") == 0:
            text = text.replace(anchor, anchor + f"    fontFamily: '{FONT_FAMILY}',\n", 1)
            changed += 1
    if changed:
        common.write_text(text, encoding="utf-8")
    print(f"Шрифт {FONT_FAMILY} встроен: {copied} начертани(й)")


def install_brand_assets(root: Path, brand_dir: Path) -> None:
    """Меняет иконки RustDesk на наши во всём дереве."""
    if not brand_dir.is_dir():
        print(f"Каталог оформления {brand_dir} не найден — иконки остаются стандартными")
        return

    copied = 0
    for name, targets in BRAND_ASSETS:
        source = brand_dir / name
        if not source.is_file():
            continue
        for relative in targets:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied += 1

    android_root = root / "flutter" / "android" / "app" / "src" / "main" / "res"
    for density in ANDROID_DENSITIES:
        source_dir = brand_dir / "android" / f"mipmap-{density}"
        target_dir = android_root / f"mipmap-{density}"
        if not source_dir.is_dir() or not target_dir.is_dir():
            continue
        for name in ANDROID_ICONS:
            source = source_dir / name
            if source.is_file():
                shutil.copyfile(source, target_dir / name)
                copied += 1

    background = android_root / "values" / "ic_launcher_background.xml"
    if background.is_file():
        background.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<resources>\n"
            '    <color name="ic_launcher_background">#0B101C</color>\n'
            "</resources>\n",
            encoding="utf-8",
        )
        copied += 1

    print(f"Иконки заменены на фирменные: {copied} файл(ов)")


def patch_update_url(path: Path, update_url: str) -> None:
    """Перенаправляет проверку обновлений на наш сервер."""
    source = path.read_text(encoding="utf-8")
    pattern = r'const URL: &str = "[^"]*";'
    matches = re.findall(pattern, source)
    if len(matches) != 1:
        raise SystemExit(
            f"{path}: ожидался один адрес проверки обновлений, найдено {len(matches)}. "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(re.sub(pattern, f'const URL: &str = "{update_url}";', source, count=1), encoding="utf-8")
    print(f"Сервер обновлений прописан в {path}")


def enable_update_check(path: Path) -> None:
    """Убирает ранний выход, из-за которого фирменная сборка не проверяет обновления."""
    source = path.read_text(encoding="utf-8")
    anchor = """pub fn check_software_update() {
    if is_custom_client() {
        return;
    }
"""
    replacement = """pub fn check_software_update() {
    // RemIT: фирменная сборка проверяет обновления на своём сервере.
"""
    if replacement in source:
        print("Проверка обновлений уже включена — пропускаем.")
        return
    if source.count(anchor) != 1:
        raise SystemExit(
            f"{path}: не найден запрет проверки обновлений для фирменной сборки. "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(anchor, replacement, 1), encoding="utf-8")
    print(f"Проверка обновлений включена в {path}")


FLUTTER_CHECK_ANCHOR = """void checkUpdate() {
  if (!isWeb) {
    if (!bind.isCustomClient()) {"""

FLUTTER_CHECK_PATCHED = """void checkUpdate() {
  if (!isWeb) {
    // RemIT: фирменная сборка тоже проверяет обновления при запуске.
    if (true) {"""


def enable_flutter_update_check(path: Path) -> None:
    """Включает проверку обновлений при запуске в интерфейсе на Flutter."""
    source = path.read_text(encoding="utf-8")
    if FLUTTER_CHECK_PATCHED in source:
        print("Проверка обновлений в интерфейсе уже включена — пропускаем.")
        return
    if source.count(FLUTTER_CHECK_ANCHOR) != 1:
        raise SystemExit(
            f"{path}: не найдена проверка обновлений checkUpdate(). "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(FLUTTER_CHECK_ANCHOR, FLUTTER_CHECK_PATCHED, 1), encoding="utf-8")
    print(f"Проверка обновлений при запуске включена в {path}")


CARD_ANCHOR = """    if (!bind.isCustomClient() &&
        updateUrl.isNotEmpty &&
        !isCardClosed &&
        bind.mainUriPrefixSync().contains('rustdesk')) {"""

CARD_PATCHED = """    // RemIT: предложение обновиться показываем и в фирменной сборке.
    if (updateUrl.isNotEmpty && !isCardClosed) {"""


def enable_update_card(path: Path, site_url: str) -> None:
    """Показывает карточку «доступна новая версия» и ведёт ссылки на наш сайт."""
    source = path.read_text(encoding="utf-8")
    original = source

    if CARD_PATCHED not in source:
        if source.count(CARD_ANCHOR) != 1:
            raise SystemExit(
                f"{path}: не найдено условие показа карточки обновления. "
                "Исходники RustDesk изменились — обновите скрипт."
            )
        source = source.replace(CARD_ANCHOR, CARD_PATCHED, 1)

    download_anchor = "final Uri url = Uri.parse('https://rustdesk.com/download');"
    if download_anchor in source:
        source = source.replace(
            download_anchor,
            f"final Uri url = Uri.parse('{site_url}/skachat');",
            1,
        )

    changelog_anchor = (
        "'https://github.com/rustdesk/rustdesk/releases/tag/${bind.mainGetNewVersion()}'"
    )
    if changelog_anchor in source:
        source = source.replace(
            changelog_anchor,
            f"'{site_url}/obnovlenie/${{bind.mainGetNewVersion()}}'",
            1,
        )

    if source == original:
        print("Карточка обновления уже настроена — пропускаем.")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    path.write_text(source, encoding="utf-8")
    print(f"Карточка обновления настроена в {path}")


LOGO_ANCHOR = """          return Container(
            constraints: BoxConstraints(maxWidth: 300, maxHeight: 60),
            child: image,
          ).marginOnly(left: 12, right: 12, top: 12);"""


def make_logo_clickable(path: Path, site_url: str) -> None:
    """Логотип в главном окне открывает сайт по нажатию."""
    source = path.read_text(encoding="utf-8")
    if "remit-logo-link" in source:
        print("Ссылка на сайте с логотипа уже добавлена — пропускаем.")
        return
    if source.count(LOGO_ANCHOR) != 1:
        raise SystemExit(
            f"{path}: не найден виджет логотипа. "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    replacement = f"""          // remit-logo-link: по нажатию открываем сайт продукта.
          return InkWell(
            onTap: () => launchUrl(Uri.parse('{site_url}')),
            child: Container(
              constraints: BoxConstraints(maxWidth: 300, maxHeight: 60),
              child: image,
            ),
          ).marginOnly(left: 12, right: 12, top: 12);"""

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(LOGO_ANCHOR, replacement, 1), encoding="utf-8")
    print(f"Логотип сделан ссылкой на {site_url} в {path}")


# Подпись под главным окном: у RustDesk это «Основано на RustDesk» со ссылкой
# на rustdesk.com. Ставим на её место приглашение написать в поддержку.
POWERED_ANCHOR = """Widget loadPowered(BuildContext context) {
  if (bind.mainGetBuildinOption(key: "hide-powered-by-me") == 'Y') {
    return SizedBox.shrink();
  }
  return MouseRegion(
    cursor: SystemMouseCursors.click,
    child: GestureDetector(
      onTap: () {
        launchUrl(Uri.parse('https://rustdesk.com'));
      },
      child: Opacity(
          opacity: 0.5,
          child: Text(
            translate("powered_by_me"),
            overflow: TextOverflow.clip,
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(fontSize: 9, decoration: TextDecoration.underline),
          )),
    ),
  ).marginOnly(top: 6);
}"""


def replace_powered_by(path: Path, support_url: str) -> None:
    """Меняет подпись «Основано на RustDesk» на ссылку в поддержку.

    Сам текст берём из переводов (ключ powered_by_me) — его правит
    rebrand_lang_strings. Здесь меняем адрес ссылки и делаем надпись
    читаемой: девятый кегль под половинной прозрачностью в окне не видно,
    а ссылка должна бросаться в глаза, когда что-то не работает.
    """
    source = path.read_text(encoding="utf-8")
    if "remit-support-link" in source:
        print("Ссылка на поддержку уже добавлена — пропускаем.")
        return
    if source.count(POWERED_ANCHOR) != 1:
        raise SystemExit(
            f"{path}: не найдена подпись loadPowered(). "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    replacement = f"""Widget loadPowered(BuildContext context) {{
  // remit-support-link: вместо упоминания исходного проекта — путь в поддержку.
  if (bind.mainGetBuildinOption(key: "hide-powered-by-me") == 'Y') {{
    return SizedBox.shrink();
  }}
  return MouseRegion(
    cursor: SystemMouseCursors.click,
    child: GestureDetector(
      onTap: () {{
        launchUrl(Uri.parse('{support_url}'));
      }},
      child: Text(
        translate("powered_by_me"),
        overflow: TextOverflow.clip,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.bodySmall?.copyWith(
            fontSize: 11,
            color: MyTheme.accent,
            decoration: TextDecoration.underline),
      ),
    ),
  ).marginOnly(top: 6, left: 8, right: 8);
}}"""

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(POWERED_ANCHOR, replacement, 1), encoding="utf-8")
    print(f"Подпись под окном ведёт в поддержку: {support_url}")


# Окно «О программе»: ссылки ведут на rustdesk.com.
ABOUT_LINKS = [
    ("https://rustdesk.com/privacy.html", "{site}/dokumenty/politika"),
    ("https://rustdesk.com", "{site}"),
]

ABOUT_WEBSITE_ANCHOR = """              InkWell(
                  onTap: () {
                    launchUrlString('__SITE__');
                  },
                  child: Text(
                    translate('Website'),
                    style: linkStyle,
                  ).marginSymmetric(vertical: 4.0)),"""


def patch_about_dialog(path: Path, site_url: str, support_url: str, source_url: str) -> None:
    """Правит окно «О программе».

    Ссылки «Политика конфиденциальности» и «Сайт» ведут на наш сайт, рядом
    появляются «Обратиться в поддержку» и «Исходный код». Блок с копирайтом
    и названием лицензии не трогаем: AGPL требует сохранять уведомление об
    авторских правах, а ссылка на исходники — вторая половина этого
    требования, без неё раздавать сборку нельзя.
    """
    source = path.read_text(encoding="utf-8")
    if "remit-about-links" in source:
        print("Окно «О программе» уже переведено на наши ссылки — пропускаем.")
        return

    for old, new in ABOUT_LINKS:
        target = new.format(site=site_url)
        quoted = f"launchUrlString('{old}');"
        if quoted not in source:
            raise SystemExit(
                f"{path}: не найдена ссылка {old} в окне «О программе». "
                "Исходники RustDesk изменились — обновите скрипт."
            )
        source = source.replace(quoted, f"launchUrlString('{target}');", 1)

    website_block = ABOUT_WEBSITE_ANCHOR.replace("__SITE__", site_url)
    if source.count(website_block) != 1:
        raise SystemExit(
            f"{path}: не найден блок ссылки «Website». "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    extra = f"""
              // remit-about-links: поддержка и исходный код.
              InkWell(
                  onTap: () {{
                    launchUrlString('{support_url}');
                  }},
                  child: Text(
                    translate('Support'),
                    style: linkStyle,
                  ).marginSymmetric(vertical: 4.0)),
              InkWell(
                  onTap: () {{
                    launchUrlString('{source_url}');
                  }},
                  child: Text(
                    translate('Source Code'),
                    style: linkStyle,
                  ).marginSymmetric(vertical: 4.0)),"""

    # Плашка с копирайтом залита синим RustDesk — перекрашиваем в фирменный
    # цвет, сам текст уведомления при этом остаётся нетронутым.
    blue = "const BoxDecoration(color: Color(0xFF2c8cff))"
    if blue in source:
        source = source.replace(blue, "const BoxDecoration(color: Color(0xFF0D9488))", 1)

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(source.replace(website_block, website_block + extra, 1), encoding="utf-8")
    print(f"Окно «О программе» переведено на ссылки {site_url}")


# Оставшиеся ссылки на rustdesk.com в интерфейсе: окно установки, настройки
# на телефоне и предложение скачать новую версию. Правим адрес и видимый текст,
# иначе пользователь из нашей программы попадает на чужой сайт.
SITE_LINKS: list[tuple[str, str]] = [
    ("https://rustdesk.com/privacy.html", "{site}/dokumenty/politika"),
    ("https://rustdesk.com/download", "{site}/skachat"),
    ("https://rustdesk.com/pricing", "{site}/tarify"),
    ("https://rustdesk.com/", "{site}"),
]

SITE_LINK_FILES = [
    "flutter/lib/desktop/pages/install_page.dart",
    "flutter/lib/desktop/pages/connection_page.dart",
    "flutter/lib/mobile/pages/settings_page.dart",
    "flutter/lib/mobile/pages/connection_page.dart",
]


def retarget_site_links(root: Path, site_url: str, domain: str) -> None:
    """Переводит оставшиеся ссылки интерфейса на наш сайт.

    Ссылки на документацию (rustdesk.com/docs/...) не трогаем: там описаны
    настройки Linux, своей такой страницы у нас нет, и вести пользователя в
    никуда хуже, чем в чужую, но рабочую документацию.
    """
    total = 0
    for relative in SITE_LINK_FILES:
        path = root / relative
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        original = source
        for old, template in SITE_LINKS:
            source = source.replace(old, template.format(site=site_url))
        # Видимая подпись ссылки — тот же адрес, но без схемы.
        source = source.replace("Text('rustdesk.com'", f"Text('{domain}'")
        if source != original:
            path.write_text(source, encoding="utf-8")
            total += 1
    print(f"Ссылки интерфейса переведены на {site_url}: файлов — {total}")


# Тексты подписи под окном. Ключ powered_by_me есть во всех переводах, поэтому
# меняем значение — так надпись остаётся переводимой.
POWERED_TEXT_RU = "Что-то не так? Обратитесь в поддержку"
POWERED_TEXT_EN = "Something wrong? Contact support"

# Строка вида `        ("ключ", "значение"),` — правим только значение,
# иначе поломаются ключи вроде "About RustDesk", по которым идёт поиск.
LANG_LINE = re.compile(
    r'^(\s*\("(?:[^"\\]|\\.)*",\s*")((?:[^"\\]|\\.)*)("\),?\s*)$',
    re.MULTILINE,
)
POWERED_LINE = re.compile(r'^(\s*\("powered_by_me",\s*")(?:[^"\\]|\\.)*("\),?\s*)$', re.MULTILINE)


def rebrand_lang_strings(root: Path, app_name: str) -> None:
    """Убирает RustDesk из переводов и меняет подпись под главным окном.

    Заменяем только значения: ключ — это английский оригинал, по нему
    translate() ищет строку, и переименование ключа просто выключило бы
    перевод.
    """
    lang_dir = root / "src" / "lang"
    if not lang_dir.is_dir():
        print(f"Пропускаю переводы: не найден {lang_dir}")
        return

    total = 0
    for path in sorted(lang_dir.glob("*.rs")):
        source = path.read_text(encoding="utf-8")
        original = source

        text = POWERED_TEXT_RU if path.stem in {"ru", "be", "kz"} else POWERED_TEXT_EN
        source = POWERED_LINE.sub(lambda m: f"{m.group(1)}{text}{m.group(2)}", source)

        # Ключи, которых у RustDesk нет: добавляем русские значения для новых
        # ссылок в окне «О программе». В остальных языках translate() вернёт
        # сам ключ — английский текст, и это допустимый запасной вариант.
        if path.stem == "ru" and '("Source Code"' not in source:
            source = POWERED_LINE.sub(
                lambda m: m.group(0)
                + '\n        ("Support", "Поддержка"),'
                + '\n        ("Source Code", "Исходный код"),',
                source,
                count=1,
            )

        def value_only(match: re.Match[str]) -> str:
            return match.group(1) + match.group(2).replace("RustDesk", app_name) + match.group(3)

        source = LANG_LINE.sub(value_only, source)

        if source != original:
            path.write_text(source, encoding="utf-8")
            total += 1
    print(f"Переводы поправлены: файлов — {total}")


STATUS_IMPORT_ANCHOR = "import 'package:flutter_hbb/models/state_model.dart';"
STATUS_IMPORT = "import 'package:flutter_hbb/remit_status.dart';"

# Куда встраивать карточку: экран компьютера и экран телефона.
STATUS_TARGETS = [
    (
        Path("flutter/lib/desktop/pages/desktop_home_page.dart"),
        "      if (!isOutgoingOnly) buildPasswordBoard(context),",
        "      const RemITStatusCard(),",
    ),
    (
        Path("flutter/lib/mobile/pages/connection_page.dart"),
        "          _buildRemoteIDTextField(),",
        "          const RemITStatusCard(),",
    ),
]


def write_status_widget(root: Path, site_url: str) -> None:
    """Кладёт в сборку файл с карточкой тарифа."""
    template = Path(__file__).with_name("remit_status.dart")
    if not template.is_file():
        raise SystemExit(f"Не найден шаблон карточки: {template}")

    target = root / "flutter" / "lib" / "remit_status.dart"
    target.write_text(
        template.read_text(encoding="utf-8").replace("__SITE_URL__", site_url),
        encoding="utf-8",
    )
    print(f"Карточка тарифа добавлена: {target}")


# Оформление интерфейса: палитра RustDesk меняется на палитру сайта.
# Одних акцентов мало — синий RustDesk и наш синий почти неразличимы, поэтому
# меняем ещё и фон, карточки, поля ввода и границы: именно они задают
# впечатление «это другая программа».
THEME_REPLACEMENTS: list[tuple[str, str, str]] = [
    # --- акценты: бирюза вместо синего RustDesk ---
    # accent тёмный настолько, чтобы белый текст на кнопке читался;
    # idColor яркий — он рисуется текстом на тёмной карточке.
    ("accent", "static const Color accent = Color(0xFF0071FF);",
     "static const Color accent = Color(0xFF0D9488);"),
    ("accent50", "static const Color accent50 = Color(0x770071FF);",
     "static const Color accent50 = Color(0x770D9488);"),
    ("accent80", "static const Color accent80 = Color(0xAA0071FF);",
     "static const Color accent80 = Color(0xAA0D9488);"),
    ("idColor", "static const Color idColor = Color(0xFF00B6F0);",
     "static const Color idColor = Color(0xFF2DD4BF);"),
    ("button", "static const Color button = Color(0xFF2C8CFF);",
     "static const Color button = Color(0xFF14B8A6);"),
    ("canvasColor", "static const Color canvasColor = Color(0xFF212121);",
     "static const Color canvasColor = Color(0xFF0C0E10);"),
    # --- тёмная тема: нейтральный графит вместо синеватого серого ---
    ("тёмный фон", "scaffoldBackgroundColor: Color(0xFF18191E),",
     "scaffoldBackgroundColor: Color(0xFF111316),"),
    ("фон диалогов", "dialogBackgroundColor: Color(0xFF18191E),",
     "dialogBackgroundColor: Color(0xFF111316),"),
    ("наведение (тёмная)", "hoverColor: Color.fromARGB(255, 45, 46, 53),",
     "hoverColor: Color(0xFF22262B),"),
    ("карточки", "cardColor: Color(0xFF24252B),",
     "cardColor: Color(0xFF1A1D21),"),
    ("поля ввода", "fillColor: Color(0xFF24252B),",
     "fillColor: Color(0xFF1A1D21),"),
    ("рамка диалога", "color: Color(0xFF24252B),",
     "color: Color(0xFF2E333A),"),
    ("границы (тёмная)", "border: Color(0xFF555555),",
     "border: Color(0xFF2E333A),"),
    ("подсветка (тёмная)", "highlight: Color(0xFF3F3F3F),",
     "highlight: Color(0xFF22262B),"),
    # --- светлая тема: холодный светло-серый вместо чистого белого ---
    ("светлый фон", "scaffoldBackgroundColor: Colors.white,",
     "scaffoldBackgroundColor: Color(0xFFF6F7F9),"),
    ("наведение (светлая)", "hoverColor: Color.fromARGB(255, 224, 224, 224),",
     "hoverColor: Color(0xFFE7EAEE),"),
    # --- форма: углы у списков сглажены. Диалоги и поля ввода не трогаем:
    # там те же значения встречаются в нескольких виджетах, и замена вслепую
    # задела бы не то. Вернёмся к ним, когда увидим живой скриншот.
    ("углы списков", """  static const ListTileThemeData listTileTheme = ListTileThemeData(
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.all(
        Radius.circular(5),
      ),
    ),
  );""", """  static const ListTileThemeData listTileTheme = ListTileThemeData(
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.all(
        Radius.circular(10),
      ),
    ),
  );"""),
]

# Шрифт интерфейса. RustDesk рисует системным — на Windows это Segoe UI,
# и именно он сильнее всего выдаёт «это тот же RustDesk». Inter кладём в
# сборку: свободная лицензия, полная кириллица, хорошо читается мелким.
FONT_FAMILY = "Inter"
FONT_WEIGHTS = [("Regular", 400), ("Medium", 500), ("SemiBold", 600), ("Bold", 700)]


def restyle_theme(path: Path) -> None:
    """Перекрашивает интерфейс в фирменную палитру."""
    source = path.read_text(encoding="utf-8")
    changed = 0
    for name, old, new in THEME_REPLACEMENTS:
        count = source.count(old)
        if count != 1:
            raise SystemExit(
                f"{path}: ожидалось одно вхождение цвета «{name}», найдено {count}. "
                "Оформление RustDesk изменилось — обновите скрипт."
            )
        source = source.replace(old, new, 1)
        changed += 1
    path.write_text(source, encoding="utf-8")
    print(f"Интерфейс перекрашен в фирменную палитру: {changed} значени(й)")


def install_status_card(path: Path, widget_anchor: str, widget_line: str) -> None:
    """Встраивает карточку в экран: добавляет импорт и сам виджет."""
    source = path.read_text(encoding="utf-8")
    if widget_line.strip() in source:
        print(f"Карточка уже встроена в {path} — пропускаем.")
        return
    if source.count(STATUS_IMPORT_ANCHOR) != 1 or source.count(widget_anchor) != 1:
        raise SystemExit(
            f"{path}: не найдено место для карточки тарифа. "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")

    source = source.replace(STATUS_IMPORT_ANCHOR, f"{STATUS_IMPORT_ANCHOR}\n{STATUS_IMPORT}", 1)
    source = source.replace(widget_anchor, f"{widget_anchor}\n{widget_line}", 1)
    path.write_text(source, encoding="utf-8")
    print(f"Карточка тарифа встроена в {path}")


MOBILE_UPDATE_ANCHOR = "          if (!bind.isCustomClient() && !isIOS)"
MOBILE_UPDATE_PATCHED = "          // RemIT: обновления показываем и в фирменной сборке.\n          if (!isIOS)"


def enable_mobile_update_card(path: Path) -> None:
    """Показывает предложение обновиться на экране телефона (кроме iOS)."""
    source = path.read_text(encoding="utf-8")
    if MOBILE_UPDATE_PATCHED.split("\n")[1] in source:
        print("Обновления на телефоне уже включены — пропускаем.")
        return
    if source.count(MOBILE_UPDATE_ANCHOR) != 1:
        print(f"Пропускаю обновления на телефоне: не найдено условие в {path}")
        return

    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        backup.write_text(source, encoding="utf-8")
    path.write_text(source.replace(MOBILE_UPDATE_ANCHOR, MOBILE_UPDATE_PATCHED, 1), encoding="utf-8")
    print(f"Предложение обновиться включено на экране телефона: {path}")


def rebrand_visible_strings(root: Path, app_name: str) -> None:
    total = 0
    for relative in BRAND_FILES:
        path = root / relative
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        count = source.count("RustDesk")
        if count == 0:
            continue
        path.write_text(source.replace("RustDesk", app_name), encoding="utf-8")
        total += count
        print(f"  {relative}: заменено вхождений — {count}")
    print(f"Название продукта заменено в видимых строках: {total}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ребрендинг клиента RustDesk под RemIT")
    parser.add_argument("root", type=Path, help="Путь к клону rustdesk/rustdesk")
    parser.add_argument("--app-name", default="RemIT")
    parser.add_argument(
        "--legacy-app-name",
        default="RustDesk,AvitoDoc",
        help="Через запятую: названия прошлых клиентов, чьи настройки переносим",
    )
    parser.add_argument("--id-server", default="remit.su")
    parser.add_argument("--relay-server", default="remit.su")
    parser.add_argument("--api-server", default="https://remit.su")
    parser.add_argument(
        "--support-url",
        default="https://remit.su/kabinet/podderzhka",
        help="Куда ведёт приглашение написать в поддержку",
    )
    parser.add_argument(
        "--source-url",
        default="https://github.com/Anathom1a/rustdesk",
        help="Публичные исходники клиента: требование AGPL-3.0",
    )
    parser.add_argument(
        "--update-url",
        default="https://remit.su/api/version/latest",
        help="Адрес проверки обновлений (маршрут сервера обновлений RemIT)",
    )
    # Ключ открытый: он и так лежит внутри каждого клиента. Держим значением
    # по умолчанию, чтобы сборка не требовала лишних настроек.
    parser.add_argument(
        "--public-key",
        default="0rexVZoXqaUjnIooWsmVscaVgkfLuxlpY7LN73X4UA0=",
        help="Публичный ключ сервера (id_ed25519.pub)",
    )
    parser.add_argument(
        "--brand-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "brand",
        help="Каталог с фирменными иконками и логотипами",
    )
    args = parser.parse_args()

    config_path = args.root / "libs" / "hbb_common" / "src" / "config.rs"
    if not config_path.is_file():
        print(
            f"Не найден {config_path}. Убедитесь, что подмодули получены: "
            "git submodule update --init --recursive",
            file=sys.stderr,
        )
        return 1

    patch_config(config_path, args)
    lock_servers(config_path, args)
    set_default_theme(config_path)

    core_main_path = args.root / "src" / "core_main.rs"
    if core_main_path.is_file():
        add_config_migration(config_path, core_main_path, args.legacy_app_name)

    lib_path = args.root / "libs" / "hbb_common" / "src" / "lib.rs"
    if lib_path.is_file():
        patch_update_url(lib_path, args.update_url)
    else:
        print(f"Пропускаю сервер обновлений: не найден {lib_path}")

    common_path = args.root / "src" / "common.rs"
    if common_path.is_file():
        enable_update_check(common_path)
        disable_custom_client(common_path)
    else:
        print(f"Пропускаю включение проверки обновлений: не найден {common_path}")

    site_url = args.api_server.rstrip("/")

    flutter_common = args.root / "flutter" / "lib" / "common.dart"
    if flutter_common.is_file():
        enable_flutter_update_check(flutter_common)
        make_logo_clickable(flutter_common, site_url)
        replace_powered_by(flutter_common, args.support_url)
        restyle_theme(flutter_common)
    else:
        print(f"Пропускаю проверку обновлений в интерфейсе: не найден {flutter_common}")

    home_page = args.root / "flutter" / "lib" / "desktop" / "pages" / "desktop_home_page.dart"
    if home_page.is_file():
        enable_update_card(home_page, site_url)
    else:
        print(f"Пропускаю карточку обновления: не найден {home_page}")

    settings_page = (
        args.root / "flutter" / "lib" / "desktop" / "pages" / "desktop_setting_page.dart"
    )
    if settings_page.is_file():
        patch_about_dialog(settings_page, site_url, args.support_url, args.source_url)
    else:
        print(f"Пропускаю окно «О программе»: не найден {settings_page}")

    retarget_site_links(args.root, site_url, site_url.split("://")[-1].rstrip("/"))

    mobile_page = args.root / "flutter" / "lib" / "mobile" / "pages" / "connection_page.dart"
    if mobile_page.is_file():
        enable_mobile_update_card(mobile_page)

    if (args.root / "flutter" / "lib").is_dir():
        write_status_widget(args.root, site_url)
        for relative, widget_anchor, widget_line in STATUS_TARGETS:
            target = args.root / relative
            if target.is_file():
                install_status_card(target, widget_anchor, widget_line)
            else:
                print(f"Пропускаю карточку тарифа: не найден {target}")

    runner_main = args.root / "flutter" / "windows" / "runner" / "main.cpp"
    if runner_main.is_file():
        widen_main_window(runner_main)

    portable_main = args.root / "libs" / "portable" / "src" / "main.rs"
    if portable_main.is_file():
        brand_portable_folder(portable_main, args.app_name)

    install_brand_assets(args.root, args.brand_dir)
    install_font(args.root, args.brand_dir)
    rebrand_visible_strings(args.root, args.app_name)
    rebrand_lang_strings(args.root, args.app_name)
    print(
        "\nГотово. Осталось проверить строки установщика и собрать клиент."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
