/// 자동 연구: 서버가 켜져 있는 동안 계속 팀을 만들고 싸워 보며 찾은 결과를 보여 준다.
import 'dart:async';

import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../widgets.dart';
import '../main.dart';
import 'parties_page.dart';

const _buckets = <(String, String)>[
  ('', '전체'),
  ('meta', '메타 중심'),
  ('balanced', '균형'),
  ('unique', '독창적'),
];
const _archetypes = {
  '': '모든 전략',
  'balance': '균형형',
  'tailwind': '순풍',
  'trickroom': '트릭룸',
  'rain': '비',
  'sun': '쾌청',
  'sand': '모래바람',
  'snow': '눈',
  'psychic': '사이코필드',
  'setup': '랭크업',
};
const _intensities = <(String, String, String)>[
  ('low', '낮게', '다른 작업에 방해가 덜 되게 천천히 연구합니다.'),
  ('normal', '보통', '쉬는 시간을 줄이고 세대마다 더 많은 팀을 시험합니다.'),
  ('max', '최대', 'CPU를 최대한 써서 쉬지 않고 연구합니다.'),
];

class ResearchPage extends ConsumerStatefulWidget {
  const ResearchPage({super.key});

  @override
  ConsumerState<ResearchPage> createState() => _ResearchPageState();
}

class _ResearchPageState extends ConsumerState<ResearchPage> {
  Json? status;
  List<Json>? teams;
  Json? insights;
  String? error;
  String bucket = '';
  String archetype = '';
  Timer? _poll;
  int _ticks = 0;

  @override
  void initState() {
    super.initState();
    _refresh(all: true);
    _poll = Timer.periodic(const Duration(seconds: 3), (_) {
      _ticks++;
      _refresh(all: _ticks % 5 == 0);
    });
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  String get _format => ref.read(formatProvider);

  Future<void> _refresh({bool all = false}) async {
    try {
      final s = (await dio.get('/api/research/status', queryParameters: {'format': _format})).data as Json;
      Json? t, i;
      if (all || teams == null) {
        t = (await dio.get('/api/research/teams', queryParameters: {
          'format': _format,
          if (bucket.isNotEmpty) 'bucket': bucket,
          if (archetype.isNotEmpty) 'archetype': archetype,
          'limit': 20,
        }))
            .data as Json;
        i = (await dio.get('/api/research/insights', queryParameters: {'format': _format})).data as Json;
      }
      if (!mounted) return;
      setState(() {
        status = s;
        if (t != null) teams = (t['teams'] as List).cast<Json>();
        if (i != null) insights = i;
        error = null;
      });
    } catch (_) {
      if (mounted) setState(() => error = '연구 상태를 불러오지 못했습니다. 서버 연결을 확인해 주세요.');
    }
  }

  Future<void> _control({bool? running, String? intensity}) async {
    try {
      await dio.post('/api/research/control', data: {
        if (running != null) 'running': running,
        if (intensity != null) 'intensity': intensity,
      });
    } finally {
      await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(formatProvider, (_, __) {
      teams = null;
      _refresh(all: true);
    });
    final format = ref.watch(formatProvider);
    final theme = Theme.of(context);
    final s = status;
    return PageBody(children: [
      PageHeader('자동 연구',
          glyph: LabGlyph.spark,
          subtitle: format == 'Doubles' ? '더블배틀' : '싱글배틀'),
      Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Text(
            '앱 서버가 켜져 있는 동안 팀을 계속 새로 만들고, 바꾸고, 섞어서 매번 새로운 상대와 싸워 봅니다. '
            '결과는 쌓여서 오래 연구할수록 더 강하고 다양한 팀이 남고, 팀 자동 구성도 여기서 찾은 팀을 출발점으로 씁니다.',
            style: theme.textTheme.bodyMedium),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(error!, style: TextStyle(color: theme.colorScheme.error)),
        ),
      if (s != null) ResearchStatusCard(status: s, onControl: _control),
      Section('발견한 팀',
          subtitle: '판 수가 많아 믿을 만한 성적(하한 신뢰구간) 순서입니다',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
              for (final (key, label) in _buckets)
                ChoiceChip(
                  label: Text(label),
                  selected: bucket == key,
                  onSelected: (_) {
                    setState(() => bucket = key);
                    _refresh(all: true);
                  },
                ),
              DropdownButton<String>(
                value: archetype,
                icon: const LabIcon(LabGlyph.down, size: 17),
                items: [
                  for (final e in _archetypes.entries) DropdownMenuItem(value: e.key, child: Text(e.value)),
                ],
                onChanged: (v) {
                  setState(() => archetype = v ?? '');
                  _refresh(all: true);
                },
              ),
            ]),
            const SizedBox(height: 10),
            if (teams == null)
              const Text('불러오는 중…')
            else if (teams!.isEmpty)
              const Text('아직 충분히 검증된 팀이 없습니다. 연구가 진행되면 여기에 나타납니다 (팀마다 40판 이상).'),
          ])),
      for (final team in teams ?? const <Json>[])
        PartyCard(party: team, key: ValueKey(('research', team['id']))),
      if (insights != null) ResearchInsights(insights!),
    ]);
  }
}

