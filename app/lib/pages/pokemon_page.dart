import 'dart:convert';

import '../lab_icons.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'duel_dialog.dart';
import 'pokemon_overview.dart';
import 'team_page.dart';

/// 포켓몬 연구실: 세트를 고르고 → 상대별 우열, 추천 파트너, 운용법, 채용 통계를 본다.
class PokemonPage extends ConsumerStatefulWidget {
  final String id;
  const PokemonPage({super.key, required this.id});
  @override
  ConsumerState<PokemonPage> createState() => _PokemonPageState();
}

class _PokemonPageState extends ConsumerState<PokemonPage> {
  Json? custom; // 대표 세트를 고르거나 직접 편집한 세트
  String source = 'auto'; // auto(팀 세트가 있으면 팀, 없으면 인기 세트) | 대표 세트 라벨 | custom
  String tab = 'matchup';
  int topN = 20;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final id = widget.id;
    final detail = ref.watch(pokemonDetailProvider(id));
    final fmt = ref.watch(formatProvider);
    final team = ref.watch(teamProvider);
    final teamIndex = team.indexWhere((s) => s.detail['id'] == id);
    final teamSet = teamIndex >= 0 ? team[teamIndex].set : null;

    return AsyncView<Json>(detail, (d) {
      final baseSet = custom ?? teamSet ?? d['defaultSet'] as Json;
      final set = <String, dynamic>{...baseSet, 'id': id};
      final usingTeam = custom == null && teamSet != null;
      final lab = ref.watch(labProvider((id, jsonEncode(set), topN)));
      final me = lab.valueOrNull?['me'] as Json?;
      final variants = ((lab.valueOrNull?['variants'] ?? const []) as List).cast<Json>();

      void pick(String src, Json? s) => setState(() {
            source = src;
            custom = s == null ? null : Json.from(s);
          });

      Future<void> compareWith() async {
        final all = await ref.read(pokemonListProvider.future);
        if (!context.mounted) return;
        final foe = await showPokemonPicker(context, all, fmt);
        if (foe != null && context.mounted) {
          showDialog(context: context, builder: (_) => DuelDialog(mySet: set, foeId: foe['id'] as String));
        }
      }

      final rank = d['rank'];
      return PageBody(children: [
        // ---------------------------------------------------------------- 머리말 + 세트 선택
        Card(
          margin: const EdgeInsets.only(bottom: 16),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Sprite((me?['sprite'] ?? d['sprite']) as String, size: 96),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${me?['ko'] ?? d['ko'] ?? d['name']}',
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: -.5)),
                    Text('${me?['name'] ?? d['name']} · ${fmt == 'Doubles' ? '더블' : '싱글'} ${rank == null ? '데이터 없음' : '$rank위'}',
                        style: TextStyle(fontSize: 13.5, color: cs.onSurfaceVariant)),
                    const SizedBox(height: 8),
                    TypeRow((me?['types'] ?? d['types']) as List),
                    if (me != null) ...[
                      const SizedBox(height: 8),
                      Text((me['roles'] as List).map((r) => r['label']).join(' · '),
                          style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                    ],
                  ]),
                ),
                if (teamIndex < 0)
                  FilledButton.icon(
                    icon: const LabIcon(LabGlyph.plus, size: 18),
                    label: Text(team.length >= 6 ? '팀이 가득 참' : '이 세트로 팀에 추가'),
                    onPressed: team.length >= 6
                        ? null
                        : () async {
                            await ref.read(teamProvider.notifier).add(id, set: set);
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                                  content: Text('${d['ko'] ?? d['name']} — 팀에 추가했습니다'),
                                  action: SnackBarAction(label: '팀 보기', onPressed: () => context.go('/team'))));
                            }
                          },
                  )
                else if (!usingTeam)
                  OutlinedButton.icon(
                    icon: const LabIcon(LabGlyph.save, size: 18),
                    label: const Text('내 팀 세트로 저장'),
                    onPressed: () {
                      ref.read(teamProvider.notifier).update(teamIndex, set);
                      pick('auto', null);
                    },
                  ),
              ]),
              const Padding(padding: EdgeInsets.symmetric(vertical: 16), child: Divider()),
              Row(children: [
                const Text('분석할 세트', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                const SizedBox(width: 8),
                Expanded(
                    child: Text('세트를 바꾸면 아래 상성·파트너·운용법이 그 세트 기준으로 다시 계산됩니다',
                        style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant))),
              ]),
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                if (teamSet != null)
                  ChoiceChip(
                      avatar: const LabIcon(LabGlyph.team, size: 16),
                      label: const Text('내 팀 세트'),
                      selected: usingTeam,
                      onSelected: (_) => pick('auto', null)),
                for (final v in variants)
                  ChoiceChip(
                      label: Text('${v['label']}${v['pct'] != null ? ' ${fmtPct(v['pct'] as num)}' : ''}'),
                      selected: !usingTeam && (source == v['label'] || (custom == null && v == variants.first)),
                      onSelected: (_) => pick(v['label'] as String, v['set'] as Json)),
                if (source == 'custom') const ChoiceChip(label: Text('직접 편집'), selected: true),
                ActionChip(
                    avatar: const LabIcon(LabGlyph.tune, size: 16),
                    label: const Text('세트 편집'),
                    onPressed: () => showDialog(
                        context: context,
                        builder: (_) => SetEditor(slot: TeamSlot(set, d), onChanged: (v) => pick('custom', v)))),
              ]),
              if (me != null) ...[
                const SizedBox(height: 14),
                Wrap(spacing: 18, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    ItemIcon(me['item'] as String?, size: 20),
                    const SizedBox(width: 6),
                    Text('${me['itemKo'] ?? me['item'] ?? '도구 없음'}', style: const TextStyle(fontSize: 13.5)),
                  ]),
                  Text('${me['abilityKo'] ?? me['ability']}', style: const TextStyle(fontSize: 13.5)),
                  Text(natureLabel(me['nature'] as String, me['natureKo'] as String?),
                      style: const TextStyle(fontSize: 13.5)),
                  Text(
                      statKeys.map((k) => '${statKo[k]} ${(me['stats'] as Json)[k]}').join('  ') +
                          ((me['speed'] as num) != ((me['stats'] as Json)['spe'] as num)
                              ? '  (실전 스피드 ${(me['speed'] as num).round()})'
                              : ''),
                      style: TextStyle(
                          fontSize: 12.5, color: cs.onSurfaceVariant, fontFeatures: const [FontFeature.tabularFigures()])),
                ]),
                const SizedBox(height: 10),
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final m in (me['moveInfo'] as List).cast<Json>())
                    MoveChip(m['name'] as String, ko: m['ko'] as String?, type: m['type'] as String?),
                ]),
              ],
            ]),
          ),
        ),
        // ---------------------------------------------------------------- 탭
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Align(
            alignment: Alignment.centerLeft,
            child: SegmentedButton<String>(
              showSelectedIcon: false,
              segments: [
                const ButtonSegment(value: 'matchup', icon: LabIcon(LabGlyph.swap, size: 18), label: Text('상대별 우열')),
                ButtonSegment(
                    value: 'partner',
                    icon: const LabIcon(LabGlyph.team, size: 18),
                    label: Text(fmt == 'Doubles' ? '파트너 · 운용법' : '교체 파트너 · 운용법')),
                const ButtonSegment(value: 'stats', icon: LabIcon(LabGlyph.meta, size: 18), label: Text('채용 통계')),
              ],
              selected: {tab},
              onSelectionChanged: (s) => setState(() => tab = s.first),
            ),
          ),
        ),
        if (tab == 'stats')
          PokemonOverview(id: id)
        else
          AsyncView<Json>(lab, (l) {
            if (tab == 'matchup') {
              return _MatchupTab(
                  lab: l,
                  topN: topN,
                  onTopN: (v) => setState(() => topN = v),
                  onCompare: compareWith,
                  onOpen: (foeId) =>
                      showDialog(context: context, builder: (_) => DuelDialog(mySet: set, foeId: foeId)));
            }
            return _PartnerTab(lab: l, doubles: fmt == 'Doubles');
          }, onRetry: () => ref.invalidate(labProvider((id, jsonEncode(set), topN)))),
      ]);
    }, onRetry: () => ref.invalidate(pokemonDetailProvider(id)));
  }
}

