import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../main.dart';
import '../settings.dart';
import '../team_state.dart';
import '../widgets.dart';

final _speedTopProvider = StateProvider<int>((ref) => 60);

final speedTierProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  final top = ref.watch(_speedTopProvider);
  final team = ref.watch(teamProvider);
  return (await dio.post('/api/speed', data: {
    'format': fmt,
    'topN': top,
    'team': [for (final s in team) s.set],
  }))
      .data as Json;
});

/// 스피드 티어: 메타 상위권의 실전 스피드(주력 세트 기준)와 내 팀을 한 줄에 놓고 본다.
class SpeedPage extends ConsumerStatefulWidget {
  const SpeedPage({super.key});
  @override
  ConsumerState<SpeedPage> createState() => _SpeedPageState();
}

class _SpeedPageState extends ConsumerState<SpeedPage> {
  bool tailwind = false; // 내 팀 ×2
  bool trickRoom = false; // 느린 순서
  bool scarf = true; // 상대 구애스카프 줄 표시

  @override
  Widget build(BuildContext context) {
    final data = ref.watch(speedTierProvider);
    final top = ref.watch(_speedTopProvider);
    final fmt = ref.watch(formatProvider);
    final cs = Theme.of(context).colorScheme;
    return PageBody(children: [
      PageHeader('스피드 티어',
          glyph: LabGlyph.bolt,
          subtitle:
              '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 메타 상위권의 실전 스피드와 내 팀을 비교합니다. 정렬은 가장 많이 쓰는 성격·분배 기준입니다.'),
      Card(
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          child: Wrap(spacing: 18, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
            SegmentedButton<int>(
              showSelectedIcon: false,
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
              segments: const [
                ButtonSegment(value: 30, label: Text('상위 30')),
                ButtonSegment(value: 60, label: Text('상위 60')),
                ButtonSegment(value: 100, label: Text('상위 100')),
              ],
              selected: {top},
              onSelectionChanged: (v) => ref.read(_speedTopProvider.notifier).state = v.first,
            ),
            FilterChip(
                label: const Text('내 팀 순풍 (×2)'),
                selected: tailwind,
                onSelected: (v) => setState(() => tailwind = v)),
            FilterChip(
                label: const Text('트릭룸 (느린 순)'),
                selected: trickRoom,
                onSelected: (v) => setState(() => trickRoom = v)),
            FilterChip(
                label: const Text('상대 구애스카프 표시'),
                selected: scarf,
                onSelected: (v) => setState(() => scarf = v)),
          ]),
        ),
      ),
      AsyncView<Json>(data, (d) {
        final meta = (d['meta'] as List).cast<Json>();
        final team = (d['team'] as List).cast<Json>();
        // 한 줄씩: (스피드, 종류, 데이터)
        final rows = <(num, String, Json)>[
          for (final m in meta) (m['common'] as num, 'meta', m),
          if (scarf)
            for (final m in meta)
              if ((m['scarfPct'] as num) >= 10) (((m['common'] as num) * 1.5).floor(), 'scarf', m),
          for (final t in team) ((t['speed'] as num) * (tailwind ? 2 : 1), 'mine', t),
        ];
        rows.sort((a, b) {
          final c = trickRoom ? a.$1.compareTo(b.$1) : b.$1.compareTo(a.$1);
          return c != 0 ? c : (a.$2 == 'mine' ? -1 : 1);
        });
        return Section(
          '스피드 순서',
          subtitle: team.isEmpty
              ? '팀 빌더에서 팀을 만들면 내 포켓몬이 이 순서에 함께 표시됩니다'
              : '강조된 줄이 내 팀입니다 · 오른쪽 숫자는 최속 / 준속 / 무보정 / 최저속',
          child: Column(children: [
            for (final (speed, kind, mon) in rows) _SpeedRow(speed: speed, kind: kind, mon: mon),
            if (rows.isEmpty) Text('데이터가 없습니다', style: TextStyle(color: cs.onSurfaceVariant)),
          ]),
        );
      }, onRetry: () => ref.invalidate(speedTierProvider)),
    ]);
  }
}

class _SpeedRow extends StatelessWidget {
  const _SpeedRow({required this.speed, required this.kind, required this.mon});
  final num speed;
  final String kind;
  final Json mon;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final mine = kind == 'mine';
    final scarf = kind == 'scarf';
    final accent = mine ? cs.primary : scarf ? const Color(0xFFFFC857) : cs.onSurface;
    final name = (mon['ko'] ?? mon['name']) as String;
    return InkWell(
      onTap: () => context.push('/pokemon/${mon['id']}'),
      borderRadius: BorderRadius.circular(10),
      child: Container(
        margin: const EdgeInsets.only(bottom: 4),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: mine ? cs.primary.withOpacity(.13) : scarf ? const Color(0x14FFC857) : null,
          borderRadius: BorderRadius.circular(10),
          border: mine ? Border.all(color: cs.primary.withOpacity(.6)) : null,
        ),
        child: Row(children: [
          SizedBox(
            width: 56,
            child: Text('${speed.round()}',
                style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: accent,
                    fontFeatures: const [FontFeature.tabularFigures()])),
          ),
          Sprite(mon['sprite'] as String, size: 38),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Flexible(
                  child: Text(name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 8),
                if (mine)
                  _Tag(mon['scarf'] == true ? '내 팀 · 구애스카프' : '내 팀', cs.primary)
                else if (scarf)
                  _Tag(tr('구애스카프 {}').replaceFirst('{}', fmtPct(mon['scarfPct'] as num)), const Color(0xFFFFC857))
                else
                  Text('#${mon['rank']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
              ]),
              if (!mine && !scarf)
                Text(
                    tr('스피드 성격 {} · 스피드 투자 {}')
                        .replaceFirst('{}', fmtPct(mon['plusPct'] as num))
                        .replaceFirst('{}', fmtPct(mon['investedPct'] as num)),
                    style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            ]),
          ),
          if (!mine && !scarf)
            Text('${mon['max']} / ${mon['neutral']} / ${mon['uninvested']} / ${mon['min']}',
                style: TextStyle(
                    fontSize: 12.5, color: cs.onSurfaceVariant, fontFeatures: const [FontFeature.tabularFigures()])),
        ]),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.text, this.color);
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
        decoration: BoxDecoration(color: color.withOpacity(.18), borderRadius: BorderRadius.circular(6)),
        child: Text(text, style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: color)),
      );
}
