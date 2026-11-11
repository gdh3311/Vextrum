import 'dart:convert';

import '../lab_icons.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'battle_preview.dart';
import 'match_journal.dart';
import 'team_switcher.dart';

/// 상대 6마리 (포켓몬 목록의 항목 그대로 보관)
class EnemyNotifier extends StateNotifier<List<Json>> {
  EnemyNotifier() : super(const []) {
    _load();
  }
  static const _key = 'enemy_v1';

  Future<void> _load() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_key);
      if (raw != null && state.isEmpty) state = (jsonDecode(raw) as List).cast<Json>();
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      (await SharedPreferences.getInstance()).setString(_key, jsonEncode(state));
    } catch (_) {}
  }

  void replace(List<Json> members) {
    state = [
      for (final p in members.take(6))
        {'id': p['id'], 'name': p['name'], 'ko': p['ko'], 'sprite': p['sprite']}
    ];
    _save();
  }

  void removeAt(int i) {
    state = [
      for (var k = 0; k < state.length; k++)
        if (k != i) state[k]
    ];
    _save();
  }

  void clear() {
    state = const [];
    _save();
  }
}

final enemyProvider = StateNotifierProvider<EnemyNotifier, List<Json>>((ref) => EnemyNotifier());
final _confirmedLeadProvider = StateProvider<List<String>>((ref) => const []);
final _lockedBringProvider = StateProvider<List<String>>((ref) => const []);

final enemyAnalysisProvider = FutureProvider<Json?>((ref) async {
  final enemy = ref.watch(enemyProvider);
  final team = ref.watch(teamProvider);
  final fmt = ref.watch(formatProvider);
  final confirmed = ref.watch(_confirmedLeadProvider);
  final locked = ref.watch(_lockedBringProvider);
  if (enemy.isEmpty) return null;
  final res = await dio.post('/api/enemy/analyze', data: {
    'format': fmt,
    'enemy': [for (final e in enemy) e['id']],
    'team': [for (final s in team) s.set],
    if (fmt == 'Doubles' && confirmed.length == 2) 'enemyLead': confirmed,
    if (fmt == 'Doubles' && locked.isNotEmpty) 'lockedBring': locked,
  });
  return res.data as Json;
});

/// 저장된 팀 각각을 이 상대에 붙였을 때의 선출 점수 (팀이 둘 이상일 때)
final enemyCompareProvider = FutureProvider<List<Json>?>((ref) async {
  final enemy = ref.watch(enemyProvider);
  final teams = ref.watch(teamListProvider);
  final fmt = ref.watch(formatProvider);
  final need = fmt == 'Doubles' ? 4 : 3; // 선출 인원을 채운 팀끼리만 비교
  final usable = [
    for (var i = 0; i < teams.length; i++)
      if (teams[i].sets.length >= need) i
  ];
  if (enemy.isEmpty || usable.length < 2) return null;
  final rows = <Json>[];
  for (final i in usable) {
    final res = await dio.post('/api/enemy/analyze', data: {
      'format': fmt,
      'enemy': [for (final e in enemy) e['id']],
      'team': teams[i].sets,
    });
    final rec = (res.data as Json)['recommendation'] as Json?;
    if (rec != null) {
      rows.add({'index': i, 'name': teams[i].name, 'sprites': teams[i].sprites, 'score': rec['score'], 'lead': rec['lead']});
    }
  }
  rows.sort((a, b) => (b['score'] as num).compareTo(a['score'] as num));
  return rows;
});

class _TeamCompare extends ConsumerWidget {
  const _TeamCompare();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final rows = ref.watch(enemyCompareProvider).valueOrNull;
    final active = ref.watch(activeTeamIndexProvider);
    if (rows == null || rows.length < 2) return const SizedBox();
    return Section('어느 팀이 유리한가',
        subtitle: '저장된 팀을 이 상대에 각각 붙여 본 선출 점수 · 높을수록 유리',
        child: Column(children: [
          for (var k = 0; k < rows.length; k++)
            InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => ref.read(teamProvider.notifier).select(rows[k]['index'] as int),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 2),
                child: Row(children: [
                  SizedBox(
                      width: 26,
                      child: Text('${k + 1}',
                          style: TextStyle(
                              fontSize: 15, fontWeight: FontWeight.w700, color: k == 0 ? cs.primary : cs.onSurfaceVariant))),
                  SizedBox(
                      width: 120,
                      child: Text(rows[k]['name'] as String,
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis)),
                  for (final s in (rows[k]['sprites'] as List)) Sprite(s as String, size: 30),
                  const Spacer(),
                  Text('선봉 ${(rows[k]['lead'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')}',
                      style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
                  const SizedBox(width: 16),
                  SizedBox(
                      width: 44,
                      child: Text('${(rows[k]['score'] as num).round()}',
                          textAlign: TextAlign.right,
                          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700))),
                  const SizedBox(width: 12),
                  rows[k]['index'] == active
                      ? Text('보는 중', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: cs.primary))
                      : Text('선택', style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
                ]),
              ),
            ),
        ]));
  }
}