// ==================================================================== 상대별 우열

class _MatchupTab extends StatelessWidget {
  final Json lab;
  final int topN;
  final ValueChanged<int> onTopN;
  final VoidCallback onCompare;
  final ValueChanged<String> onOpen;
  const _MatchupTab(
      {required this.lab, required this.topN, required this.onTopN, required this.onCompare, required this.onOpen});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final rows = (lab['table'] as List).cast<Json>();
    final count = lab['count'] as Json;
    final head = TextStyle(fontSize: 12, color: cs.onSurfaceVariant, fontWeight: FontWeight.w500);

    Widget hit(Json? h, Color color) {
      if (h == null) return Text('유효타 없음', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant));
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          TypeDot(h['type'] as String?),
          const SizedBox(width: 6),
          Flexible(
              child: Text('${h['ko'] ?? h['move']}',
                  style: const TextStyle(fontSize: 13.5), maxLines: 1, overflow: TextOverflow.ellipsis)),
          const SizedBox(width: 8),
          Text((h['max'] as num) <= 0 ? '효과 없음' : '${(h['min'] as num).round()}~${(h['max'] as num).round()}%',
              style: const TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w700, fontFeatures: [FontFeature.tabularFigures()])),
          const SizedBox(width: 6),
          Text('${h['koText']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
        ]),
        const SizedBox(height: 5),
        DamageBar(min: h['min'] as num, max: h['max'] as num, color: color),
      ]);
    }

    return Section(
      '메타 상위 $topN마리와의 1:1 우열',
      subtitle: '유리 ${count['WIN']} · 호각 ${count['EVEN']} · 불리 ${count['LOSE']}  —  서로 가장 아픈 기술만 눌렀을 때 누가 먼저 쓰러뜨리는지. 행을 누르면 기술별 상세',
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        SegmentedButton<int>(
          showSelectedIcon: false,
          style: const ButtonStyle(visualDensity: VisualDensity.compact),
          segments: const [
            ButtonSegment(value: 20, label: Text('상위 20')),
            ButtonSegment(value: 40, label: Text('상위 40')),
          ],
          selected: {topN},
          onSelectionChanged: (s) => onTopN(s.first),
        ),
        const SizedBox(width: 8),
        OutlinedButton.icon(
            onPressed: onCompare, icon: const LabIcon(LabGlyph.search, size: 18), label: const Text('다른 포켓몬과 비교')),
      ]),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
          child: Row(children: [
            SizedBox(width: 58, child: Text('우열', style: head)),
            SizedBox(width: 190, child: Text('상대', style: head)),
            Expanded(child: Text('내가 주는 데미지', style: head)),
            const SizedBox(width: 20),
            Expanded(child: Text('내가 받는 데미지', style: head)),
            SizedBox(width: 60, child: Text('스피드', style: head, textAlign: TextAlign.center)),
          ]),
        ),
        const Divider(),
        for (final r in rows)
          InkWell(
            onTap: () => onOpen(r['id'] as String),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 4),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: cs.outlineVariant))),
              child: Row(children: [
                SizedBox(
                    width: 58,
                    child: Align(
                        alignment: Alignment.centerLeft,
                        child: VerdictBadge((r['verdict'] as Json)['label'] as String))),
                SizedBox(
                  width: 190,
                  child: Row(children: [
                    Sprite(r['sprite'] as String, size: 40),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('${r['ko'] ?? r['name']}',
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                        Text('${r['rank']}위 · ${r['name']}',
                            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ]),
                    ),
                  ]),
                ),
                Expanded(child: hit(r['mine'] as Json?, good)),
                const SizedBox(width: 20),
                Expanded(child: hit(r['theirs'] as Json?, bad)),
                SizedBox(
                  width: 60,
                  child: Center(
                    child: switch ((r['verdict'] as Json)['speed']) {
                      'fast' => const Text('선공', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: good)),
                      'slow' => Text('후공', style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
                      _ => const Text('동속', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: even)),
                    },
                  ),
                ),
              ]),
            ),
          ),
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text('상대는 가장 흔한 세트 기준입니다. 상세 창에서 상대 도구를 바꿔 볼 수 있습니다. 데미지는 난수 85~100% 범위의 근사치입니다.',
              style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
        ),
      ]),
    );
  }
}

