import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'sim_insights.dart';
import 'party_lab.dart';
import 'party_simulation.dart';
import 'team_switcher.dart';
import '../i18n.dart';

List<Json> partySets(Json party) =>
    [for (final m in (party['members'] as List).cast<Json>()) m['set'] as Json];

class PartiesPage extends ConsumerStatefulWidget {
  const PartiesPage({super.key});

  @override
  ConsumerState<PartiesPage> createState() => _PartiesPageState();
}

enum _PartyTab { ladder, styles, simulation }

class _PartiesPageState extends ConsumerState<PartiesPage> {
  _PartyTab tab = _PartyTab.ladder;
  String? season;

  @override
  Widget build(BuildContext context) {
    final simulated = tab == _PartyTab.simulation;
    final published = tab == _PartyTab.ladder;
    final provider = partiesProvider;
    final data = ref.watch(provider);
    final compact = MediaQuery.sizeOf(context).width < 480;
    final format = ref.watch(formatProvider);
    return PageBody(children: [
      PageHeader('파티 탐색',
          glyph: LabGlyph.archive,
          subtitle: format == 'Doubles' ? '더블배틀' : '싱글배틀',
          trailing: TextButton.icon(
            icon: const LabIcon(LabGlyph.spark, size: 16),
            onPressed: () => context.go('/team/auto'),
            label: const Text('맞춤 팀 생성'),
          )),
      Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Align(
          alignment: Alignment.centerLeft,
          child: SegmentedButton<_PartyTab>(
            selectedIcon: const LabIcon(LabGlyph.check, size: 16),
            showSelectedIcon: !compact,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: [
              const ButtonSegment(
                  value: _PartyTab.ladder, label: Text('랭커 파티')),
              const ButtonSegment(
                  value: _PartyTab.styles, label: Text('전략별 추천')),
              ButtonSegment(
                  value: _PartyTab.simulation,
                  label: Text(compact ? '추천 연구소' : '추천 파티 연구소')),
            ],
            selected: {tab},
            onSelectionChanged: (value) => setState(() => tab = value.first),
          ),
        ),
      ),
      if (simulated)
        const PartyLab()
      else
        AsyncView<Json>(data, (d) {
          final list = published ? 'published' : 'recommended';
          final visible = (d[list] as List)
              .cast<Json>()
              .where(
                  (p) => !published || season == null || p['season'] == season)
              .toList();
          return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (published)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: FilterDropdown(
                      value: season,
                      allLabel: '모든 시즌',
                      labels: {
                        for (final s in (d['seasons'] as List).cast<String>())
                          s: '시즌 $s'
                      },
                      onChanged: (value) => setState(() => season = value),
                    ),
                  ),
                Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Text(published
                        ? '공개 구성 글에서 확인한 파티입니다. 공개 범위에 따라 멤버와 세트 정보가 달라집니다.'
                        : '시즌 ${d['season']}의 메타 상성, 역할 분담과 동료 채용으로 만든 파티입니다.'),
                  ),
                if (visible.isEmpty)
                  Section('등록된 파티가 없습니다',
                      child: Text(published
                          ? '선택한 시즌과 배틀 형식에 등록된 공개 파티가 없습니다.'
                          : '이 배틀 형식의 추천을 만들 데이터가 부족합니다.')),
                for (final party in visible)
                  PartyCard(party: party, key: ValueKey((tab, party['id']))),
              ]);
        }, onRetry: () => ref.invalidate(provider)),
    ]);
  }
}

class PartyCard extends ConsumerStatefulWidget {
  final Json party;
  const PartyCard({super.key, required this.party});

  @override
  ConsumerState<PartyCard> createState() => _PartyCardState();
}

class _PartyCardState extends ConsumerState<PartyCard> {
  bool saving = false;