const _levelKo = {'HIGH': '높음', 'MEDIUM': '보통', 'LOW': '낮음'};
const _levelColor = {'HIGH': Color(0xFFF0616D), 'MEDIUM': Color(0xFFE0A93B), 'LOW': Color(0xFF7A7A7A)};
const _good = Color(0xFF34C77B);
const _bad = Color(0xFFF0616D);

class EnemyPage extends ConsumerWidget {
  const EnemyPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enemy = ref.watch(enemyProvider);
    final team = ref.watch(teamProvider);
    final fmt = ref.watch(formatProvider);
    final all = ref.watch(pokemonListProvider);
    final analysis = ref.watch(enemyAnalysisProvider);
    final confirmed = ref.watch(_confirmedLeadProvider);
    final locked = ref.watch(_lockedBringProvider);
    final teams = ref.watch(teamListProvider);
    final currentIndex = ref.watch(activeTeamIndexProvider);
    final teamName = currentIndex < teams.length ? teams[currentIndex].name : '내 팀';
    void setConfirmed(List<String> ids) => ref.read(_confirmedLeadProvider.notifier).state = ids;
    void setLocked(List<String> ids) => ref.read(_lockedBringProvider.notifier).state = ids;
    ref.listen(formatProvider, (_, __) {
      setConfirmed([]);
      setLocked([]);
    });
    ref.listen(activeTeamIndexProvider, (_, __) => setLocked([]));
    ref.listen(teamProvider, (before, after) {
      final ids = after.map((s) => s.set['id']).toSet();
      if (!ids.containsAll(ref.read(_lockedBringProvider))) setLocked([]);
    });
    Future<void> editEnemy() async {
      final list = all.valueOrNull;
      if (list == null) return;
      final picked = await pickOpponents(context, list, enemy, fmt);
      if (picked != null && context.mounted) {
        final ids = picked.map((p) => p['id']).toSet();
        setConfirmed(confirmed.where(ids.contains).toList());
        if (!ids.containsAll(enemy.map((p) => p['id'])) || picked.length != enemy.length) setLocked([]);
        ref.read(enemyProvider.notifier).replace(picked);
      }
    }