// ==================================================================== 파트너 · 운용법

class _PartnerTab extends ConsumerWidget {
  final Json lab;
  final bool doubles;
  const _PartnerTab({required this.lab, required this.doubles});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final partners = (lab['partners'] as List).cast<Json>();
    final book = lab['playbook'] as Json;
    final team = ref.watch(teamProvider);
    final body = TextStyle(fontSize: 14, height: 1.55, color: cs.onSurface);

    Widget typed(String text) {
      if (!text.startsWith('TYPES:')) return Text(text, style: body);
      return Wrap(spacing: 4, runSpacing: 4, children: [for (final t in text.substring(6).split(',')) TypeChip(t)]);
    }

    final playbook = Section(
      '운용법',
      subtitle: '이 세트를 실전에서 굴리는 방법',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final t in (book['tips'] as List).cast<Json>())
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                  width: 112,
                  child: Text(t['title'] as String,
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: cs.primary, height: 1.6))),
              Expanded(child: typed(t['text'] as String)),
            ]),
          ),
        const Padding(padding: EdgeInsets.symmetric(vertical: 6), child: Divider()),
        const SizedBox(height: 8),
        const Text('기술별 쓰임', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        for (final m in (book['moves'] as List).cast<Json>())
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(
                  width: 150,
                  child: Align(
                      alignment: Alignment.centerLeft,
                      child: MoveChip(m['name'] as String, ko: m['ko'] as String?, type: m['type'] as String?))),
              const SizedBox(width: 10),
              Expanded(
                  child: Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(m['note'] as String,
                          style: TextStyle(fontSize: 13.5, height: 1.5, color: cs.onSurface)))),
            ]),
          ),
      ]),
    );

    final partnerSection = Section(
      doubles ? '추천 파트너' : '함께 넣기 좋은 포켓몬',
      subtitle: doubles
          ? '실제 동료 채용 순위 + 내가 불리한 상대를 대신 잡는지 + 타입·기술 궁합으로 점수를 매겼습니다'
          : '실제 동료 채용 순위 + 내가 불리한 상대를 대신 잡는지 + 타입 궁합으로 점수를 매겼습니다',
      child: partners.isEmpty
          ? Text('추천할 만한 파트너를 찾지 못했습니다', style: TextStyle(color: cs.onSurfaceVariant))
          : Column(children: [
              for (final p in partners)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(border: Border(bottom: BorderSide(color: cs.outlineVariant))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    InkWell(
                      borderRadius: BorderRadius.circular(8),
                      onTap: () => context.push('/pokemon/${p['id']}'),
                      child: SizedBox(
                        width: 190,
                        child: Row(children: [
                          Sprite(p['sprite'] as String, size: 52),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text('${p['ko'] ?? p['name']}',
                                  style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis),
                              Text('${p['rank']}위 · ${(p['roles'] as List).take(2).join(' · ')}',
                                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis),
                            ]),
                          ),
                        ]),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        for (final w in (p['why'] as List))
                          Padding(
                            padding: const EdgeInsets.only(bottom: 3),
                            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Padding(
                                padding: const EdgeInsets.only(top: 3, right: 7),
                                child: LabIcon('$w'.startsWith('주의') ? LabGlyph.alert : LabGlyph.check,
                                    size: 15, color: '$w'.startsWith('주의') ? even : cs.primary),
                              ),
                              Expanded(child: Text('$w', style: TextStyle(fontSize: 13.5, height: 1.45, color: cs.onSurface))),
                            ]),
                          ),
                        if ((p['resists'] as List).isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Wrap(spacing: 4, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                              Text('내 약점을 받아 줌  ', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                              for (final t in (p['resists'] as List)) TypeChip(t as String, dense: true),
                            ]),
                          ),
                      ]),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                        onPressed: team.length >= 6 || team.any((s) => s.detail['id'] == p['id'])
                            ? null
                            : () => ref.read(teamProvider.notifier).add(p['id'] as String, set: p['set'] as Json),
                        child: Text(team.any((s) => s.detail['id'] == p['id']) ? '팀에 있음' : '팀에 추가')),
                  ]),
                ),
            ]),
    );

    return LayoutBuilder(builder: (context, c) {
      if (c.maxWidth >= 1040) {
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(flex: 11, child: partnerSection),
          const SizedBox(width: 16),
          Expanded(flex: 9, child: playbook),
        ]);
      }
      return Column(children: [playbook, partnerSection]);
    });
  }
}
