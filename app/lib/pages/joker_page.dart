import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';

const _roleFilters = {
  'intimidate': '위협', 'fakeout': '속이다', 'speedcontrol': '스피드 컨트롤', 'redirect': '유도',
  'wideguard': '와이드가드', 'priority': '선공기', 'weather': '날씨', 'terrain': '필드', 'pivot': '교체 기술',
  'disrupt': '방해', 'fast': '고속', 'bulky': '내구형',
};
const _gradeColor = {
  'S': Color(0xFFE9B44C), 'A': Color(0xFF45D0BF), 'B': Color(0xFF8D95A6), 'C': Color(0xFF8D95A6),
};

class JokerPage extends ConsumerWidget {
  const JokerPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final f = ref.watch(jokerFilterProvider);
    final data = ref.watch(jokersProvider);
    final fmt = ref.watch(formatProvider);
    void set(JokerFilter nf) => ref.read(jokerFilterProvider.notifier).state = nf;

    return PageBody(children: [
      PageHeader('조커 파인더', glyph: LabGlyph.crystal,
          subtitle: '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 순위는 낮지만 지금 메타 상위권을 넓게 압박할 수 있는 포켓몬'),
      Card(
        margin: const EdgeInsets.only(bottom: 16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          child: Wrap(spacing: 24, runSpacing: 12, crossAxisAlignment: WrapCrossAlignment.center, children: [
            _FilterGroup(
              '사용 순위',
              SegmentedButton<int>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: const [
                  ButtonSegment(value: 30, label: Text('30위 밖')),
                  ButtonSegment(value: 50, label: Text('50위 밖')),
                  ButtonSegment(value: 100, label: Text('100위 밖')),
                  ButtonSegment(value: 150, label: Text('150위 밖')),
                ],
                selected: {f.minRank},
                onSelectionChanged: (v) => set(f.copyWith(minRank: v.first)),
              ),
            ),
            _FilterGroup(
              '기준 메타',
              SegmentedButton<int>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: const [
                  ButtonSegment(value: 20, label: Text('상위 20')),
                  ButtonSegment(value: 30, label: Text('상위 30')),
                ],
                selected: {f.topN},
                onSelectionChanged: (v) => set(f.copyWith(topN: v.first)),
              ),
            ),
            _FilterGroup(
                '역할', _Dropdown(value: f.role, labels: _roleFilters, onChanged: (v) => set(f.copyWith(role: () => v)))),
            _FilterGroup(
                '타입', _Dropdown(value: f.type, labels: typeKo, onChanged: (v) => set(f.copyWith(type: () => v)))),
          ]),
        ),
      ),
      AsyncView<Json>(data, (d) {
        final jokers = (d['jokers'] as List).cast<Json>();
        if (jokers.isEmpty) {
          return const Padding(padding: EdgeInsets.all(32), child: Center(child: Text('조건에 맞는 포켓몬이 없습니다')));
        }
        return Column(children: [for (final j in jokers) _JokerCard(j)]);
      }, onRetry: () => ref.invalidate(jokersProvider)),
    ]);
  }
}

class _JokerCard extends ConsumerWidget {
  final Json j;
  const _JokerCard(this.j);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final p = j['pokemon'] as Json;
    final sc = j['scores'] as Json;
    final team = ref.watch(teamProvider);
    final grade = j['grade'] as String;