    return PageBody(children: [
      PageHeader('실전 상대 분석', glyph: LabGlyph.versus,
          subtitle: '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 상대 엔트리를 넣고, 내 팀으로 선출과 대응을 준비합니다.',
          trailing: enemy.isEmpty
              ? null
              : TextButton.icon(
                  onPressed: () {
                    setConfirmed([]);
                    setLocked([]);
                    ref.read(enemyProvider.notifier).clear();
                  },
                  icon: const LabIcon(LabGlyph.trash, size: 18),
                  label: const Text('비우기'))),
      Section(
        '상대 팀 · ${enemy.length}/6',
        subtitle: '빠른 입력으로 여러 마리를 고르거나 이름을 붙여넣을 수 있습니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          for (var i = 0; i < enemy.length; i++)
            InputChip(
              deleteIcon: const LabIcon(LabGlyph.cross, size: 15),
              avatar: Sprite(enemy[i]['sprite'] as String, size: 28),
              label: Text('${enemy[i]['ko'] ?? enemy[i]['name']}'.replaceAll('♀', '암컷').replaceAll('♂', '수컷')),
              onPressed: () => context.push('/pokemon/${enemy[i]['id']}'),
              onDeleted: () {
                setConfirmed(confirmed.where((id) => id != enemy[i]['id']).toList());
                setLocked([]);
                ref.read(enemyProvider.notifier).removeAt(i);
              },
            ),
            FilledButton.tonalIcon(
              icon: const LabIcon(LabGlyph.search, size: 18),
              label: const Text('상대 빠른 입력'),
              onPressed: all.hasValue ? editEnemy : null,
            ),
          ]),
          if (fmt == 'Doubles' && enemy.length >= 2)
            LabExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text(confirmed.length == 2 ? '상대 선봉 확인됨' : '배틀에서 본 상대 선봉 입력'),
              subtitle: const Text('선출을 마쳤다면 내 선출을 먼저 고정하세요.'),
              expandedAlignment: Alignment.centerLeft,
              children: [
                Wrap(spacing: 6, runSpacing: 4, children: [
                  for (final mon in enemy)
                    FilterChip(
                      label: Text(monName(mon)),
                      selected: confirmed.contains(mon['id']),
                      onSelected: (add) {
                        final id = mon['id'] as String;
                        if (!add) {
                          setConfirmed(confirmed.where((m) => m != id).toList());
                        } else if (confirmed.length < 2) {
                          setConfirmed([...confirmed, id]);
                        }
                      },
                    ),
                  if (confirmed.isNotEmpty)
                    TextButton(onPressed: () => setConfirmed([]), child: const Text('선봉 초기화')),
                ]),
              ],
            ),
        ]),
      ),
      Section(
        '내 팀',
        subtitle: '저장된 팀 중에서 골라 분석합니다',
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          const TeamPickerButton(),
          const SizedBox(width: 4),
          TextButton(onPressed: () => context.go('/team'), child: const Text('수정')),
        ]),
        child: team.isEmpty
            ? const Text('팀 빌더에서 팀을 만들면 선봉 추천과 상대별 대응이 함께 나옵니다.')
            : Wrap(spacing: 8, runSpacing: 8, children: [
                for (final s in team)
                  MonPill({
                    ...s.detail,
                    if (s.set['mega'] != null)
                      for (final m in (s.detail['megas'] as List).cast<Json>())
                        if (m['name'] == s.set['mega']) ...{'sprite': m['sprite'], 'ko': m['ko'], 'name': m['name']}
                  }),
              ]),
      ),
      if (enemy.isNotEmpty)
        AsyncView<Json?>(analysis, (a) => a == null ? const SizedBox() : _Result(a, fmt, setLocked),
            onRetry: () => ref.invalidate(enemyAnalysisProvider)),
      MatchJournalPanel(
        format: fmt,
        teamName: teamName,
        team: [for (final s in team) s.set],
        enemy: enemy,
        confirmed: confirmed,
        locked: locked,
      ),
      if (enemy.isNotEmpty) const _TeamCompare(),
    ]);
  }
}

class _Result extends StatelessWidget {
  final Json a;
  final String fmt;
  final ValueChanged<List<String>> onLock;
  const _Result(this.a, this.fmt, this.onLock);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final strategies = (a['strategies'] as List? ?? []).cast<Json>();
    final leads = (a['leads'] as List? ?? []).cast<Json>();
    final rec = a['recommendation'] as Json?;
    final enemy = (a['enemy'] as List).cast<Json>();
    final briefing = fmt == 'Doubles' && rec != null && rec['floor'] != null;

    Widget badge(String level) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(color: _levelColor[level], borderRadius: BorderRadius.circular(6)),
          child: Text(_levelKo[level]!,
              style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
        );

    Widget sprites(List mons, {double size = 40}) => Row(mainAxisSize: MainAxisSize.min, children: [
          for (final m in mons.cast<Json>())
            Tooltip(message: '${m['ko'] ?? m['name']} (${m['name']})', child: Sprite(m['sprite'] as String, size: size)),
        ]);

    String names(List mons) => mons.cast<Json>().map((m) => m['ko'] ?? m['name']).join(' + ');

