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
import 'calc_common.dart';

final _speedTopProvider = StateProvider<int>((ref) => 60);

final speedTierProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  ref.watch(battleDataVersionProvider);
  final fmt = ref.watch(formatProvider);
  final top = ref.watch(_speedTopProvider);
  final team = ref.watch(teamProvider);
  final preview = ref.watch(previewRulesProvider);
  return (await dio.post('/api/speed', data: {
    'preview': preview,
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
  _Side? left = _savedLeft, right = _savedRight; // 스피드 비교 (화면을 옮겨 다녀도 기억)

  @override
  void initState() {
    super.initState();
    if (left == null) {
      final team = ref.read(teamProvider);
      if (team.isNotEmpty) left = _Side.of(team.first);
    }
  }

  void setLeft(_Side? v) => setState(() => left = _savedLeft = v);
  void setRight(_Side? v) => setState(() => right = _savedRight = v);

  Future<void> compareWith(String id) async {
    final detail = await ref.read(pokemonDetailProvider(id).future);
    if (!mounted) return;
    setRight(_Side.of(TeamSlot(Json.from(detail['defaultSet'] as Json), detail)));
  }

  @override
  Widget build(BuildContext context) {
    final data = ref.watch(speedTierProvider);
    final top = ref.watch(_speedTopProvider);
    final fmt = ref.watch(formatProvider);
    final cs = Theme.of(context).colorScheme;
    return PageBody(children: [
      PageHeader('배틀 계산기',
          glyph: LabGlyph.bolt,
          subtitle:
              '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 메타 상위권의 실전 스피드와 내 팀을 비교합니다. 정렬은 가장 많이 쓰는 성격·분배 기준입니다.'),
      const CalcSwitcher('/speed'),
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
            const PreviewRulesChip(),
            FilterChip(
                label: const Text('상대 구애스카프 표시'),
                selected: scarf,
                onSelected: (v) => setState(() => scarf = v)),
          ]),
        ),
      ),
      _SpeedCompare(
        left: left,
        right: right,
        trickRoom: trickRoom,
        onLeft: setLeft,
        onRight: setRight,
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
            for (final (speed, kind, mon) in rows)
              _SpeedRow(
                  speed: speed,
                  kind: kind,
                  mon: mon,
                  onCompare: kind == 'mine' ? null : () => compareWith(mon['id'] as String)),
            if (rows.isEmpty) Text('데이터가 없습니다', style: TextStyle(color: cs.onSurfaceVariant)),
          ]),
        );
      }, onRetry: () => ref.invalidate(speedTierProvider)),
    ]);
  }
}

class _SpeedRow extends StatelessWidget {
  const _SpeedRow({required this.speed, required this.kind, required this.mon, this.onCompare});
  final num speed;
  final String kind;
  final Json mon;
  final VoidCallback? onCompare;

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
          if (onCompare != null)
            Tooltip(
              message: '스피드 비교의 오른쪽에 넣기',
              child: IconButton(
                  visualDensity: VisualDensity.compact,
                  onPressed: onCompare,
                  icon: const LabIcon(LabGlyph.swap, size: 18)),
            ),
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


_Side? _savedLeft, _savedRight;

/// 스피드 비교 한쪽의 설정
class _Side {
  final TeamSlot slot;
  final int points;
  final int nature; // +1 / 0 / −1
  final int stage;
  final bool scarf, tailwind, paralysis;
  const _Side(this.slot,
      {this.points = 0, this.nature = 0, this.stage = 0, this.scarf = false, this.tailwind = false, this.paralysis = false});

  factory _Side.of(TeamSlot s) {
    final fx = natureEffects[s.set['nature']] ?? const [null, null];
    return _Side(s,
        points: ((((s.set['points'] ?? const {}) as Map)['spe'] ?? 0) as num).toInt(),
        nature: fx[0] == 'spe' ? 1 : (fx[1] == 'spe' ? -1 : 0),
        scarf: s.set['item'] == 'Choice Scarf');
  }

  _Side copy({int? points, int? nature, int? stage, bool? scarf, bool? tailwind, bool? paralysis}) => _Side(slot,
      points: points ?? this.points,
      nature: nature ?? this.nature,
      stage: stage ?? this.stage,
      scarf: scarf ?? this.scarf,
      tailwind: tailwind ?? this.tailwind,
      paralysis: paralysis ?? this.paralysis);

