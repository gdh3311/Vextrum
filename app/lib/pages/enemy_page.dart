import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';

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

  void add(Json p) {
    if (state.length >= 6 || state.any((e) => e['id'] == p['id'])) return;
    state = [
      ...state,
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

final enemyAnalysisProvider = FutureProvider<Json?>((ref) async {
  final enemy = ref.watch(enemyProvider);
  final team = ref.watch(teamProvider);
  final fmt = ref.watch(formatProvider);
  if (enemy.isEmpty) return null;
  final res = await dio.post('/api/enemy/analyze', data: {
    'format': fmt,
    'enemy': [for (final e in enemy) e['id']],
    'team': [for (final s in team) s.set],
  });
  return res.data as Json;
});

const _levelKo = {'HIGH': '높음', 'MEDIUM': '보통', 'LOW': '낮음'};
const _levelColor = {'HIGH': Color(0xFFD64545), 'MEDIUM': Color(0xFFB8860B), 'LOW': Color(0xFF7A7A7A)};
const _good = Color(0xFF1E9E55);
const _bad = Color(0xFFD64545);

class EnemyPage extends ConsumerWidget {
  const EnemyPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final enemy = ref.watch(enemyProvider);
    final team = ref.watch(teamProvider);
    final fmt = ref.watch(formatProvider);
    final all = ref.watch(pokemonListProvider);
    final analysis = ref.watch(enemyAnalysisProvider);
    final t = Theme.of(context);
    final cs = t.colorScheme;

    Future<void> addMon() async {
      final list = all.valueOrNull;
      if (list == null) return;
      final picked = await showPokemonPicker(context, list, fmt);
      if (picked != null) ref.read(enemyProvider.notifier).add(picked);
    }

    return PageBody(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 4),
        child: Row(children: [
          Expanded(
            child: Text('상대 분석 · ${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'}',
                style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
          ),
          if (enemy.isNotEmpty)
            TextButton.icon(
                onPressed: () => ref.read(enemyProvider.notifier).clear(),
                icon: const Icon(Icons.delete_outline),
                label: const Text('비우기')),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
        child: Text('상대 팀 6마리를 넣으면 예상 전략과 선봉을 추정하고, 내 팀에서 무엇을 내보낼지 추천합니다.',
            style: t.textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant)),
      ),
      Section(
        '상대 팀',
        subtitle: '상대는 포켓몬마다 가장 흔한 세트를 들고 있다고 가정합니다',
        child: Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
          for (var i = 0; i < enemy.length; i++)
            InputChip(
              avatar: Sprite(enemy[i]['sprite'] as String, size: 28),
              label: Text('${enemy[i]['ko'] ?? enemy[i]['name']}'),
              onPressed: () => context.push('/pokemon/${enemy[i]['id']}'),
              onDeleted: () => ref.read(enemyProvider.notifier).removeAt(i),
            ),
          if (enemy.length < 6)
            ActionChip(
                avatar: const Icon(Icons.add, size: 18),
                label: Text('상대 포켓몬 추가 (${enemy.length}/6)'),
                onPressed: all.hasValue ? addMon : null),
        ]),
      ),
      Section(
        '내 팀',
        trailing: TextButton(onPressed: () => context.go('/team'), child: const Text('팀 빌더에서 수정')),
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
        AsyncView<Json?>(analysis, (a) => a == null ? const SizedBox() : _Result(a, fmt),
            onRetry: () => ref.invalidate(enemyAnalysisProvider)),
    ]);
  }
}

class _Result extends StatelessWidget {
  final Json a;
  final String fmt;
  const _Result(this.a, this.fmt);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final strategies = (a['strategies'] as List).cast<Json>();
    final leads = (a['leads'] as List).cast<Json>();
    final rec = a['recommendation'] as Json?;
    final enemy = (a['enemy'] as List).cast<Json>();

