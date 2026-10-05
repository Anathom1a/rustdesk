// RemIT: состояние тарифа в главном окне клиента.
//
// Файл добавляется в сборку скриптом brand-client.py: он подставляет адрес
// сайта вместо __SITE_URL__ и вставляет карточку на главный экран.
//
// Карточка показывает остаток бесплатного времени на сегодня либо срок
// действия подписки. На компьютерах под управлением (модуль «Управление»)
// в ней же кнопка «Позвать ИТ» (компьютер компании) или «Позвать мастера»
// (клиент компьютерного мастера) — заявка уходит тем, кто обслуживает компьютер.
// Если компьютер ещё никто не обслуживает, в карточке есть «Код от мастера»:
// клиент вводит код, и компьютер попадает под обслуживание. Данные берутся с
// нашего сервера раз в минуту; если связи нет, карточка просто не показывается.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_hbb/models/platform_model.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const String kRemITSite = '__SITE_URL__';
const Duration _kRefreshInterval = Duration(seconds: 60);
const Duration _kRequestTimeout = Duration(seconds: 8);

class RemITStatus {
  const RemITStatus({
    required this.message,
    required this.exhausted,
    required this.alert,
    required this.limitCut,
    required this.usedSeconds,
    required this.limitSeconds,
    required this.linkUrl,
    required this.linkText,
    required this.helpDesk,
    required this.helpDeskProvider,
    required this.helpDeskTitle,
    required this.helpDeskKind,
    required this.joinCode,
  });

  final String message;
  final bool exhausted;
  // Выделить карточку как предупреждение.
  final bool alert;
  // Недавно разорвано подключение из-за лимита одновременных сессий.
  final bool limitCut;
  final int usedSeconds;
  final int? limitSeconds;
  final String linkUrl;
  final String linkText;
  // Компьютер под управлением: в карточке есть кнопка «Позвать ИТ».
  final bool helpDesk;
  // Кто обслуживает компьютер (имя мастера; у ИТ компании пусто).
  final String helpDeskProvider;
  // Подпись кнопки: «Позвать ИТ» (сотрудник компании) или «Позвать мастера» (клиент мастера).
  final String helpDeskTitle;
  // it или master: клиенту мастера окно заявки спрашивает телефон или Telegram.
  final String helpDeskKind;
  // Можно ввести код от мастера.
  final bool joinCode;
}

// Заявку из одного слова мастер не разберёт — просим описать подробнее.
const int _kHelpMessageMin = 10;
// Телефон или Telegram клиента мастера: короче — точно не контакт.
const int _kHelpContactMin = 5;
// Последний указанный контакт — чтобы не вводить его каждый раз.
const String _kHelpContactOption = 'remit-help-contact';

class RemITStatusCard extends StatefulWidget {
  const RemITStatusCard({Key? key}) : super(key: key);

  @override
  State<RemITStatusCard> createState() => _RemITStatusCardState();
}

