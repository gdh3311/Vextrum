import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import 'team_guide.dart';
import 'team_switcher.dart';
import '../widgets.dart';
import '../i18n.dart';

const _pointCap = 66; // 능력 포인트 총합 상한
const _pointMax = 32; // 한 능력치 상한

Json? _megaOf(TeamSlot s) {
  final name = s.set['mega'];
  if (name == null) return null;
  for (final m in (s.detail['megas'] as List).cast<Json>()) {
    if (m['name'] == name) return m;
  }
  return null;
}

Map<String, Json> _learnMap(Json detail) =>
    {for (final m in (detail['learnset'] as List).cast<Json>()) m['name'] as String: m};

Map<String, int> _finalStats(TeamSlot s) {
  final base = (_megaOf(s)?['stats'] ?? s.detail['stats']) as Json;
  final pts = (s.set['points'] ?? const {}) as Map;
  final fx = natureEffects[s.set['nature']] ?? const [null, null];
  return {
    for (final k in statKeys)
      k: (((base[k] as num) + ((pts[k] ?? 0) as num)) * (k == fx[0] ? 1.1 : (k == fx[1] ? 0.9 : 1.0))).floor()
  };
}

class TeamPage extends ConsumerWidget {
  const TeamPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final team = ref.watch(teamProvider);
    final fmt = ref.watch(formatProvider);
    final analysis = ref.watch(analysisProvider);
    final all = ref.watch(pokemonListProvider);
    Future<void> addMon() async {
      final list = all.valueOrNull;
      if (list == null) return;
      final picked = await showPokemonPicker(context, list, fmt);
      if (picked != null) await ref.read(teamProvider.notifier).add(picked['id'] as String);
    }

    final members = (analysis.valueOrNull?['members'] as List?)?.cast<Json>();

    return PageBody(children: [
      PageHeader('팀 빌더', glyph: LabGlyph.team,
          subtitle: '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 팀을 여러 개 저장해 두고 골라 쓸 수 있습니다. 카드를 누르면 세트를 편집합니다'),
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: () => context.push('/team/auto'),
            icon: const LabIcon(LabGlyph.spark),
            label: const Text('팀 자동 구성'),
          ),
          OutlinedButton.icon(
            onPressed: () => context.go('/parties'),
            icon: const LabIcon(LabGlyph.team),
            label: const Text('랭커 · 추천 파티'),
          ),
          OutlinedButton.icon(
            onPressed: () => context.go('/battle'),
            icon: const LabIcon(LabGlyph.controller),
            label: const Text('가상 배틀'),
          ),
          OutlinedButton.icon(
            onPressed: () => context.go('/enemy'),
            icon: const LabIcon(LabGlyph.versus),
            label: const Text('이 팀으로 실전 선출'),
          ),
        ]),
      ),
      const TeamSwitcher(),
      LayoutBuilder(builder: (context, c) {
        final cols = c.maxWidth >= 1000 ? 3 : (c.maxWidth >= 640 ? 2 : 1);
        final w = (c.maxWidth - (cols - 1) * 12) / cols;
        return Wrap(spacing: 12, runSpacing: 12, children: [
          for (var i = 0; i < team.length; i++)
            SizedBox(
              width: w,
              child: _SlotCard(
                  index: i,
                  slot: team[i],
                  roles: members != null && i < members.length ? (members[i]['roles'] as List).cast<Json>() : null),
            ),
          if (team.length < 6)
            SizedBox(
              width: w,
              height: 214,
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                    foregroundColor: Theme.of(context).colorScheme.onSurfaceVariant,
                    side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant, width: 1.5),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
                onPressed: all.hasValue ? addMon : null,
                icon: const LabIcon(LabGlyph.plus),
                label: Text('포켓몬 추가 (${team.length}/6)'),
              ),
            ),
        ]);
      }),
      const SizedBox(height: 24),
      if (team.isEmpty)
        _EmptyTeam(onSample: () async {
          final meta = await ref.read(metaProvider.future);
          final top = (meta['ranking'] as List).first as Json;
          final detail = await fetchDetail(top['id'] as String, fmt);
          final mates = ((detail['usage']?['teammates'] ?? const []) as List).cast<Json>();
          final ids = [top['id'] as String, for (final m in mates.take(5)) m['id'] as String];
          for (final id in ids) {
            await ref.read(teamProvider.notifier).add(id);
          }
        })
      else
        AsyncView<Json?>(
            analysis,
            (a) => a == null ? const SizedBox() : TeamTabs(guide: a['guide'] as Json?, analysis: _Analysis(a)),
            onRetry: () => ref.invalidate(analysisProvider)),
    ]);
  }
}