  Future<void> _save({bool play = false}) async {
    setState(() => saving = true);
    final p = widget.party;
    try {
      await ref
          .read(teamProvider.notifier)
          .saveParty(p['name'] as String, partySets(p), p['format'] as String);
      if (!mounted) return;
      if (play) {
        context.go('/battle');
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: const Text('새 팀으로 저장했습니다'),
        action:
            SnackBarAction(label: tr('팀 빌더'), onPressed: () => context.go('/team')),
      ));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('파티를 저장하지 못했습니다')));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.party;
    final members = (p['members'] as List).cast<Json>();
    final complete = p['complete'] == true;
    final published = p['rank'] != null;
    final fit = (p['fit'] as List? ?? []).cast<Json>();
    final fixedIds = (p['fixedIds'] as List? ?? []).toSet();
    final theme = Theme.of(context);
    return Section(
      p['name'] as String,
      subtitle: published
          ? '${p['season']} · 최종 ${p['rank']}위 · ${p['player']}${p['rating'] == null ? '' : ' · 레이팅 ${p['rating']}'}'
          : p['origin'] != null
              ? '${tr(p['origin']['label'] as String)} · ${tr(p['origin']['detail'] as String)}'
              : '메타 상성 점수 ${p['metaScore']} / 100',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (p['note'] != null) Text(p['note'] as String),
        if (p['simulation'] case final Json simulation)
          PartySimulationResult(simulation, members: members),
        if (p['rankers'] case final Json rankers) RankerMatchups(rankers),
        if (p['tuning'] case final Json tuning) _TuningNotes(tuning),
        if (p['analysis'] != null)
          LabExpansionTile(
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            expandedAlignment: Alignment.centerLeft,
            title: const Text('팀 분석 · 역할, 약점, 운영법'),
            children: [CandidateAnalysis(p), const SizedBox(height: 10)],
          ),
        if (p['profile'] case final Json profile)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(spacing: 6, runSpacing: 4, children: [
              for (final (key, label, icon) in [
                ('fast_attacker', '빠른 공격수', LabGlyph.bolt),
                ('physical', '물리', LabGlyph.versus),
                ('special', '특수', LabGlyph.crystal),
                ('bulky', '내구', LabGlyph.shield),
              ])
                Chip(
                  avatar: LabIcon(icon, size: 14),
                  label: Text("$label ${profile[key]}"),
                  visualDensity: VisualDensity.compact,
                ),
            ]),
          ),
        if (fit.isNotEmpty)
          LabExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: const Text('구성 근거'),
            subtitle: Text(fit
                .map((style) =>
                    '${style['name']} ${style['complete'] == true ? '충족' : '일부 반영'}')
                .join(' · ')),
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            expandedAlignment: Alignment.centerLeft,
            children: [
              for (final style in fit) ...[
                Text(style['name'] as String,
                    style: theme.textTheme.titleSmall),
                for (final role in (style['evidence'] as List).cast<Json>())
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                        '${role['role']}${role['minimum'] == null ? '' : ' ${role['count']}/${role['minimum']}'} · ${(role['members'] as List).isEmpty ? '담당 없음' : (role['members'] as List).join(', ')}'),
                  ),
              ],
            ],
          ),
        const SizedBox(height: 6),
        for (final member in members)
          if (member['set']['moves'] != null)
            LabExpansionTile(
              tilePadding: EdgeInsets.zero,
              leading: Sprite(member['sprite'] as String, size: 40),
              title: Text(
                  '${member['ko'] ?? member['name']}${fixedIds.contains(member['id']) ? ' · 지정' : ''}${member['joker'] == true ? ' · 조커' : ''}'),
              subtitle: Text([
                '${member['itemKo'] ?? member['set']['item'] ?? '도구 없음'}',
                if (member['usageRank'] != null) '사용률 ${member['usageRank']}위',
                if (member['speed'] != null) '스피드 ${member['speed']}',
              ].join(' · ')),
              childrenPadding: const EdgeInsets.only(bottom: 12),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              expandedAlignment: Alignment.centerLeft,
              children: [_SetDetails(member)],
            ),
        if (!complete) ...[
          const Text('공개된 정보 · 멤버 구성'),
          const SizedBox(height: 6),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final member in members)
              if (member['set']['moves'] == null) MonPill(member),
          ]),
        ],
        if (!published)
          for (final warning in (p['warnings'] as List).cast<Json>())
            Text('• ${warning['text']}', style: theme.textTheme.bodySmall),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (complete)
            FilledButton.tonalIcon(
              onPressed: saving ? null : _save,
              icon: const LabIcon(LabGlyph.addList),
              label: Text(saving ? '저장 중' : '새 팀으로 저장'),
            ),
          if (complete && p['simulation'] != null)
            OutlinedButton.icon(
              onPressed: saving ? null : () => _save(play: true),
              icon: const LabIcon(LabGlyph.controller),
              label: const Text('저장하고 배틀'),
            ),
          if (published)
            TextButton.icon(
              onPressed: () async {
                await Clipboard.setData(
                    ClipboardData(text: p['source'] as String));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('출처 주소를 복사했습니다')));
                }
              },
              icon: const LabIcon(LabGlyph.link),
              label: Text('${Uri.parse(p['source'] as String).host} · 출처 복사'),
            ),
        ]),
      ]),
    );
  }
}

