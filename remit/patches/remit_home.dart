// RemIT: карточка «Ваш ID» в левой колонке главного окна.
//
// Файл добавляется в сборку скриптом brand-client.py: он подставляет адрес
// сайта и название программы вместо __SITE_URL__ и __APP_NAME__ и ставит
// карточку на место штатных полей ID и пароля RustDesk.
//
// Зачем своя карточка: у RustDesk ID и пароль — два поля ввода с тонкой
// полоской слева, и человеку, которому помогают, неочевидно, что из этого
// диктовать. Здесь ID крупно и по три цифры (как на сайте), пароль ниже, а
// кнопка «Скопировать ID и пароль» кладёт в буфер готовое сообщение для
// мессенджера: ID, одноразовый пароль и ссылку для подключения.
// Постоянный пароль в сообщение не попадает никогда.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_hbb/common.dart';
import 'package:flutter_hbb/desktop/pages/desktop_setting_page.dart';
import 'package:flutter_hbb/desktop/pages/desktop_tab_page.dart';
import 'package:flutter_hbb/models/platform_model.dart';
import 'package:flutter_hbb/models/server_model.dart';
import 'package:provider/provider.dart';

const String kRemITHomeSite = '__SITE_URL__';
const String kRemITHomeAppName = '__APP_NAME__';

/// Подсветить карточку «Ваш ID» на несколько секунд (окно первого запуска).
final ValueNotifier<bool> remitIdCardHighlight = ValueNotifier(false);

class RemITIdCard extends StatelessWidget {
  const RemITIdCard({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider.value(
      value: gFFI.serverModel,
      child: Consumer<ServerModel>(
        builder: (context, model, _) => _RemITIdCardBody(model: model),
      ),
    );
  }
}

class _RemITIdCardBody extends StatelessWidget {
  const _RemITIdCardBody({required this.model});

  final ServerModel model;

  /// Одноразовый пароль показываем и отдаём в «Скопировать», только когда он
  /// действительно используется — так же решает и штатный экран RustDesk.
  bool get _oneTime =>
      model.approveMode != 'click' &&
      model.verificationMethod != kUsePermanentPassword;

  String _invite(String id, String password) {
    final lines = <String>[
      'Подключитесь ко мне в $kRemITHomeAppName.',
      'ID: $id',
      if (_oneTime && password.isNotEmpty && password != '-') 'Пароль: $password',
      '$kRemITHomeSite/podklyuchit/${id.replaceAll(' ', '')}',
    ];
    return lines.join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = theme.colorScheme.primary;
    final muted = theme.textTheme.titleLarge?.color?.withOpacity(0.55);
    final labelStyle = TextStyle(fontSize: 12, color: muted);

    return ValueListenableBuilder<bool>(
      valueListenable: remitIdCardHighlight,
      builder: (context, highlight, child) => AnimatedContainer(
        duration: const Duration(milliseconds: 350),
        margin: const EdgeInsets.fromLTRB(12, 4, 12, 6),
        padding: const EdgeInsets.fromLTRB(16, 12, 10, 16),
        decoration: BoxDecoration(
          color: theme.cardColor,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: accent.withOpacity(highlight ? 1 : 0.4),
            width: highlight ? 2 : 1,
          ),
          boxShadow: highlight
              ? [BoxShadow(color: accent.withOpacity(0.45), blurRadius: 22, spreadRadius: 1)]
              : const [],
        ),
        child: child,
      ),
      child: ValueListenableBuilder<TextEditingValue>(
        valueListenable: model.serverId,
        builder: (context, idValue, _) => ValueListenableBuilder<TextEditingValue>(
          valueListenable: model.serverPasswd,
          builder: (context, passwordValue, _) {
            final id = idValue.text;
            final password = passwordValue.text;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text('Ваш ID', style: labelStyle)),
                    _SmallIconButton(
                      icon: Icons.tune,
                      tooltip: translate('Settings'),
                      onPressed: () => DesktopTabPage.onAddSetting(),
                    ),
                  ],
                ),
                // ID — самое крупное на экране: именно его диктуют.
                GestureDetector(
                  onDoubleTap: () => _copy(id.replaceAll(' ', ''), translate('Copied')),
                  child: Padding(
                    padding: const EdgeInsets.only(right: 6, bottom: 12),
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(
                        id,
                        maxLines: 1,
                        style: const TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.6,
                          fontFeatures: [FontFeature.tabularFigures()],
                        ),
                      ),
                    ),
                  ),
                ),
                Text(
                  _oneTime ? 'Одноразовый пароль' : 'Пароль задан в настройках',
                  style: labelStyle,
                ),
                Row(
                  children: [
                    Expanded(
                      child: _oneTime
                          ? Text(
                              password,
                              maxLines: 1,
                              style: const TextStyle(
                                fontSize: 17,
                                fontWeight: FontWeight.w500,
                                letterSpacing: 3,
                                fontFamily: 'monospace',
                              ),
                            )
                          : Text('••••••', style: TextStyle(fontSize: 17, color: muted)),
                    ),
                    if (_oneTime)
                      _SmallIconButton(
                        icon: Icons.refresh,
                        tooltip: translate('Refresh Password'),
                        onPressed: () => bind.mainUpdateTemporaryPassword(),
                      ),
                    if (!bind.isDisableSettings())
                      _SmallIconButton(
                        icon: Icons.edit_outlined,
                        tooltip: translate('Change Password'),
                        onPressed: () => DesktopSettingPage.switch2page(SettingsTabKey.safety),
                      ),
                  ],
                ),
                const SizedBox(height: 14),
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: SizedBox(
                    width: double.infinity,
                    height: 36,
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: theme.textTheme.titleLarge?.color,
                        backgroundColor: accent.withOpacity(0.12),
                        side: BorderSide(color: accent.withOpacity(0.55)),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
                        padding: const EdgeInsets.symmetric(horizontal: 10),
                      ),
                      onPressed: id.trim().isEmpty
                          ? null
                          : () => _copy(_invite(id, password), 'Скопировано — вставьте в мессенджер'),
                      icon: Icon(Icons.copy_rounded, size: 16, color: accent),
                      label: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          _oneTime ? 'Скопировать ID и пароль' : 'Скопировать ID',
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                        ),
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.only(top: 8, right: 6),
                  child: Text(
                    'Вставьте в мессенджер тому, кто помогает: там будут ID, пароль и ссылка.',
                    style: TextStyle(fontSize: 11.5, height: 1.35, color: muted),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  static void _copy(String text, String toast) {
    if (text.isEmpty) return;
    Clipboard.setData(ClipboardData(text: text));
    showToast(toast);
  }
}