    Widget bar(String label, num v) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(children: [
            SizedBox(width: 88, child: Text(label, style: const TextStyle(fontSize: 12))),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(value: (v / 100).clamp(0.0, 1.0).toDouble(), minHeight: 7),
              ),
            ),
            SizedBox(
                width: 30,
                child: Text('$v',
                    textAlign: TextAlign.right, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700))),
          ]),
        );

    Widget mons(String title, List rows, Color color) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
          const SizedBox(height: 4),
          if (rows.isEmpty) Text('뚜렷한 상대 없음', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final m in rows.cast<Json>())
              MonPill(m,
                  caption: '${m['moveKo'] ?? m['move'] ?? '-'} ${fmtPct(m['pct'] as num)}',
                  onTap: () => context.push('/pokemon/${m['id']}')),
          ]),
        ]);

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            InkWell(
                onTap: () => context.push('/pokemon/${p['id']}'), child: Sprite(p['sprite'] as String, size: 84)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                NameBlock(p['ko'] as String?, p['name'] as String, size: 17),
                const SizedBox(height: 4),
                Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  TypeRow(p['types'] as List, dense: true),
                  Text('사용 순위 #${j['rank']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                ]),
                const SizedBox(height: 6),
                Text((p['roles'] as List).map((r) => r['label']).join(' · '),
                    style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
              ]),
            ),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Row(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                      color: _gradeColor[grade]!.withOpacity(.16), borderRadius: BorderRadius.circular(6)),
                  child: Text('$grade 등급',
                      style: TextStyle(color: _gradeColor[grade], fontSize: 12.5, fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: 8),
                Text('${(j['score'] as num).round()}',
                    style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700, height: 1)),
              ]),
              const SizedBox(height: 8),
              FilledButton.tonalIcon(
                icon: const LabIcon(LabGlyph.plus, size: 18),
                label: Text(team.length >= 6 ? '팀 가득 참' : '팀에 추가'),
                onPressed: team.length >= 6
                    ? null
                    : () async {
                        await ref.read(teamProvider.notifier).add(p['id'] as String, set: j['set'] as Json);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                              content: Text('${p['ko'] ?? p['name']} — 추천 세트로 추가했습니다'),
                              action: SnackBarAction(label: '팀 보기', onPressed: () => context.go('/team'))));
                        }
                      },
              ),
            ]),
          ]),
          const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Divider()),
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 880 ? 3 : (c.maxWidth >= 560 ? 2 : 1);
            final w = (c.maxWidth - (cols - 1) * 28) / cols;
            return Wrap(spacing: 28, runSpacing: 18, children: [
              SizedBox(
                width: w,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  bar('메타 커버리지', sc['coverage'] as num),
                  bar('의외성', sc['surprise'] as num),
                  bar('역할 압축', sc['compression'] as num),
                  bar('스피드', sc['speed'] as num),
                  bar('유틸리티', sc['utility'] as num),
                ]),
              ),
              SizedBox(
                width: w,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('추천 세트', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Row(children: [
                    ItemIcon(p['item'] as String?, size: 22),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                          '${p['itemKo'] ?? p['item'] ?? '도구 없음'} · ${p['abilityKo'] ?? p['ability']} · '
                          '${p['natureKo'] ?? p['nature']}',
                          style: const TextStyle(fontSize: 12),
                          maxLines: 2),
                    ),
                  ]),
                  const SizedBox(height: 6),
                  Wrap(spacing: 4, runSpacing: 4, children: [
                    for (final m in (p['moveInfo'] as List).cast<Json>())
                      MoveChip(m['name'] as String, ko: m['ko'] as String?, type: m['type'] as String?),
                  ]),
                  const SizedBox(height: 6),
                  Text(
                      '포인트 ${statKeys.map((k) => '${(p['points'] as Json)[k]}').join('/')} → '
                      '${statKeys.map((k) => '${(p['stats'] as Json)[k]}').join('/')}',
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                ]),
              ),
              SizedBox(
                width: w,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  mons('강한 상대', j['strong'] as List, const Color(0xFF34C77B)),
                  const SizedBox(height: 10),
                  mons('약한 상대', j['weak'] as List, const Color(0xFFF0616D)),
                ]),
              ),
            ]);
          }),
        ]),
      ),
    );
  }
}

class _FilterGroup extends StatelessWidget {
  final String label;
  final Widget child;
  const _FilterGroup(this.label, this.child);
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        const SizedBox(width: 10),
        child,
      ]);
}

/// '전체' + 항목 목록에서 하나를 고르는 드롭다운
class _Dropdown extends StatelessWidget {
  final String? value;
  final Map<String, String> labels;
  final ValueChanged<String?> onChanged;
  const _Dropdown({required this.value, required this.labels, required this.onChanged});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return PopupMenuButton<String>(
      tooltip: '',
      position: PopupMenuPosition.under,
      color: cs.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      constraints: const BoxConstraints(maxHeight: 420),
      onSelected: (v) => onChanged(v.isEmpty ? null : v),
      itemBuilder: (_) => [
        const PopupMenuItem(value: '', height: 38, child: Text('전체', style: TextStyle(fontSize: 13.5))),
        for (final e in labels.entries)
          PopupMenuItem(value: e.key, height: 38, child: Text(e.value, style: const TextStyle(fontSize: 13.5))),
      ],
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 7, 8, 7),
        decoration: BoxDecoration(
            color: value == null ? cs.surfaceContainer : cs.primary.withOpacity(.16),
            borderRadius: BorderRadius.circular(9)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(value == null ? '전체' : labels[value] ?? value!,
              style: TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w600, color: value == null ? cs.onSurface : cs.primary)),
          const SizedBox(width: 2),
          LabIcon(LabGlyph.down, size: 18, color: cs.onSurfaceVariant),
        ]),
      ),
    );
  }
}