class _SlotCard extends ConsumerWidget {
  final int index;
  final TeamSlot slot;
  final List<Json>? roles;
  const _SlotCard({required this.index, required this.slot, this.roles});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final d = slot.detail;
    final s = slot.set;
    final mega = _megaOf(slot);
    final learn = _learnMap(d);
    final items = {for (final i in ref.watch(itemsProvider).valueOrNull ?? const <Json>[]) i['name']: i['ko']};
    final natures = (ref.watch(infoProvider).valueOrNull?['natures'] ?? const {}) as Map;
    final stats = _finalStats(slot);
    final types = (mega?['types'] ?? d['types']) as List;
    final moves = (s['moves'] as List? ?? const []).cast<String>();
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => showDialog(context: context, builder: (_) => SetEditor(slot: slot, onChanged: (v) => ref.read(teamProvider.notifier).update(index, v))),
        child: SizedBox(
          height: 214,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 10, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SpriteBadge((mega?['sprite'] ?? d['sprite']) as String, size: 60, type: types.firstOrNull as String?),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    NameBlock((mega?['ko'] ?? d['ko']) as String?, (mega?['name'] ?? d['name']) as String, size: 15.5),
                    const SizedBox(height: 5),
                    TypeRow((mega?['types'] ?? d['types']) as List, dense: true),
                  ]),
                ),
                IconButton(
                    visualDensity: VisualDensity.compact,
                    tooltip: tr('상세 통계'),
                    color: cs.onSurfaceVariant,
                    onPressed: () => context.push('/pokemon/${d['id']}'),
                    icon: const LabIcon(LabGlyph.meta, size: 20)),
                IconButton(
                    visualDensity: VisualDensity.compact,
                    tooltip: tr('팀에서 빼기'),
                    color: cs.onSurfaceVariant,
                    onPressed: () => ref.read(teamProvider.notifier).removeAt(index),
                    icon: const LabIcon(LabGlyph.cross, size: 20)),
              ]),
              const SizedBox(height: 10),
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: Row(children: [
                  ItemIcon(s['item'] as String?, size: 20),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(s['item'] == null ? '도구 없음' : '${items[s['item']] ?? s['item']}',
                        style: const TextStyle(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
                  ),
                  Text('${(natures[s['nature']] as Map?)?['ko'] ?? s['nature']} · 스피드 ${stats['spe']}', style: muted),
                ]),
              ),
              const SizedBox(height: 10),
              if (moves.isEmpty)
                Text('기술을 선택하세요', style: TextStyle(fontSize: 13, color: cs.error))
              else
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: Column(children: [
                    for (var r = 0; r < 2; r++)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(children: [
                          for (var c = 0; c < 2; c++) ...[
                            if (c == 1) const SizedBox(width: 6),
                            Expanded(
                              child: r * 2 + c < moves.length
                                  ? MoveChip(moves[r * 2 + c],
                                      ko: learn[moves[r * 2 + c]]?['ko'] as String?,
                                      type: learn[moves[r * 2 + c]]?['type'] as String?,
                                      expand: true)
                                  : const SizedBox(),
                            ),
                          ],
                        ]),
                      ),
                  ]),
                ),
              const Spacer(),
              if (roles != null && roles!.isNotEmpty)
                Text(roles!.map((r) => r['label']).join(' · '),
                    style: muted, maxLines: 1, overflow: TextOverflow.ellipsis),
            ]),
          ),
        ),
      ),
    );
  }
}

/// 세트 편집: 폼(메가) / 도구 / 특성 / 성격 / 기술 4개 / 능력 포인트
class SetEditor extends ConsumerStatefulWidget {
  final TeamSlot slot;
  final ValueChanged<Json> onChanged;
  const SetEditor({super.key, required this.slot, required this.onChanged});
  @override
  ConsumerState<SetEditor> createState() => _SetEditorState();
}