  num get base => (baseStatsOf(slot)['spe'] ?? 0) as num;
  int get speed => speedOf(
      base: base, points: points, nature: nature, stage: stage, scarf: scarf, tailwind: tailwind, paralysis: paralysis);
}

class _SpeedCompare extends ConsumerWidget {
  const _SpeedCompare(
      {required this.left, required this.right, required this.trickRoom, required this.onLeft, required this.onRight});
  final _Side? left, right;
  final bool trickRoom;
  final ValueChanged<_Side?> onLeft, onRight;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    String? verdict;
    if (left != null && right != null) {
      final a = left!.speed, b = right!.speed;
      final an = '${left!.slot.detail['ko'] ?? left!.slot.detail['name']}';
      final bn = '${right!.slot.detail['ko'] ?? right!.slot.detail['name']}';
      if (a == b) {
        verdict = tr('동속: 누가 먼저일지 반반입니다');
      } else {
        final first = (a > b) != trickRoom ? an : bn;
        verdict = tr('{} 먼저 움직입니다').replaceFirst('{}', first) + (trickRoom ? tr(' (트릭룸)') : '');
      }
    }
    Widget side(_Side? v, ValueChanged<_Side?> set, String label) => Container(
          padding: const EdgeInsets.all(10),
          decoration:
              BoxDecoration(color: cs.surfaceContainerHighest.withOpacity(.4), borderRadius: BorderRadius.circular(12)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            CalcMonHeader(
                slot: v?.slot,
                label: label,
                onPick: () async {
                  final s = await pickCalcMon(context, ref);
                  if (s != null) set(_Side.of(s));
                },
                trailing: v == null
                    ? null
                    : Text('${v.speed}',
                        style: TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                            color: cs.primary,
                            fontFeatures: const [FontFeature.tabularFigures()]))),
            QuickPicks(
                meta: label != tr('내 쪽') || ref.watch(teamProvider).isEmpty, onPick: (s) => set(_Side.of(s))),
            if (v != null) ...[
              Text(tr('스피드 종족값 {}').replaceFirst('{}', '${speciesBase('spe', v.base)}'),
                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
              Row(children: [
                SizedBox(
                    width: 74,
                    child: Text(tr('포인트 {}').replaceFirst('{}', '${v.points}'), style: const TextStyle(fontSize: 13))),
                Expanded(
                  child: Slider(
                      value: v.points.toDouble(),
                      min: 0,
                      max: 32,
                      divisions: 32,
                      onChanged: (x) => set(v.copy(points: x.round()))),
                ),
              ]),
              SegmentedButton<int>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: const [
                  ButtonSegment(value: 1, label: Text('스피드↑')),
                  ButtonSegment(value: 0, label: Text('보정 없음')),
                  ButtonSegment(value: -1, label: Text('스피드↓')),
                ],
                selected: {v.nature},
                onSelectionChanged: (x) => set(v.copy(nature: x.first)),
              ),
              const SizedBox(height: 6),
              Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                FilterChip(label: const Text('구애스카프'), selected: v.scarf, onSelected: (x) => set(v.copy(scarf: x))),
                FilterChip(label: const Text('순풍'), selected: v.tailwind, onSelected: (x) => set(v.copy(tailwind: x))),
                FilterChip(label: const Text('마비'), selected: v.paralysis, onSelected: (x) => set(v.copy(paralysis: x))),
                StageDropdown(label: tr('랭크'), value: v.stage, onChanged: (x) => set(v.copy(stage: x))),
              ]),
            ],
          ]),
        );
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Section(
        '스피드 비교',
        subtitle: '두 포켓몬의 실제 스피드를 비교합니다. 아래 목록의 오른쪽 버튼으로 상대를 바로 넣을 수 있습니다',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          LayoutBuilder(builder: (context, c) {
            final a = side(left, onLeft, tr('내 쪽')), b = side(right, onRight, tr('상대'));
            return c.maxWidth >= 640
                ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Expanded(child: a),
                    const SizedBox(width: 10),
                    Expanded(child: b),
                  ])
                : Column(children: [a, const SizedBox(height: 10), b]);
          }),
          if (verdict != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(verdict, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800)),
            ),
        ]),
      ),
    );
  }
}