class _RemITStatusCardState extends State<RemITStatusCard> {
  RemITStatus? _status;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(_kRefreshInterval, (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final apiServer = await bind.mainGetApiServer();
      final base = apiServer.isNotEmpty ? apiServer : kRemITSite;
      final id = await bind.mainGetMyId();
      if (id.isEmpty) {
        return;
      }
      final uuid = await bind.mainGetUuid();

      final response = await http
          .post(
            Uri.parse('$base/api/v1/client/state'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({'id': id, 'uuid': uuid}),
          )
          .timeout(_kRequestTimeout);

      if (response.statusCode != 200) {
        return;
      }

      final data = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      final exhausted = data['exhausted'] == true;
      final cabinet = (data['cabinetUrl'] ?? data['siteUrl'] ?? kRemITSite).toString();
      final tariffs = (data['tariffUrl'] ?? kRemITSite).toString();

      // Ссылку и её подпись сервер присылает сам: так новые поводы для
      // уведомления (например, превышен лимит одновременных сессий) не
      // требуют выпускать новую версию клиента. Поля может не быть у
      // старого сервера — тогда решаем, как раньше.
      final serverLink = (data['linkUrl'] ?? '').toString();
      final serverLinkText = (data['linkText'] ?? '').toString();

      final status = RemITStatus(
        message: (data['message'] ?? '').toString(),
        exhausted: exhausted,
        alert: data['alert'] == true || exhausted,
        limitCut: data['limitCut'] != null,
        usedSeconds: (data['usedSeconds'] as num?)?.toInt() ?? 0,
        limitSeconds: (data['limitSeconds'] as num?)?.toInt(),
        linkUrl: serverLink.isNotEmpty ? serverLink : (exhausted ? tariffs : cabinet),
        linkText: serverLinkText.isNotEmpty
            ? serverLinkText
            : (exhausted ? 'Посмотреть тарифы' : 'Личный кабинет'),
        helpDesk: data['helpDesk'] == true,
        helpDeskProvider: (data['helpDeskProvider'] ?? '').toString(),
        helpDeskTitle: (data['helpDeskTitle'] ?? '').toString().isNotEmpty
            ? data['helpDeskTitle'].toString()
            : 'Позвать ИТ',
        helpDeskKind: (data['helpDeskKind'] ?? 'it').toString(),
        joinCode: data['joinCode'] == true,
      );

      if (mounted) {
        setState(() => _status = status);
      }
    } catch (_) {
      // Сайт недоступен — показывать нечего, работу клиента это не трогает.
    }
  }

  /// «Позвать ИТ» / «Позвать мастера»: человек описывает проблему (клиент
  /// мастера — ещё и телефон или Telegram), заявка уходит в кабинет и в
  /// Telegram тем, кто обслуживает этот компьютер.
  Future<void> _callIt() async {
    final controller = TextEditingController();
    // Клиенту мастера: как с ним связаться, пока мастер не подключился.
    final askContact = _status?.helpDeskKind == 'master';
    final contactController = TextEditingController(
        text: askContact ? bind.mainGetLocalOption(key: _kHelpContactOption) : '');
    String? result;
    bool sending = false;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(_status?.helpDeskTitle ?? 'Позвать ИТ'),
          content: SizedBox(
            width: 380,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(_status?.helpDeskProvider.isNotEmpty == true
                    ? 'Опишите, что случилось. Заявка уйдёт мастеру «${_status!.helpDeskProvider}» — он увидит сведения о компьютере и подключится.'
                    : 'Опишите, что случилось. Специалист увидит сведения о компьютере и подключится.'),
                const SizedBox(height: 12),
                TextField(
                  controller: controller,
                  autofocus: true,
                  minLines: 3,
                  maxLines: 6,
                  maxLength: 1000,
                  decoration: const InputDecoration(hintText: 'Например: не печатает принтер в бухгалтерии'),
                ),
                if (askContact)
                  TextField(
                    controller: contactController,
                    maxLength: 100,
                    keyboardType: TextInputType.phone,
                    decoration: const InputDecoration(
                      labelText: 'Телефон или Telegram',
                      hintText: 'Например: +7 900 123-45-67 или @ivan',
                    ),
                  ),
                if (result != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(result!),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Закрыть'),
            ),
            ElevatedButton(
              onPressed: sending
                  ? null
                  : () async {
                      final text = controller.text.trim();
                      if (text.replaceAll(RegExp(r'\s+'), ' ').length < _kHelpMessageMin) {
                        setDialogState(() => result = 'Опишите, что случилось, хотя бы парой слов — так мастер быстрее поможет.');
                        return;
                      }
                      final contact = contactController.text.trim();
                      if (askContact && contact.length < _kHelpContactMin) {
                        setDialogState(() => result = 'Укажите телефон или Telegram — так мастер сможет сразу с вами связаться.');
                        return;
                      }
                      setDialogState(() => sending = true);
                      final answer = await _sendHelp(text, askContact ? contact : null);
                      if (answer.$1 && askContact) {
                        await bind.mainSetLocalOption(key: _kHelpContactOption, value: contact);
                      }
                      setDialogState(() {
                        sending = false;
                        result = answer.$2;
                        if (answer.$1) controller.clear();
                      });
                    },
              child: Text(sending ? 'Отправляем…' : 'Отправить'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
    contactController.dispose();
  }

  /// «Код от мастера»: клиент вводит код, который мастер прислал ему
  /// (например, в чат), — и компьютер попадает под обслуживание.
  Future<void> _enterCode() async {
    final controller = TextEditingController();
    String? result;
    bool sending = false;
    bool done = false;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Код от мастера'),
          content: SizedBox(
            width: 380,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Введите код, который прислал ваш компьютерный мастер. После этого в программе появится кнопка «Позвать мастера».'),
                const SizedBox(height: 12),
                if (!done)
                  TextField(
                    controller: controller,
                    autofocus: true,
                    textCapitalization: TextCapitalization.characters,
                    maxLength: 12,
                    decoration: const InputDecoration(hintText: 'Например: K7QM-4PZ2'),
                  ),
                if (result != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(result!),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(done ? 'Готово' : 'Закрыть'),
            ),
            if (!done)
              ElevatedButton(
                onPressed: sending
                    ? null
                    : () async {
                        final code = controller.text.trim();
                        if (code.replaceAll(RegExp(r'[^0-9A-Za-z]'), '').length != 8) {
                          setDialogState(() => result = 'В коде 8 букв и цифр — проверьте его.');
                          return;
                        }
                        setDialogState(() => sending = true);
                        final answer = await _post('/api/v1/client/join', {'code': code});
                        setDialogState(() {
                          sending = false;
                          done = answer.$1;
                          result = answer.$2;
                        });
                        if (answer.$1) _load();
                      },
                child: Text(sending ? 'Проверяем…' : 'Подключить'),
              ),
          ],
        ),
      ),
    );
    controller.dispose();
  }

  Future<(bool, String)> _sendHelp(String message, String? contact) async {
    final answer = await _post('/api/v1/client/help', {
      'message': message,
      if (contact != null) 'contact': contact,
    });
    return (answer.$1, answer.$1 && answer.$2.isEmpty ? 'Заявка отправлена.' : answer.$2);
  }

  /// Запрос к сайту от имени этого компьютера (ID и uuid).
  Future<(bool, String)> _post(String path, Map<String, String> fields) async {
    try {
      final apiServer = await bind.mainGetApiServer();
      final base = apiServer.isNotEmpty ? apiServer : kRemITSite;
      final id = await bind.mainGetMyId();
      final uuid = await bind.mainGetUuid();
      final response = await http
          .post(
            Uri.parse('$base$path'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({'id': id, 'uuid': uuid, ...fields}),
          )
          .timeout(_kRequestTimeout);
      final data = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      if (response.statusCode == 200) {
        return (true, (data['message'] ?? '').toString());
      }
      return (false, (data['error'] ?? 'Не получилось. Попробуйте ещё раз.').toString());
    } catch (_) {
      return (false, 'Нет связи с сервером. Попробуйте ещё раз.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    if (status == null || status.message.isEmpty) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    final accent = status.alert ? const Color(0xFFE05B5B) : theme.colorScheme.primary;
    final limit = status.limitSeconds;
    final double? progress =
        (limit != null && limit > 0) ? (status.usedSeconds / limit).clamp(0.0, 1.0).toDouble() : null;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: accent.withOpacity(0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                status.limitCut
                    ? Icons.link_off
                    : (status.exhausted ? Icons.hourglass_bottom : Icons.schedule),
                size: 18,
                color: accent,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  status.message,
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
          if (progress != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  backgroundColor: accent.withOpacity(0.15),
                  valueColor: AlwaysStoppedAnimation<Color>(accent),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: InkWell(
              onTap: () => launchUrl(Uri.parse(status.linkUrl)),
              child: Text(
                status.linkText,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: accent,
                  decoration: TextDecoration.underline,
                ),
              ),
            ),
          ),
          if (status.helpDesk) ...[
            if (status.helpDeskProvider.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  'Ваш мастер: «${status.helpDeskProvider}»',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: OutlinedButton.icon(
                onPressed: _callIt,
                icon: const Icon(Icons.support_agent, size: 18),
                label: Text(status.helpDeskTitle),
              ),
            ),
          ],
          if (!status.helpDesk && status.joinCode)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: InkWell(
                onTap: _enterCode,
                child: Text(
                  'Есть код от мастера?',
                  style: theme.textTheme.bodySmall?.copyWith(decoration: TextDecoration.underline),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