class ResearchStatusCard extends StatelessWidget {
  const ResearchStatusCard({super.key, required this.status, required this.onControl});
  final Json status;
  final Future<void> Function({bool? running, String? intensity}) onControl;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final running = status['running'] == true;
    final busy = status['busy'] == true;
    final intensity = status['intensity'] as String? ?? 'low';
    final events = (status['events'] as List? ?? const []).cast<Json>();
    final uptime = (status['uptime'] as num? ?? 0).round();
    Widget stat(String label, Object value) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(color: cs.surfaceContainerHigh, borderRadius: BorderRadius.circular(12)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(label, style: theme.textTheme.bodySmall),
            Text('$value',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.w800, fontFeatures: [FontFeature.tabularFigures()])),
          ]),
        );
    return Section(
      '연구 상태',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _Pulse(active: running && !busy),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              running ? (status['activity'] as String? ?? '') : '연구가 꺼져 있습니다',
              style: theme.textTheme.titleSmall,
            ),
          ),
          Switch(value: running, onChanged: (v) => onControl(running: v)),
        ]),
        if (status['error'] != null)
          Text(tr('마지막 오류: {}').replaceFirst('{}', '${status['error']}'),
              style: TextStyle(color: cs.error, fontSize: 12.5)),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          stat('기록된 팀', _thousands(status['teams'] as int? ?? 0)),
          stat('누적 모의전', _thousands(status['battles'] as int? ?? 0)),
          stat('이번 실행 모의전', _thousands(status['sessionBattles'] as int? ?? 0)),
          stat('이번 실행 세대', status['generation'] ?? 0),
          stat('채운 틈새', '${status['niches'] ?? 0}/27'),
          if (running) stat('실행 시간', tr('{}분').replaceFirst('{}', '${uptime ~/ 60}')),
        ]),
        const SizedBox(height: 12),
        Text('연구 세기', style: theme.textTheme.titleSmall),
        const SizedBox(height: 5),
        Wrap(spacing: 8, runSpacing: 6, children: [
          for (final (key, label, _) in _intensities)
            ChoiceChip(
              label: Text(label),
              selected: intensity == key,
              onSelected: (_) => onControl(intensity: key),
            ),
        ]),
        const SizedBox(height: 4),
        Text(_intensities.firstWhere((i) => i.$1 == intensity, orElse: () => _intensities.first).$3,
            style: theme.textTheme.bodySmall),
        if (events.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('최근 발견', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          for (final ev in events.take(6))
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Padding(
                  padding: EdgeInsets.only(top: 2, right: 6),
                  child: LabIcon(LabGlyph.star, size: 13),
                ),
                Expanded(child: Text(ev['text'] as String, style: theme.textTheme.bodySmall)),
              ]),
            ),
        ],
      ]),
    );
  }
}

class ResearchInsights extends StatelessWidget {
  const ResearchInsights(this.data, {super.key});
  final Json data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pairs = (data['pairs'] as List).cast<Json>();
    final species = (data['species'] as List).cast<Json>();
    if (pairs.isEmpty && species.isEmpty) return const SizedBox();
    return Section('연구로 배운 것',
        subtitle: '함께 넣었을 때 각자의 승률로 기대되는 것보다 더 잘 이긴 조합',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final p in pairs)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                Sprite((p['a'] as Json)['sprite'] as String, size: 32),
                Sprite((p['b'] as Json)['sprite'] as String, size: 32),
                const SizedBox(width: 6),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${(p['a'] as Json)['name']} + ${(p['b'] as Json)['name']}'),
                    Text(
                        tr('{} · 기대보다 {}%p · {}판')
                            .replaceFirst('{}', fmtPct(100 * (p['rate'] as num)))
                            .replaceFirst('{}',
                                '${(p['lift'] as num) >= 0 ? '+' : ''}${(100 * (p['lift'] as num)).toStringAsFixed(1)}')
                            .replaceFirst('{}', _thousands(p['games'] as int)),
                        style: theme.textTheme.bodySmall),
                  ]),
                ),
              ]),
            ),
          if (species.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('연구에서 승률이 높은 포켓몬', style: theme.textTheme.titleSmall),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 6, children: [
              for (final s in species)
                Chip(
                  avatar: Sprite(s['sprite'] as String, size: 22),
                  label: Text('${s['name']} ${fmtPct(100 * (s['rate'] as num))}'),
                  visualDensity: VisualDensity.compact,
                ),
            ]),
          ],
        ]));
  }
}

class _Pulse extends StatefulWidget {
  const _Pulse({required this.active});
  final bool active;
  @override
  State<_Pulse> createState() => _PulseState();
}

class _PulseState extends State<_Pulse> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(covariant _Pulse oldWidget) {
    super.didUpdateWidget(oldWidget);
    _sync();
  }

  void _sync() {
    if (widget.active && !MediaQuery.disableAnimationsOf(context)) {
      if (!_c.isAnimating) _c.repeat();
    } else {
      _c
        ..stop()
        ..value = 0;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.active ? const Color(0xFF34C77B) : Theme.of(context).colorScheme.outline;
    return AnimatedBuilder(
      animation: _c,
      builder: (context, _) => SizedBox.square(
        dimension: 22,
        child: Stack(alignment: Alignment.center, children: [
          Container(
            width: 8 + 14 * _c.value,
            height: 8 + 14 * _c.value,
            decoration: BoxDecoration(shape: BoxShape.circle, color: color.withOpacity(.35 * (1 - _c.value))),
          ),
          Container(width: 10, height: 10, decoration: BoxDecoration(shape: BoxShape.circle, color: color)),
        ]),
      ),
    );
  }
}

String _thousands(int n) {
  final s = '$n';
  final out = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) out.write(',');
    out.write(s[i]);
  }
  return out.toString();
}
