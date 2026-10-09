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

    return Container(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 6),
      padding: const EdgeInsets.fromLTRB(16, 12, 10, 16),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: accent.withOpacity(0.4)),
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