class _SetEditorState extends ConsumerState<SetEditor> {
  late TeamSlot slot = widget.slot;

  @override
  Widget build(BuildContext context) {
    final d = slot.detail;
    final s = slot.set;
    final cs = Theme.of(context).colorScheme;
    final usage = d['usage'] as Json?;
    final megas = (d['megas'] as List).cast<Json>();
    final mega = _megaOf(slot);
    final learn = _learnMap(d);
    final allItems = ref.watch(itemsProvider).valueOrNull ?? const <Json>[];
    final itemKo = {for (final i in allItems) i['name']: i['ko']};
    final natures = (ref.watch(infoProvider).valueOrNull?['natures'] ?? const {}) as Map;
    final moves = [...(s['moves'] as List? ?? const []).cast<String>()];
    final pts = {for (final k in statKeys) k: (((s['points'] ?? const {}) as Map)[k] ?? 0) as int};
    final used = pts.values.fold<int>(0, (a, b) => a + b);
    final stats = _finalStats(slot);
    final fx = natureEffects[s['nature']] ?? const [null, null];

    void put(Json patch) {
      final next = <String, dynamic>{...s, ...patch};
      setState(() => slot = slot.withSet(next));
      widget.onChanged(next);
    }

    Future<void> pickItem() async {
      final usedItems = ((usage?['items'] ?? const []) as List).cast<Json>();
      final usedNames = {for (final i in usedItems) i['name']};
      final ownStones = {for (final m in megas) m['stone']};
      final list = <PickItem<String>>[
        const PickItem('', '도구 없음'),
        for (final i in usedItems)
          PickItem(i['name'] as String, '${i['ko'] ?? i['name']}',
              subtitle: i['name'] as String,
              leading: ItemIcon(i['name'] as String, size: 28),
              trailing: fmtPct(i['pct'] as num),
              group: '이 포켓몬이 자주 지니는 도구'),
        for (final m in megas)
          if (m['stone'] != null && !usedNames.contains(m['stone']))
            PickItem(m['stone'] as String, '${itemKo[m['stone']] ?? m['stone']}',
                subtitle: '${m['stone']} → ${m['ko'] ?? m['name']}',
                leading: ItemIcon(m['stone'] as String, size: 28),
                group: '메가스톤'),
        for (final i in allItems)
          if (i['stone'] != true && !usedNames.contains(i['name']) && !ownStones.contains(i['name']))
            PickItem(i['name'] as String, '${i['ko'] ?? i['name']}',
                subtitle: i['name'] as String, leading: ItemIcon(i['name'] as String, size: 28), group: '전체 도구'),
      ];
      final v = await showPicker(context, '도구 선택', list);
      if (v == null) return;
      Json? m;
      for (final x in megas) {
        if (x['stone'] == v) m = x;
      }
      put({'item': v.isEmpty ? null : v, 'mega': m?['name']}); // 메가스톤을 들면 자동으로 메가 폼
    }

    Future<void> pickMove(int k) async {
      final usedMoves = ((usage?['moves'] ?? const []) as List).cast<Json>();
      final usedNames = {for (final m in usedMoves) m['name']};
      PickItem<String> item(Json m, {num? pct, required String group}) => PickItem(m['name'] as String,
          '${m['ko'] ?? m['name']}',
          subtitle:
              '${m['name']} · ${categoryKo[m['category']]}${(m['power'] as num) > 0 ? ' 위력 ${m['power']}' : ''}',
          leading: TypeChip(m['type'] as String),
          trailing: pct == null ? null : fmtPct(pct),
          group: group);
      final others = moves.asMap().entries.where((e) => e.key != k).map((e) => e.value).toSet();
      final list = <PickItem<String>>[
        if (k < moves.length) const PickItem('', '이 칸 비우기'),
        for (final m in usedMoves)
          if (!others.contains(m['name'])) item(m, pct: m['pct'] as num, group: '채용률 순'),
        for (final m in learn.values)
          if (!usedNames.contains(m['name']) && !others.contains(m['name'])) item(m, group: '그 외 배울 수 있는 기술'),
      ];
      final v = await showPicker(context, '기술 ${k + 1} 선택', list);
      if (v == null) return;
      if (v.isEmpty) {
        moves.removeAt(k);
      } else if (k < moves.length) {
        moves[k] = v;
      } else {
        moves.add(v);
      }
      put({'moves': moves});
    }

    Future<void> pickNature() async {
      final usedNat = {
        for (final n in ((usage?['natures'] ?? const []) as List).cast<Json>()) n['name']: n['pct'] as num
      };
      final names = natureEffects.keys.toList()
        ..sort((a, b) => (usedNat[b] ?? -1).compareTo(usedNat[a] ?? -1));
      final v = await showPicker(context, '성격 선택', [
        for (final n in names)
          PickItem(n, natureLabel(n, (natures[n] as Map?)?['ko'] as String?),
              trailing: usedNat[n] == null ? null : fmtPct(usedNat[n]))
      ]);
      if (v != null) put({'nature': v});
    }

    Future<void> pickAbility() async {
      final usedAb = {
        for (final a in ((usage?['abilities'] ?? const []) as List).cast<Json>()) a['name']: a['pct'] as num
      };
      final v = await showPicker(context, '특성 선택', [
        for (final a in (d['abilities'] as List).cast<Json>())
          PickItem(a['name'] as String, '${a['ko'] ?? a['name']}',
              subtitle: a['name'] as String, trailing: usedAb[a['name']] == null ? null : fmtPct(usedAb[a['name']]))
      ]);
      if (v != null) put({'ability': v});
    }

    Widget field(String label, Widget child, VoidCallback? onTap) => InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: InputDecorator(
            decoration: InputDecoration(
                labelText: label,
                isDense: true,
                suffixIcon: onTap == null ? null : const LabIcon(LabGlyph.down),
                contentPadding: const EdgeInsets.fromLTRB(10, 10, 4, 10)),
            child: child,
          ),
        );

