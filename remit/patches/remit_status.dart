// RemIT: состояние тарифа в главном окне клиента.
//
// Файл добавляется в сборку скриптом brand-client.py: он подставляет адрес
// сайта вместо __SITE_URL__ и вставляет карточку на главный экран.
//
// Карточка показывает остаток бесплатного времени на сегодня либо срок
// действия подписки. Данные берутся с нашего сервера раз в минуту; если связи
// нет, карточка просто не показывается.

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
    required this.usedSeconds,
    required this.limitSeconds,
    required this.linkUrl,
    required this.linkText,
  });

  final String message;
  final bool exhausted;
  final int usedSeconds;
  final int? limitSeconds;
  final String linkUrl;
  final String linkText;
}

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

      final status = RemITStatus(
        message: (data['message'] ?? '').toString(),
        exhausted: exhausted,
        usedSeconds: (data['usedSeconds'] as num?)?.toInt() ?? 0,
        limitSeconds: (data['limitSeconds'] as num?)?.toInt(),
        linkUrl: exhausted ? tariffs : cabinet,
        linkText: exhausted ? 'Посмотреть тарифы' : 'Личный кабинет',
      );

      if (mounted) {
        setState(() => _status = status);
      }
    } catch (_) {
      // Сайт недоступен — показывать нечего, работу клиента это не трогает.
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = _status;
    if (status == null || status.message.isEmpty) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    final accent = status.exhausted ? const Color(0xFFE05B5B) : theme.colorScheme.primary;
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
                status.exhausted ? Icons.hourglass_bottom : Icons.schedule,
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
        ],
      ),
    );
  }
}