class _SetDetails extends StatelessWidget {
  final Json member;
  const _SetDetails(this.member);

  @override
  Widget build(BuildContext context) {
    final s = member['set'] as Json;
    final points = s['points'] as Json;
    final roles = (member['roles'] as List).cast<Json>();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text([
        member['abilityKo'] ?? s['ability'] ?? '특성 정보 없음',
        if (member['megaAbility'] != null &&
            member['megaAbility'] != s['ability'])
          '메가 후 ${member['megaAbility']}',
        natureLabel(s['nature'] as String, member['natureKo'] as String?),
      ].join(' · ')),
      const SizedBox(height: 5),
      Text(
          '능력 포인트 (HP/공격/방어/특공/특방/스피드)  ${statKeys.map((k) => points[k] ?? 0).join(' / ')}'),
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 6, children: [
        for (final m in (member['moveInfo'] as List).cast<Json>())
          MoveChip(m['name'] as String,
              ko: m['ko'] as String?, type: m['type'] as String?),
      ]),
      if (roles.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(roles.map((r) => r['label']).join(' · ')),
        ),
    ]);
  }
}

/// 세트 최적화 결과: 채택된 변경과 시험한 수
class _TuningNotes extends StatelessWidget {
  final Json tuning;
  const _TuningNotes(this.tuning);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final changes = (tuning['changes'] as List? ?? const []).cast<Json>();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('세트 최적화', style: theme.textTheme.titleSmall),
        const SizedBox(height: 4),
        Text(
            tr('변경 후보 {}개를 {}판씩 시험하고, 나아 보인 {}개를 새 상대와 {}판씩 다시 확인했습니다.')
                .replaceFirst('{}', '${tuning['tried'] ?? 0}')
                .replaceFirst('{}', '${tuning['screenRuns'] ?? 0}')
                .replaceFirst('{}', '${tuning['screened'] ?? 0}')
                .replaceFirst('{}', '${tuning['confirmRuns'] ?? 0}'),
            style: theme.textTheme.bodySmall),
        const SizedBox(height: 6),
        if (changes.isEmpty)
          const Text('사용률 세트보다 확실히 나은 변경이 없어 그대로 두었습니다.')
        else ...[
          for (final c in changes)
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text(tr('{} · {} · {} (승률 +{}%p)')
                  .replaceFirst('{}', '${c['name']}')
                  .replaceFirst('{}', tr(c['kind'] as String))
                  .replaceFirst('{}', '${c['change']}')
                  .replaceFirst('{}', '${c['gain']}')),
            ),
          if (tuning['base'] != null && tuning['tuned'] != null)
            Text(
                tr('최종 확인 · 기존 {} → 최적화 {}')
                    .replaceFirst('{}', fmtPct(100 * (tuning['base'] as num)))
                    .replaceFirst('{}', fmtPct(100 * (tuning['tuned'] as num))),
                style: theme.textTheme.bodySmall),
        ],
      ]),
    );
  }
}