    final megaAbility = mega == null ? null : ((mega['abilities'] as List).first as Json);
    final abilityKo = {for (final a in (d['abilities'] as List).cast<Json>()) a['name']: a['ko']};

    return Dialog(
      insetPadding: const EdgeInsets.all(16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760, maxHeight: 820),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
            child: Row(children: [
              Sprite((mega?['sprite'] ?? d['sprite']) as String, size: 56),
              const SizedBox(width: 10),
              Expanded(
                  child: NameBlock((mega?['ko'] ?? d['ko']) as String?, (mega?['name'] ?? d['name']) as String,
                      size: 18)),
              TextButton(
                  onPressed: () => put(Json.from(d['defaultSet'] as Json)), child: const Text('인기 세트로 되돌리기')),
              IconButton(onPressed: () => Navigator.pop(context), icon: const LabIcon(LabGlyph.cross)),
            ]),
          ),
          Flexible(
            child: SingleChildScrollView(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (megas.isNotEmpty) ...[
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    ChoiceChip(
                        label: const Text('기본 폼'),
                        selected: mega == null,
                        onSelected: (_) => put({
                              'mega': null,
                              if (megas.any((m) => m['stone'] == s['item'])) 'item': null,
                            })),
                    for (final m in megas)
                      ChoiceChip(
                          avatar: Sprite(m['sprite'] as String, size: 24),
                          label: Text('${m['ko'] ?? m['name']}'),
                          selected: mega?['name'] == m['name'],
                          onSelected: (_) => put({'mega': m['name'], if (m['stone'] != null) 'item': m['stone']})),
                  ]),
                  const SizedBox(height: 14),
                ],
                LayoutBuilder(builder: (context, c) {
                  final two = c.maxWidth >= 520;
                  final w = two ? (c.maxWidth - 12) / 2 : c.maxWidth;
                  return Wrap(spacing: 12, runSpacing: 12, children: [
                    SizedBox(
                      width: w,
                      child: field(
                          '도구',
                          Row(children: [
                            ItemIcon(s['item'] as String?, size: 24),
                            const SizedBox(width: 8),
                            Expanded(
                                child: s['item'] == null
                                    ? const Text('도구 없음')
                                    : NameBlock(itemKo[s['item']] as String?, s['item'] as String, size: 13)),
                          ]),
                          pickItem),
                    ),
                    SizedBox(
                      width: w,
                      child: megaAbility != null
                          ? field(
                              '특성 (메가진화 후 고정)',
                              NameBlock(megaAbility['ko'] as String?, megaAbility['name'] as String, size: 13),
                              null)
                          : field(
                              '특성',
                              s['ability'] == null
                                  ? const Text('-')
                                  : NameBlock(abilityKo[s['ability']] as String?, s['ability'] as String, size: 13),
                              pickAbility),
                    ),
                    for (var k = 0; k < 4; k++)
                      SizedBox(
                        width: w,
                        child: field(
                            '기술 ${k + 1}',
                            k < moves.length
                                ? Row(children: [
                                    TypeChip((learn[moves[k]]?['type'] ?? 'Normal') as String, dense: true),
                                    const SizedBox(width: 8),
                                    Expanded(
                                        child: NameBlock(learn[moves[k]]?['ko'] as String?, moves[k], size: 13)),
                                    if (learn[moves[k]] != null)
                                      Text(
                                          '${categoryKo[learn[moves[k]]!['category']]}'
                                          '${(learn[moves[k]]!['power'] as num) > 0 ? ' ${learn[moves[k]]!['power']}' : ''}',
                                          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                                  ])
                                : Text('선택 안 함', style: TextStyle(color: cs.onSurfaceVariant)),
                            k <= moves.length ? () => pickMove(k) : null),
                      ),
                    SizedBox(
                      width: c.maxWidth,
                      child: field(
                          '성격',
                          Text(natureLabel(s['nature'] as String? ?? 'Hardy',
                              (natures[s['nature']] as Map?)?['ko'] as String?)),
                          pickNature),
                    ),
                  ]);
                }),
                const SizedBox(height: 18),
                Row(children: [
                  const Text('능력 포인트', style: TextStyle(fontWeight: FontWeight.w700)),
                  const SizedBox(width: 8),
                  Text('남은 포인트 ${_pointCap - used} / $_pointCap',
                      style: TextStyle(fontSize: 12, color: used > _pointCap ? cs.error : cs.onSurfaceVariant)),
                  const Spacer(),
                  TextButton(
                      onPressed: () => put({'points': {for (final k in statKeys) k: 0}}), child: const Text('초기화')),
                ]),
                if (((usage?['spreads'] ?? const []) as List).isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Wrap(spacing: 6, runSpacing: 6, children: [
                      for (final sp in (usage!['spreads'] as List).cast<Json>().take(5))
                        ActionChip(
                            visualDensity: VisualDensity.compact,
                            label: Text('${statKeys.map((k) => '${sp[k]}').join('/')} · ${fmtPct(sp['pct'] as num)}',
                                style: const TextStyle(fontSize: 12)),
                            onPressed: () => put({'points': {for (final k in statKeys) k: sp[k]}})),
                    ]),
                  ),
                for (final k in statKeys)
                  Row(children: [
                    SizedBox(
                      width: 62,
                      child: Text('${statKo[k]}${k == fx[0] ? ' ↑' : (k == fx[1] ? ' ↓' : '')}',
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: k == fx[0]
                                  ? const Color(0xFFF0616D)
                                  : (k == fx[1] ? const Color(0xFF2F6FED) : null))),
                    ),
                    Expanded(
                      child: Slider(
                        value: pts[k]!.toDouble(),
                        min: 0,
                        max: _pointMax.toDouble(),
                        divisions: _pointMax,
                        label: '${pts[k]}',
                        onChanged: (v) {
                          final room = _pointCap - (used - pts[k]!);
                          final nv = v.round().clamp(0, room < _pointMax ? room : _pointMax);
                          if (nv != pts[k]) put({'points': {...pts, k: nv}});
                        },
                      ),
                    ),
                    SizedBox(width: 30, child: Text('+${pts[k]}', style: const TextStyle(fontSize: 12))),
                    SizedBox(
                        width: 40,
                        child: Text('${stats[k]}',
                            textAlign: TextAlign.right,
                            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
                  ]),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- 분석 결과

const _good = Color(0xFF34C77B);
const _bad = Color(0xFFF0616D);
const _even = Color(0xFFE0A93B);

class _Analysis extends ConsumerWidget {
  final Json a;
  const _Analysis(this.a);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final members = (a['members'] as List).cast<Json>();
    final warnings = (a['warnings'] as List).cast<Json>();
    final split = a['damageSplit'] as Json;
    final matchups = (a['matchups'] as List).cast<Json>();
    final suggestions = (a['suggestions'] as List).cast<Json>();
    final topN = ref.watch(analysisTopNProvider);
    final counts = <String, int>{};
    for (final m in matchups) {
      counts[m['label'] as String] = (counts[m['label']] ?? 0) + 1;
    }

    return Column(children: [
      Section(
        '팀 약점 진단',
        subtitle: warnings.isEmpty ? '눈에 띄는 구조적 약점이 없습니다' : null,
        trailing: a['metaScore'] == null
            ? null
            : Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text('${a['metaScore']}', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700)),
                Tooltip(
                  message: '메타 상위권 각각에 대한 팀의 상성 점수를 순위 가중으로 평균한 값입니다.\n50이 호각, 62 이상이면 유리한 편입니다.',
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Text('메타 대응 점수', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                    const SizedBox(width: 3),
                    LabIcon(LabGlyph.help, size: 14, color: cs.onSurfaceVariant),
                  ]),
                ),
              ]),
        child: Column(children: [
          for (final w in warnings)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: LabIcon(
                  w['severity'] == 'high' ? LabGlyph.alert : (w['severity'] == 'mid' ? LabGlyph.alert : LabGlyph.info),
                  color: w['severity'] == 'high' ? _bad : (w['severity'] == 'mid' ? _even : cs.primary)),
              title: Row(children: [
                if (w['type'] != null) ...[TypeChip(w['type'] as String, dense: true), const SizedBox(width: 6)],
                Flexible(
                    child: Text(
                        w['type'] != null
                            ? (w['text'] as String).replaceFirst('${w['type']} 타입', '${typeKo[w['type']]} 타입')
                            : w['text'] as String,
                        style: const TextStyle(fontWeight: FontWeight.w700))),
              ]),
              subtitle: Text(w['detail'] as String),
            ),
          const SizedBox(height: 6),
          Row(children: [
            Text('물리 ${split['physical']}%', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
            const SizedBox(width: 8),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: Row(children: [
                  Expanded(
                      flex: (split['physical'] as int) + 1,
                      child: Container(height: 12, color: const Color(0xFFE08A00))),
                  Expanded(
                      flex: (split['special'] as int) + 1, child: Container(height: 12, color: const Color(0xFF5060E1))),
                ]),
              ),
            ),
            const SizedBox(width: 8),
            Text('특수 ${split['special']}%', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          ]),
        ]),
      ),
      if (suggestions.isNotEmpty)
        Section('한 자리만 바꾼다면',
            subtitle: '메타 대응 점수가 가장 많이 오르는 교체 (추천 세트 기준)',
            child: Column(children: [
              for (final s in suggestions)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(children: [
                    Sprite(s['out']['sprite'] as String, size: 36),
                    const LabIcon(LabGlyph.forward, size: 16),
                    Sprite(s['in']['sprite'] as String, size: 44),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text.rich(TextSpan(children: [
                          TextSpan(
                              text: '${s['in']['ko'] ?? s['in']['name']}',
                              style: const TextStyle(fontWeight: FontWeight.w700)),
                          TextSpan(
                              text: '  ${s['in']['name']} · #${s['in']['rank']}',
                              style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                        ])),
                        Text(
                            '${s['out']['ko'] ?? s['out']['name']} 대신 · '
                            '${(s['in']['roles'] as List).map((r) => r['label']).take(4).join(', ')}',
                            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                        if ((s['fixes'] as List).isNotEmpty)
                          Row(children: [
                            Text('개선: ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                            for (final f in (s['fixes'] as List).cast<Json>())
                              Tooltip(message: '${f['ko'] ?? f['name']}', child: Sprite(f['sprite'] as String, size: 26)),
                          ]),
                      ]),
                    ),
                    Text('+${s['gain']}', style: const TextStyle(fontWeight: FontWeight.w700, color: _good)),
                    const SizedBox(width: 8),
                    OutlinedButton(
                        onPressed: () => ref
                            .read(teamProvider.notifier)
                            .add(s['in']['id'] as String, set: s['set'] as Json, replaceAt: s['slot'] as int),
                        child: const Text('교체')),
                  ]),
                ),
            ])),
      LayoutBuilder(builder: (context, c) {
        final two = c.maxWidth >= 900;
        final w = two ? (c.maxWidth - 12) / 2 : c.maxWidth;
        return Wrap(spacing: 12, children: [
          SizedBox(width: w, child: _TypeTable(members, (a['typeRows'] as List).cast<Json>())),
          SizedBox(
            width: w,
            child: Section('역할 구성',
                child: Column(children: [
                  for (final r in (a['roleCoverage'] as List).cast<Json>())
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Row(children: [
                        SizedBox(width: 104, child: Text(r['label'] as String, style: const TextStyle(fontSize: 13))),
                        Stars(r['stars'] as int),
                        const SizedBox(width: 8),
                        Expanded(
                            child: Text((r['who'] as List).join(', '),
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis)),
                      ]),
                    ),
                ])),
          ),
        ]);
      }),
      Section(
        '메타 상성',
        subtitle: '유리 ${counts['GOOD'] ?? 0} · 호각 ${counts['EVEN'] ?? 0} · 불리 ${counts['BAD'] ?? 0}  (상대는 가장 흔한 세트 기준, 데미지는 근사치)',
        trailing: SegmentedButton<int>(
          showSelectedIcon: false,
          style: const ButtonStyle(visualDensity: VisualDensity.compact),
          segments: const [
            ButtonSegment(value: 20, label: Text('상위 20')),
            ButtonSegment(value: 40, label: Text('상위 40')),
          ],
          selected: {topN},
          onSelectionChanged: (s) => ref.read(analysisTopNProvider.notifier).state = s.first,
        ),
        child: Column(children: [for (final m in matchups) _MatchupRow(m)]),
      ),
    ]);
  }
}

