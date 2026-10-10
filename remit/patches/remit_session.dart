// RemIT: остаток бесплатного времени на панели окна сеанса.
//
// Файл добавляется в сборку скриптом brand-client.py (подставляет адрес сайта
// вместо __SITE_URL__) и встаёт на верхнюю панель окна удалённого доступа
// рядом с кнопкой «Завершить».
//
// Раньше о лимите напоминали только всплывающие сообщения за 30, 10 и 1
// минуту. Теперь остаток виден всё время, пока идёт сеанс: «42 мин».
// За 10 минут до конца значок жёлтый, за минуту — красный. По нажатию
// открывается страница тарифов. На подписке без лимита значка нет.
//
// Данные — тот же /api/v1/client/state, что и у карточки на главном экране,
// раз в минуту. Между запросами остаток уменьшается сам: таймер идёт, пока
// открыт сеанс, — так считает и сервер.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_hbb/models/platform_model.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const String kRemITSessionSite = '__SITE_URL__';
const Duration _kSessionRefresh = Duration(seconds: 60);
const Duration _kSessionTick = Duration(seconds: 15);
const Duration _kSessionTimeout = Duration(seconds: 8);

class RemITSessionTime extends StatefulWidget {
  const RemITSessionTime({super.key, this.compact = false});

  /// Панель прижата к левому или правому краю: значок узкий, в две строки.
  final bool compact;

  @override
  State<RemITSessionTime> createState() => _RemITSessionTimeState();
}

class _RemITSessionTimeState extends State<RemITSessionTime> {
  int? _remaining;
  String _tariffUrl = '$kRemITSessionSite/tarify';
  DateTime _loadedAt = DateTime.now();
  Timer? _refresh;
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _load();
    _refresh = Timer.periodic(_kSessionRefresh, (_) => _load());
    _tick = Timer.periodic(_kSessionTick, (_) {
      if (mounted && _remaining != null) setState(() {});
    });
  }

  @override
  void dispose() {
    _refresh?.cancel();
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final apiServer = await bind.mainGetApiServer();
      final base = apiServer.isNotEmpty ? apiServer : kRemITSessionSite;
      final id = await bind.mainGetMyId();
      if (id.isEmpty) return;
      final uuid = await bind.mainGetUuid();
      final response = await http
          .post(
            Uri.parse('$base/api/v1/client/state'),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode({'id': id, 'uuid': uuid}),
          )
          .timeout(_kSessionTimeout);
      if (response.statusCode != 200 || !mounted) return;
      final data = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      setState(() {
        _remaining = data['unlimited'] == true
            ? null
            : (data['remainingSeconds'] as num?)?.toInt();
        _tariffUrl = (data['tariffUrl'] ?? _tariffUrl).toString();
        _loadedAt = DateTime.now();
      });
    } catch (_) {
      // Нет связи — значок просто не показываем, сеансу это не мешает.
    }
  }

  /// Остаток с поправкой на время с последнего ответа сервера.
  int? get _left {
    final remaining = _remaining;
    if (remaining == null) return null;
    final passed = DateTime.now().difference(_loadedAt).inSeconds;
    return (remaining - passed).clamp(0, remaining).toInt();
  }

  static String _text(int seconds) {
    final minutes = (seconds / 60).ceil();
    if (minutes >= 60) {
      final hours = minutes ~/ 60;
      final rest = minutes % 60;
      return rest == 0 ? '$hours ч' : '$hours ч $rest мин';
    }
    return '$minutes мин';
  }

  @override
  Widget build(BuildContext context) {
    final left = _left;
    if (left == null) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final Color color = left <= 60
        ? const Color(0xFFFB6F6F)
        : left <= 600
            ? const Color(0xFFF7BF4A)
            : theme.colorScheme.primary;
    final text = _text(left);
    final label = widget.compact
        ? Text(
            text.replaceAll(' мин', '\nмин').replaceAll(' ч', '\nч'),
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 10, height: 1.1, fontWeight: FontWeight.w600, color: color),
          )
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.schedule, size: 15, color: color),
              const SizedBox(width: 5),
              Text(
                text,
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  color: color,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ],
          );

    return Tooltip(
      message: left == 0
          ? 'Бесплатное время на сегодня закончилось. Без лимита — с подпиской.'
          : 'Осталось бесплатного времени на сегодня. Без лимита — с подпиской.',
      child: InkWell(
        borderRadius: BorderRadius.circular(9),
        onTap: () => launchUrl(Uri.parse(_tariffUrl)),
        child: Container(
          height: widget.compact ? 36 : 32,
          width: widget.compact ? 32 : null,
          margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          padding: EdgeInsets.symmetric(horizontal: widget.compact ? 0 : 10),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: color.withOpacity(0.12),
            borderRadius: BorderRadius.circular(9),
            border: Border.all(color: color.withOpacity(0.45)),
          ),
          child: label,
        ),
      ),
    );
  }
}