    Widget badge(String level) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
          decoration: BoxDecoration(color: _levelColor[level], borderRadius: BorderRadius.circular(6)),
          child: Text(_levelKo[level]!,
              style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800)),
        );

    Widget sprites(List mons, {double size = 40}) => Row(mainAxisSize: MainAxisSize.min, children: [
          for (final m in mons.cast<Json>())
            Tooltip(message: '${m['ko'] ?? m['name']} (${m['name']})', child: Sprite(m['sprite'] as String, size: size)),
        ]);

    String names(List mons) => mons.cast<Json>().map((m) => m['ko'] ?? m['name']).join(' + ');

    return Column(children: [
      LayoutBuilder(builder: (context, c) {
        final two = c.maxWidth >= 860;
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
                            Row(children: [
                              Text(s['label'] as String, style: const TextStyle(fontWeight: FontWeight.w800)),
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
          SizedBox(
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
                                  style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
                          ]),
                        ),
                      ]),
                    ),
                ])),
          ),
        ]);
      }),
      if (rec != null)
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
              Text('다른 선택지', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: cs.onSurfaceVariant)),
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
      if (rec != null)
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
                                style: TextStyle(fontSize: 10, color: typeColor[m['type']] ?? cs.onSurfaceVariant)),
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
                                  fontWeight: FontWeight.w900,
                                  color: (e['threat'] as num) >= 50 ? _bad : ((e['threat'] as num) <= 38 ? _good : null))),
                          Text('위협도', style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
                        ]),
                      ),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Row(children: [
                            Text('대응 ', style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
                            Sprite(e['answer']['sprite'] as String, size: 26),
                            Flexible(
                              child: Text(
                                  '${e['answer']['moveKo'] ?? e['answer']['move'] ?? '-'} ${fmtPct(e['answer']['pct'] as num)}',
                                  style: const TextStyle(fontSize: 11),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis),
                            ),
                          ]),
                          if ((e['danger'] as List).isNotEmpty)
                            Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
                              Text('위험 ', style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
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
        child: Text(title, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800)),
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
                            style: const TextStyle(fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis)),
                  ]),
                  Text((m['roles'] as List).map((r) => r['label']).take(3).join(' · '),
                      style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant),
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
    Widget line(IconData icon, Color color, List<InlineSpan> spans) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, size: 16, color: color),
            const SizedBox(width: 6),
            Expanded(child: Text.rich(TextSpan(children: spans), style: const TextStyle(fontSize: 13))),
          ]),
        );
    TextSpan b(Object? s) => TextSpan(text: '$s', style: const TextStyle(fontWeight: FontWeight.w800));
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
                  style: const TextStyle(fontWeight: FontWeight.w800), maxLines: 1, overflow: TextOverflow.ellipsis)),
          Text('가능성 ', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
          badge,
        ]),
        const SizedBox(height: 6),
        if (sw != null)
          line(Icons.swap_horiz, cs.primary, [
            b(n(sw['out'] as Json)),
            const TextSpan(text: ' → '),
            b(n(sw['in'] as Json)),
            TextSpan(text: ' 교체 · ${sw['reason']} (${sw['moveKo'] ?? sw['move']} 예상 ${fmtPct(sw['takenPct'] as num)})'),
          ]),
        for (final x in (p['actions'] as List).cast<Json>())
          line(Icons.bolt, _good, [
            b(n(x['mon'] as Json)),
            const TextSpan(text: ' → '),
            b(x['moveKo'] ?? x['move']),
            TextSpan(text: ' → ${n(x['target'] as Json)} '),
            b(fmtPct(x['pct'] as num)),
            TextSpan(
                text: x['faster'] == true ? '  선공' : '  후공',
                style: TextStyle(fontSize: 11, color: x['faster'] == true ? _good : cs.onSurfaceVariant)),
          ]),
        for (final r in (p['risks'] as List).cast<Json>())
          line(Icons.warning_amber, _bad, [
            TextSpan(text: '${n(r['from'] as Json)}의 '),
            b(r['moveKo'] ?? r['move']),
            TextSpan(text: ' → ${n(r['to'] as Json)} '),
            b(fmtPct(r['pct'] as num)),
          ]),
      ]),
    );
  }
}