class _TypeTable extends StatelessWidget {
  final List<Json> members;
  final List<Json> rows;
  const _TypeTable(this.members, this.rows);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Widget cell(num m) {
      if (m == 1) return const SizedBox();
      final (bg, label) = switch (m) {
        >= 4 => (const Color(0xFFB71C1C), '4'),
        >= 2 => (_bad, '2'),
        0 => (cs.outline, '무효'),
        <= 0.25 => (const Color(0xFF0B6B3A), '¼'),
        _ => (_good, '½'),
      };
      return Container(
        margin: const EdgeInsets.all(1.5),
        alignment: Alignment.center,
        decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(4)),
        child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
      );
    }

    return Section(
      '타입 상성표',
      subtitle: '공격받는 타입별 배율 (특성 반영) · 빨강 = 약점, 초록 = 반감',
      child: Table(
        columnWidths: const {0: FixedColumnWidth(54)},
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          TableRow(children: [
            const SizedBox(),
            for (final m in members)
              Tooltip(message: '${m['ko'] ?? m['name']}', child: Center(child: Sprite(m['sprite'] as String, size: 34))),
            const Center(child: Text('약점', style: TextStyle(fontSize: 12))),
            const Center(child: Text('반감', style: TextStyle(fontSize: 12))),
          ]),
          for (final r in rows)
            TableRow(children: [
              Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1.5),
                  child: Align(alignment: Alignment.centerLeft, child: TypeChip(r['type'] as String, dense: true))),
              for (final m in (r['mults'] as List)) SizedBox(height: 22, child: cell(m as num)),
              Center(
                  child: Text('${r['weak']}',
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: (r['weak'] as int) >= 3 ? _bad : ((r['weak'] as int) == 0 ? cs.outline : null)))),
              Center(
                  child: Text('${r['resist']}',
                      style: TextStyle(
                          fontWeight: FontWeight.w700, color: (r['resist'] as int) == 0 ? cs.outline : _good))),
            ]),
        ],
      ),
    );
  }
}

