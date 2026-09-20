#!/usr/bin/env python3
"""Превращает исходники RustDesk в фирменный клиент СвязьDesk.

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

Файлы переводов (src/lang/*.rs) намеренно не трогаем: RustDesk сам подставляет
название продукта во время работы, а переименование в этих файлах сломало бы
ключи переводов вроде «About RustDesk».

Использование:
    python3 brand-client.py /path/to/rustdesk \
        --app-name SvyazDesk \
        --id-server id.svyazdesk.ru \
        --relay-server relay.svyazdesk.ru \
        --api-server https://svyazdesk.ru \
        --update-url https://svyazdesk.ru/api/version/latest \
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
    marker = "// СвязьDesk: подмена серверов через custom.txt запрещена."
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
    // СвязьDesk: фирменная сборка проверяет обновления на своём сервере.
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
    // СвязьDesk: фирменная сборка тоже проверяет обновления при запуске.
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

CARD_PATCHED = """    // СвязьDesk: предложение обновиться показываем и в фирменной сборке.
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
    if "svyazdesk-logo-link" in source:
        print("Ссылка на сайте с логотипа уже добавлена — пропускаем.")
        return
    if source.count(LOGO_ANCHOR) != 1:
        raise SystemExit(
            f"{path}: не найден виджет логотипа. "
            "Исходники RustDesk изменились — обновите скрипт."
        )

    replacement = f"""          // svyazdesk-logo-link: по нажатию открываем сайт продукта.
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


STATUS_IMPORT_ANCHOR = "import 'package:flutter_hbb/models/state_model.dart';"
STATUS_IMPORT = "import 'package:flutter_hbb/svyazdesk_status.dart';"

# Куда встраивать карточку: экран компьютера и экран телефона.
STATUS_TARGETS = [
    (
        Path("flutter/lib/desktop/pages/desktop_home_page.dart"),
        "      if (!isOutgoingOnly) buildPasswordBoard(context),",
        "      const SvyazDeskStatusCard(),",
    ),
    (
        Path("flutter/lib/mobile/pages/connection_page.dart"),
        "          _buildRemoteIDTextField(),",
        "          const SvyazDeskStatusCard(),",
    ),
]


def write_status_widget(root: Path, site_url: str) -> None:
    """Кладёт в сборку файл с карточкой тарифа."""
    template = Path(__file__).with_name("svyazdesk_status.dart")
    if not template.is_file():
        raise SystemExit(f"Не найден шаблон карточки: {template}")

    target = root / "flutter" / "lib" / "svyazdesk_status.dart"
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
    # --- акценты ---
    ("accent", "static const Color accent = Color(0xFF0071FF);",
     "static const Color accent = Color(0xFF3B7BFA);"),
    ("accent50", "static const Color accent50 = Color(0x770071FF);",
     "static const Color accent50 = Color(0x773B7BFA);"),
    ("accent80", "static const Color accent80 = Color(0xAA0071FF);",
     "static const Color accent80 = Color(0xAA3B7BFA);"),
    ("idColor", "static const Color idColor = Color(0xFF00B6F0);",
     "static const Color idColor = Color(0xFF2FD8E6);"),
    ("button", "static const Color button = Color(0xFF2C8CFF);",
     "static const Color button = Color(0xFF5F9BFF);"),
    ("canvasColor", "static const Color canvasColor = Color(0xFF212121);",
     "static const Color canvasColor = Color(0xFF080B14);"),
    # --- тёмная тема: серый RustDesk меняем на холодный ink с сайта ---
    ("тёмный фон", "scaffoldBackgroundColor: Color(0xFF18191E),",
     "scaffoldBackgroundColor: Color(0xFF0B101C),"),
    ("фон диалогов", "dialogBackgroundColor: Color(0xFF18191E),",
     "dialogBackgroundColor: Color(0xFF0B101C),"),
    ("наведение (тёмная)", "hoverColor: Color.fromARGB(255, 45, 46, 53),",
     "hoverColor: Color(0xFF17233A),"),
    ("карточки", "cardColor: Color(0xFF24252B),",
     "cardColor: Color(0xFF101829),"),
    ("поля ввода", "fillColor: Color(0xFF24252B),",
     "fillColor: Color(0xFF101829),"),
    ("рамка диалога", "color: Color(0xFF24252B),",
     "color: Color(0xFF1B2740),"),
    ("границы (тёмная)", "border: Color(0xFF555555),",
     "border: Color(0xFF1B2740),"),
    ("подсветка (тёмная)", "highlight: Color(0xFF3F3F3F),",
     "highlight: Color(0xFF17233A),"),
    # --- светлая тема: лёгкий холодный оттенок вместо чистого белого ---
    ("светлый фон", "scaffoldBackgroundColor: Colors.white,",
     "scaffoldBackgroundColor: Color(0xFFF4F7FD),"),
    ("наведение (светлая)", "hoverColor: Color.fromARGB(255, 224, 224, 224),",
     "hoverColor: Color(0xFFE3EAF7),"),
]


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
MOBILE_UPDATE_PATCHED = "          // СвязьDesk: обновления показываем и в фирменной сборке.\n          if (!isIOS)"


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
    parser = argparse.ArgumentParser(description="Ребрендинг клиента RustDesk под СвязьDesk")
    parser.add_argument("root", type=Path, help="Путь к клону rustdesk/rustdesk")
    parser.add_argument("--app-name", default="SvyazDesk")
    parser.add_argument("--id-server", default="id.svyazdesk.ru")
    parser.add_argument("--relay-server", default="relay.svyazdesk.ru")
    parser.add_argument("--api-server", default="https://svyazdesk.ru")
    parser.add_argument(
        "--update-url",
        default="https://svyazdesk.ru/api/version/latest",
        help="Адрес проверки обновлений (маршрут сервера обновлений СвязьDesk)",
    )
    parser.add_argument("--public-key", required=True, help="Публичный ключ hbbs (id_ed25519.pub)")
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
        restyle_theme(flutter_common)
    else:
        print(f"Пропускаю проверку обновлений в интерфейсе: не найден {flutter_common}")

    home_page = args.root / "flutter" / "lib" / "desktop" / "pages" / "desktop_home_page.dart"
    if home_page.is_file():
        enable_update_card(home_page, site_url)
    else:
        print(f"Пропускаю карточку обновления: не найден {home_page}")

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
    rebrand_visible_strings(args.root, args.app_name)
    print(
        "\nГотово. Осталось проверить строки установщика и собрать клиент."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
