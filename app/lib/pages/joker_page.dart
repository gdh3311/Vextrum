import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

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
  'S': Color(0xFFD64545), 'A': Color(0xFFE08A00), 'B': Color(0xFF2F6FED), 'C': Color(0xFF7A7A7A),
};

class JokerPage extends ConsumerWidget {
  const JokerPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final f = ref.watch(jokerFilterProvider);
    final data = ref.watch(jokersProvider);
    final fmt = ref.watch(formatProvider);
    final t = Theme.of(context);
    void set(JokerFilter nf) => ref.read(jokerFilterProvider.notifier).state = nf;

    return PageBody(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 4),
        child: Text('조커 파인더 · ${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'}',
            style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
        child: Text('순위는 낮지만 지금 메타 상위권을 넓게 압박할 수 있는 포켓몬을 찾습니다.',
            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
      ),
      Section(
        '조건',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            const Text('사용 순위'),
            for (final r in const [30, 50, 100, 150])
              ChoiceChip(
                  label: Text('$r위 밖'), selected: f.minRank == r, onSelected: (_) => set(f.copyWith(minRank: r))),
            const SizedBox(width: 12),
            const Text('기준 메타'),
            for (final n in const [20, 30])
              ChoiceChip(label: Text('상위 $n'), selected: f.topN == n, onSelected: (_) => set(f.copyWith(topN: n))),
          ]),
          const SizedBox(height: 10),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final e in _roleFilters.entries)
              FilterChip(
                  visualDensity: VisualDensity.compact,
                  label: Text(e.value),
                  selected: f.role == e.key,
                  onSelected: (on) => set(f.copyWith(role: () => on ? e.key : null))),
          ]),
          const SizedBox(height: 10),
          Wrap(spacing: 4, runSpacing: 4, children: [
            for (final ty in typeKo.keys)
              InkWell(
                onTap: () => set(f.copyWith(type: () => f.type == ty ? null : ty)),
                child: Opacity(opacity: f.type == null || f.type == ty ? 1 : .35, child: TypeChip(ty)),
              ),
          ]),
        ]),
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
          Text(title, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: color)),
          const SizedBox(height: 4),
          if (rows.isEmpty) Text('뚜렷한 상대 없음', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final m in rows.cast<Json>())
              MonPill(m,
                  caption: '${m['moveKo'] ?? m['move'] ?? '-'} ${fmtPct(m['pct'] as num)}',
                  onTap: () => context.push('/pokemon/${m['id']}')),
          ]),
        ]);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
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
                Wrap(spacing: 4, runSpacing: 4, children: [
                  for (final r in (p['roles'] as List).cast<Json>())
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                          border: Border.all(color: cs.outlineVariant), borderRadius: BorderRadius.circular(20)),
                      child: Text(r['label'] as String, style: const TextStyle(fontSize: 10)),
                    ),
                ]),
              ]),
            ),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Row(mainAxisSize: MainAxisSize.min, children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(color: _gradeColor[grade], borderRadius: BorderRadius.circular(6)),
                  child: Text('$grade 조커',
                      style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800)),
                ),
                const SizedBox(width: 8),
                Text('${(j['score'] as num).round()}',
                    style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w900, height: 1)),
              ]),
              const SizedBox(height: 8),
              FilledButton.tonalIcon(
                icon: const Icon(Icons.add, size: 18),
                label: Text(team.length >= 6 ? '팀 가득 참' : '팀에 추가'),
                onPressed: team.length >= 6
                    ? null
                    : () async {
                        await ref.read(teamProvider.notifier).add(p['id'] as String, set: j['set'] as Json);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                              content: Text('${p['ko'] ?? p['name']}을(를) 추천 세트로 팀에 추가했습니다'),
                              action: SnackBarAction(label: '팀 보기', onPressed: () => context.go('/team'))));
                        }
                      },
              ),
            ]),
          ]),
          const Divider(height: 22),
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 880 ? 3 : (c.maxWidth >= 560 ? 2 : 1);
            final w = (c.maxWidth - (cols - 1) * 20) / cols;
            return Wrap(spacing: 20, runSpacing: 14, children: [
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
                  const Text('추천 세트', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800)),
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
                      style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
                ]),
              ),
              SizedBox(
                width: w,
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  mons('강한 상대', j['strong'] as List, const Color(0xFF1E9E55)),
                  const SizedBox(height: 10),
                  mons('약한 상대', j['weak'] as List, const Color(0xFFD64545)),
                ]),
              ),
            ]);
          }),
        ]),
      ),
    );
  }
}