class _MatchupRow extends StatelessWidget {
  final Json m;
  const _MatchupRow(this.m);
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final label = m['label'] as String;
    final color = label == 'GOOD' ? _good : (label == 'BAD' ? _bad : _even);
    final ko = label == 'GOOD' ? '유리' : (label == 'BAD' ? '불리' : '호각');
    final answers = (m['answers'] as List).cast<Json>();
    final threatened = (m['threatened'] as List).cast<Json>();
    Widget mini(Json x, {required bool attack}) => Tooltip(
          message: '${x['ko'] ?? x['name']} · ${x['move'] ?? '-'}',
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Sprite(x['sprite'] as String, size: 26),
            Text('${x['moveKo'] ?? x['move'] ?? '-'} ${fmtPct(x['pct'] as num)}',
                style: TextStyle(fontSize: 12, color: attack ? null : _bad)),
          ]),
        );
    return InkWell(
      onTap: () => context.push('/pokemon/${m['id']}'),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
          Container(
            width: 44,
            padding: const EdgeInsets.symmetric(vertical: 3),
            alignment: Alignment.center,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(6)),
            child: Text(ko, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w700)),
          ),
          SizedBox(
              width: 34,
              child: Text('${(m['score'] as num).round()}',
                  textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700))),
          const SizedBox(width: 6),
          Sprite(m['sprite'] as String, size: 40),
          const SizedBox(width: 6),
          SizedBox(
            width: 120,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${m['ko'] ?? m['name']}',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              Text('#${m['rank']} ${m['name']}',
                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant), maxLines: 1, overflow: TextOverflow.ellipsis),
            ]),
          ),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
                Text('공격', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                for (final x in answers.take(2)) mini(x, attack: true),
              ]),
              if (threatened.isNotEmpty)
                Wrap(spacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  Text('위험', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                  for (final x in threatened.take(3)) mini(x, attack: false),
                ]),
            ]),
          ),
        ]),
      ),
    );
  }
}