class _SmallIconButton extends StatelessWidget {
  const _SmallIconButton({required this.icon, required this.tooltip, required this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).textTheme.titleLarge?.color;
    return Tooltip(
      message: tooltip,
      child: InkWell(
        borderRadius: BorderRadius.circular(7),
        onTap: onPressed,
        child: Padding(
          padding: const EdgeInsets.all(5),
          child: Icon(icon, size: 17, color: color?.withOpacity(0.6)),
        ),
      ),
    );
  }
}

/// Название компьютера из адресной книги кабинета («Имя в книге»).
///
/// В «Недавних» и «Избранном» RustDesk показывает только имя, заданное на
/// этом компьютере, а без него — имя Windows вроде DESKTOP-7F3K2. Если своё
/// имя не задано, берём название из адресных книг аккаунта: они загружаются
/// из кеша при запуске и обновляются с сервера. Пусто — названия нет.
String remitAbAlias(String id) {
  for (final book in gFFI.abModel.addressbooks.values) {
    for (final peer in book.peers) {
      if (peer.id == id && peer.alias.trim().isNotEmpty) return peer.alias.trim();
    }
  }
  return '';
}

const String _kWelcomeOption = 'remit-welcome-done';

/// Окно первого запуска: «Что вы хотите сделать?» — помогают вам или
/// подключаетесь вы. Показывается один раз; выбор подсвечивает нужную часть
/// главного окна. Сам виджет ничего не рисует.
class RemITWelcome extends StatefulWidget {
  const RemITWelcome({super.key});

  @override
  State<RemITWelcome> createState() => _RemITWelcomeState();
}

class _RemITWelcomeState extends State<RemITWelcome> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeShow());
  }

  Future<void> _maybeShow() async {
    if (!mounted || bind.mainGetLocalOption(key: _kWelcomeOption) == 'Y') return;
    await bind.mainSetLocalOption(key: _kWelcomeOption, value: 'Y');
    if (!mounted) return;
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => const _WelcomeDialog(),
    );
    if (choice == 'helped') {
      remitIdCardHighlight.value = true;
      showToast('Назовите ID и пароль из карточки слева тому, кто помогает',
          timeout: const Duration(seconds: 6));
      Future.delayed(const Duration(seconds: 6), () => remitIdCardHighlight.value = false);
    } else if (choice == 'helping') {
      showToast('Введите ID того компьютера справа и нажмите «Подключиться»',
          timeout: const Duration(seconds: 6));
    }
  }

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}

class _WelcomeDialog extends StatelessWidget {
  const _WelcomeDialog();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.titleLarge?.color?.withOpacity(0.6);
    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 12),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Что вы хотите сделать?',
                  style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text('Программа одна и та же у обоих — выберите, кто вы сейчас.',
                  style: TextStyle(fontSize: 13, color: muted)),
              const SizedBox(height: 20),
              _WelcomeChoice(
                icon: Icons.front_hand_outlined,
                title: 'Мне помогают',
                text: 'Кто-то подключится к этому компьютеру. Покажем, какие ID и пароль ему назвать.',
                onTap: () => Navigator.of(context).pop('helped'),
              ),
              const SizedBox(height: 12),
              _WelcomeChoice(
                icon: Icons.desktop_windows_outlined,
                title: 'Я подключаюсь',
                text: 'Помогаете кому-то или заходите на свой компьютер издалека.',
                onTap: () => Navigator.of(context).pop('helping'),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Разберусь сам'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WelcomeChoice extends StatelessWidget {
  const _WelcomeChoice({required this.icon, required this.title, required this.text, required this.onTap});

  final IconData icon;
  final String title;
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = theme.colorScheme.primary;
    return Material(
      color: theme.cardColor,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: accent.withOpacity(0.45)),
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: accent.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: accent),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 3),
                    Text(text,
                        style: TextStyle(
                            fontSize: 12.5,
                            height: 1.35,
                            color: theme.textTheme.titleLarge?.color?.withOpacity(0.65))),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