    return Column(children: [
      if (briefing) DoublesBriefing(recommendation: rec, onLock: onLock),
      if (fmt == 'Doubles' && rec == null)
        const Section('선출을 준비하려면', child: Text('내 팀과 상대 팀에 각각 두 마리 이상을 넣으세요. 상대 여섯 마리를 채우면 후발까지 비교합니다.')),
      LayoutBuilder(builder: (context, c) {
        final two = !briefing && c.maxWidth >= 860;
        final w = two ? (c.maxWidth - 12) / 2 : c.maxWidth;
        return Wrap(spacing: 12, children: [
          SizedBox(
            width: w,
            child: Section('예상 전략',
                child: Column(children: [
                  for (final s in strategies)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Padding(padding: const EdgeInsets.only(top: 2), child: badge(s['confidence'] as String)),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
                              Text(s['label'] as String, style: const TextStyle(fontWeight: FontWeight.w700)),
                              const SizedBox(width: 6),
                              sprites(s['members'] as List, size: 28),
                            ]),
                            Text(s['tip'] as String, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                          ]),
                        ),
                      ]),
                    ),
                ])),
          ),
          if (!briefing) SizedBox(
            width: w,
            child: Section('예상 선봉',
                subtitle: '선봉 통계가 없어 동료 조합·역할 시너지·내 팀 압박도로 추정한 값입니다',
                child: Column(children: [
                  for (final l in leads)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(children: [
                        badge(l['level'] as String),
                        const SizedBox(width: 8),
                        sprites(l['members'] as List),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(names(l['members'] as List),
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis),
                            if ((l['why'] as List).isNotEmpty)
                              Text((l['why'] as List).join(' · '),
                                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                          ]),
                        ),
                      ]),
                    ),
                ])),
          ),
        ]);
      }),
      if (rec != null && !briefing)
        Section(
          '추천 선출',
          subtitle: fmt == 'Doubles' ? '6마리 중 4마리 · 선봉 2 + 후발 2' : '6마리 중 3마리 · 선봉 1 + 후발 2',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 24, runSpacing: 12, children: [
              _group(context, '선봉', (rec['lead'] as List).cast<Json>(), cs.primary),
              _group(context, '후발', (rec['back'] as List).cast<Json>(), cs.outline),
            ]),
            if ((rec['alternatives'] as List).isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('다른 선택지', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: cs.onSurfaceVariant)),
              for (final alt in (rec['alternatives'] as List).cast<Json>())
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Row(children: [
                    sprites(alt['lead'] as List, size: 32),
                    const Padding(padding: EdgeInsets.symmetric(horizontal: 6), child: Text('|')),
                    Opacity(opacity: .7, child: sprites(alt['back'] as List, size: 28)),
                    const SizedBox(width: 8),
                    Expanded(
                        child: Text(names(alt['lead'] as List),
                            style: const TextStyle(fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis)),
                    Text('${alt['score']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                  ]),
                ),
            ],
          ]),
        ),
      if (rec != null && !briefing)
        Section('상대 선봉별 첫 턴 플랜',
            subtitle: '데미지는 근사치입니다. 방어·교체 읽기는 반영하지 않았습니다',
            child: Column(children: [
              for (final p in (rec['plans'] as List).cast<Json>()) _Plan(p, badge(p['level'] as String)),
            ])),
      Section('상대 포켓몬별 위협도',
          subtitle: rec == null ? '내 팀을 만들면 위협도와 대응 포켓몬이 표시됩니다' : '위협도가 높은 순 · 내 최선의 대응과 위험한 내 포켓몬',
          child: Column(children: [
            for (final e in enemy)
              InkWell(
                onTap: () => context.push('/pokemon/${e['id']}'),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(children: [
                    Sprite(e['sprite'] as String, size: 44),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 190,
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        NameBlock(e['ko'] as String?, e['name'] as String, size: 13),
                        Wrap(spacing: 4, runSpacing: 2, children: [
                          ItemIcon(e['item'] as String?, size: 16),
                          for (final m in (e['moveInfo'] as List).cast<Json>())
                            Text('${m['ko'] ?? m['name']}',
                                style: TextStyle(fontSize: 12, color: typeColor[m['type']] ?? cs.onSurfaceVariant)),
                        ]),
                      ]),
                    ),
                    if (e['threat'] != null) ...[
                      SizedBox(
                        width: 54,
                        child: Column(children: [
                          Text('${(e['threat'] as num).round()}',
                              style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: (e['threat'] as num) >= 50 ? _bad : ((e['threat'] as num) <= 38 ? _good : null))),
                          Text('위협도', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                        ]),
                      ),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Text('대응 ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                            Sprite(e['answer']['sprite'] as String, size: 26),
                            Flexible(
                              child: Text(
                                  '${e['answer']['moveKo'] ?? e['answer']['move'] ?? '-'} ${fmtPct(e['answer']['pct'] as num)}',
                                  style: const TextStyle(fontSize: 12),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis),
                            ),
                          ]),
                          if ((e['danger'] as List).isNotEmpty)
                            Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
                              Text('위험 ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                              for (final d in (e['danger'] as List).cast<Json>())
                                Tooltip(
                                    message: '${d['ko'] ?? d['name']} ← ${d['moveKo'] ?? d['move']} ${fmtPct(d['pct'] as num)}',
                                    child: Sprite(d['sprite'] as String, size: 26)),
                            ]),
                        ]),
                      ),
                    ],
                  ]),
                ),
              ),
          ])),
    ]);
  }

  Widget _group(BuildContext context, String title, List<Json> mons, Color color) {
    final cs = Theme.of(context).colorScheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
        child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
      ),
      const SizedBox(height: 6),
      Wrap(spacing: 10, runSpacing: 8, children: [
        for (final m in mons)
          Container(
            width: 230,
            padding: const EdgeInsets.all(8),
            decoration:
                BoxDecoration(border: Border.all(color: cs.outlineVariant), borderRadius: BorderRadius.circular(12)),
            child: Row(children: [
              Sprite(m['sprite'] as String, size: 56),
              const SizedBox(width: 6),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  NameBlock(m['ko'] as String?, m['name'] as String, size: 13),
                  Row(children: [
                    ItemIcon(m['item'] as String?, size: 16),
                    const SizedBox(width: 3),
                    Flexible(
                        child: Text('${m['itemKo'] ?? m['item'] ?? '도구 없음'}',
                            style: const TextStyle(fontSize: 12), maxLines: 1, overflow: TextOverflow.ellipsis)),
                  ]),
                  Text((m['roles'] as List).map((r) => r['label']).take(3).join(' · '),
                      style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                ]),
              ),
            ]),
          ),
      ]),
    ]);
  }
}