/// 팀이 비었을 때: 무엇을 할 수 있는지 + 바로 시작하는 방법
class _EmptyTeam extends StatefulWidget {
  final Future<void> Function() onSample;
  const _EmptyTeam({required this.onSample});
  @override
  State<_EmptyTeam> createState() => _EmptyTeamState();
}

class _EmptyTeamState extends State<_EmptyTeam> {
  bool busy = false;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    Widget step(LabGlyph icon, String title, String text) => SizedBox(
          width: 250,
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            LabIcon(icon, size: 22, color: cs.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                const SizedBox(height: 3),
                Text(text, style: TextStyle(fontSize: 13, height: 1.45, color: cs.onSurfaceVariant)),
              ]),
            ),
          ]),
        );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('팀을 만들면 이런 것을 알려 드립니다',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, letterSpacing: -.2)),
          const SizedBox(height: 18),
          Wrap(spacing: 28, runSpacing: 18, children: [
            step(LabGlyph.book, '전략 가이드', '팀의 운영법, 기본 선출, 조합 활용, 위험한 상대별 대응법'),
            step(LabGlyph.shield, '약점 진단', '타입 약점, 빠진 역할, 물리·특수 편중'),
            step(LabGlyph.meta, '메타 상성', '상위 20~40마리 각각에 유리한지 불리한지와 그 근거'),
            step(LabGlyph.swap, '교체 추천', '한 자리만 바꾼다면 누구를 넣을지'),
          ]),
          const SizedBox(height: 24),
          Row(children: [
            FilledButton.icon(
              onPressed: busy
                  ? null
                  : () async {
                      setState(() => busy = true);
                      try {
                        await widget.onSample();
                      } finally {
                        if (mounted) setState(() => busy = false);
                      }
                    },
              icon: busy
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const LabIcon(LabGlyph.spark, size: 18),
              label: const Text('인기 조합으로 시작'),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text('1위 포켓몬과 가장 자주 함께 쓰이는 5마리를 채웁니다. 위의 + 칸으로 직접 골라도 됩니다.',
                  style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
            ),
          ]),
        ]),
      ),
    );
  }
}