class _Plan extends StatelessWidget {
  final Json p;
  final Widget badge;
  const _Plan(this.p, this.badge);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final sw = p['switch'] as Json?;
    final foes = (p['enemyLead'] as List).cast<Json>();
    Widget line(LabGlyph icon, Color color, List<InlineSpan> spans) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            LabIcon(icon, size: 16, color: color),
            const SizedBox(width: 6),
            Expanded(child: Text.rich(TextSpan(children: spans), style: const TextStyle(fontSize: 13))),
          ]),
        );
    TextSpan b(Object? s) => TextSpan(text: '$s', style: const TextStyle(fontWeight: FontWeight.w700));
    String n(Json m) => '${m['ko'] ?? m['name']}';

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(border: Border.all(color: cs.outlineVariant), borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text('상대가 ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          for (final f in foes) Sprite(f['sprite'] as String, size: 36),
          const SizedBox(width: 6),
          Expanded(
              child: Text('${foes.map(n).join(' + ')} 선봉이면',
                  style: const TextStyle(fontWeight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis)),
          Text('가능성 ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          badge,
        ]),
        const SizedBox(height: 6),
        if (sw != null)
          line(LabGlyph.swap, cs.primary, [
            b(n(sw['out'] as Json)),
            const TextSpan(text: ' → '),
            b(n(sw['in'] as Json)),
            TextSpan(text: ' 교체 · ${sw['reason']} (${sw['moveKo'] ?? sw['move']} 예상 ${fmtPct(sw['takenPct'] as num)})'),
          ]),
        for (final x in (p['actions'] as List).cast<Json>())
          line(LabGlyph.bolt, _good, [
            b(n(x['mon'] as Json)),
            const TextSpan(text: ' → '),
            b(x['moveKo'] ?? x['move']),
            TextSpan(text: ' → ${n(x['target'] as Json)} '),
            b(fmtPct(x['pct'] as num)),
            TextSpan(
                text: x['faster'] == true ? '  선공' : '  후공',
                style: TextStyle(fontSize: 12, color: x['faster'] == true ? _good : cs.onSurfaceVariant)),
          ]),
        for (final r in (p['risks'] as List).cast<Json>())
          line(LabGlyph.alert, _bad, [
            TextSpan(text: '${n(r['from'] as Json)}의 '),
            b(r['moveKo'] ?? r['move']),
            TextSpan(text: ' → ${n(r['to'] as Json)} '),
            b(fmtPct(r['pct'] as num)),
          ]),
      ]),
    );
  }
}
