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
import 'team_guide.dart';
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

  Future<void> _save({bool play = false, Json? practice}) async {
    setState(() => saving = true);
    final p = widget.party;
    try {
      await ref
          .read(teamProvider.notifier)
          .saveParty(p['name'] as String, partySets(p), p['format'] as String);
      if (!mounted) return;
      if (play) {
        context.go('/battle', extra: practice);
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
        if (p['holdout'] case final Json sample)
          LabExpansionTile(
            title: Text("보류 상대 · ${fmtPct(100 * (sample['rate'] as num))} · ${sample['runs']}판"),
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("탐색에서 제외한 합성 코어 ${sample['coreCount']}종 · 마스터볼 CPU"),
              if (sample['ci'] case final List interval)
                Text("코어 기준 95% 추정 범위 ${fmtPct(100 * (interval[0] as num))}–${fmtPct(100 * (interval[1] as num))}"),
              for (final match in (sample['strategies'] as List).cast<Json>())
                Text("${match['label']} · ${match['runs']}판 · ${match['win']}승 ${match['draw']}무 ${match['loss']}패"),
            ],
          ),
        if (p['guide'] case final Json guide)
          LabExpansionTile(
            title: const Text('선출과 운영 가이드'),
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
            children: [TeamGuide(guide,
              sets: partySets(p),
              format: p['format'] as String,
              onPractice: (plan) {
                if (!saving) _save(play: true, practice: plan);
              },
            )],
          ),
        if (p['rankers'] case final Json rankers) RankerMatchups(rankers),
        if (p['rosterSearch'] is List && (p['rosterSearch'] as List).isNotEmpty)
          PartyRosterChanges((p['rosterSearch'] as List).cast<Json>()),
        if (p['strategy'] case final Json strategy)
          _StrategyPanel(
              strategy: strategy,
              metrics: p['metrics'] as Json? ?? const {},
              counterfactual: p['counterfactual'] as Json?,
              causes: (p['lossCauses'] as List? ?? const []).cast<Json>()),
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
              if (p['fromResearch'] == true)
                const Chip(
                  avatar: LabIcon(LabGlyph.spark, size: 14),
                  label: Text('자동 연구에서 발견'),
                  visualDensity: VisualDensity.compact,
                ),
              if (p['rankerOverlap'] case final Json overlap)
                Chip(
                  avatar: const LabIcon(LabGlyph.archive, size: 14),
                  label: Text(tr('랭커 파티와 겹침 {}/6 · {} {}위 {}')
                      .replaceFirst('{}', '${overlap['count']}')
                      .replaceFirst('{}', '${overlap['season']}')
                      .replaceFirst('{}', '${overlap['rank']}')
                      .replaceFirst('{}', '${overlap['player']}')),
                  visualDensity: VisualDensity.compact,
                ),
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

/// V2 엔진 결과: 전략 태그와 근거, 승리 조건 2개, 다목적 지표, 패배 원인, 일관성 경고
class _StrategyPanel extends StatelessWidget {
  const _StrategyPanel(
      {required this.strategy, required this.metrics, required this.causes, this.counterfactual});
  final Json strategy;
  final Json metrics;
  final Json? counterfactual;
  final List<Json> causes;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final tags = (strategy['tags'] as List).cast<Json>();
    final warnings = (strategy['warnings'] as List? ?? const []).cast<String>();
    final zero = (metrics['zeroPick'] as List? ?? const []).cast<String>();
    String pct(Object? v) => v is num ? fmtPct(100 * v) : '-';
    Widget metric(String label, String value) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(10)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(label, style: theme.textTheme.bodySmall),
            Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
          ]),
        );
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: cs.surfaceContainerHigh, borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          if (metrics['profile'] case final String profile)
            Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
              decoration: BoxDecoration(color: cs.primary.withOpacity(.18), borderRadius: BorderRadius.circular(20)),
              child: Text(profile, style: TextStyle(color: cs.primary, fontWeight: FontWeight.w800, fontSize: 12.5)),
            ),
          Expanded(child: Text('왜 이 팀인가', style: theme.textTheme.titleSmall)),
        ]),
        const SizedBox(height: 8),
        const Text('6마리 구성에서 발견한 전략 요소'),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 4, children: [
          for (final t in tags)
            Tooltip(
              message: t['why'] as String,
              child: Chip(label: Text(t['label'] as String), visualDensity: VisualDensity.compact),
            ),
        ]),
        const SizedBox(height: 8),
        if (metrics['leagues'] case final Map leagues) ...[
          Text('랭크별 상대 CPU 성적', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          for (final name in ['몬스터볼', '하이퍼볼', '마스터볼', '챔피언'])
            if (leagues[name] case final Map l)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Row(children: [
                  SizedBox(width: 74, child: Text(name, style: const TextStyle(fontWeight: FontWeight.w700))),
                  Expanded(
                    child: Text(tr('{} · 95% 범위 {}~{}% · {}판')
                        .replaceFirst('{}', pct(l['rate']))
                        .replaceFirst('{}', '${(l['ci'] as List)[0]}')
                        .replaceFirst('{}', '${(l['ci'] as List)[1]}')
                        .replaceFirst('{}', '${l['games']}')),
                  ),
                ]),
              ),
          if (metrics['stress'] case final Map st)
            Text(
                tr('스트레스 리그 · {} 상대만, 카운터형 CPU · {} ({}판)')
                    .replaceFirst('{}', tr('${st['against']}'))
                    .replaceFirst('{}', pct(st['rate']))
                    .replaceFirst('{}', '${st['games']}'),
                style: theme.textTheme.bodySmall),
          Text('승률은 앱의 배틀 엔진과 CPU 기준이며 실제 랭크전 승률이 아닙니다.', style: theme.textTheme.bodySmall),
          const SizedBox(height: 8),
        ],
        Wrap(spacing: 8, runSpacing: 8, children: [
          metric('평균 승률', pct(metrics['winRate'])),
          metric('가장 어려운 전략 2개', pct(metrics['lowerTail'])),
          metric('높은 랭크 상대 (낮은 쪽)', pct(metrics['otherPolicy'])),
          metric('쓸 만한 선봉', tr('{}가지').replaceFirst('{}', '${metrics['leadOptions'] ?? '-'}')),
          metric('랭커 파티와 다른 수', tr('{}마리').replaceFirst('{}', '${metrics['novelty'] ?? '-'}')),
        ]),
        if (metrics['originality'] case final Map o) ...[
          const SizedBox(height: 10),
          Text('독창성 (랭커 팀과 얼마나 다른가)', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          for (final (key, label) in const [
            ('species', '종 구성'),
            ('set', '세트 (도구·기술)'),
            ('tactical', '운영 (전략·선출)'),
            ('synergy', '새 조합 쌍'),
            ('viability', '실전성 (챔피언 리그)'),
          ])
            if (o[key] case final num v)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Row(children: [
                  SizedBox(width: 128, child: Text(tr(label), style: theme.textTheme.bodySmall)),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                          value: v.toDouble().clamp(0, 1), minHeight: 7, backgroundColor: cs.surfaceContainer),
                    ),
                  ),
                  SizedBox(
                      width: 40,
                      child: Text('${(100 * v).round()}',
                          textAlign: TextAlign.right, style: theme.textTheme.bodySmall)),
                ]),
              ),
          if (o['overall'] case final num overall)
            Text(tr('종합 {} · 네 가지 평균 × 실전성 (비주류만 넣어서는 오르지 않음)').replaceFirst('{}', '${(100 * overall).round()}'),
                style: theme.textTheme.bodySmall),
        ],
        if (counterfactual case final Json cf)
          if ((cf['levers'] as List? ?? const []).isNotEmpty) ...[
            const SizedBox(height: 10),
            Text('무엇을 바꿨을 때 나아졌나 (검증된 변경만)', style: theme.textTheme.titleSmall),
            for (final l in (cf['levers'] as List).cast<Json>())
              Text(
                  tr('{} · {} · {}')
                      .replaceFirst('{}', tr(l['label'] as String))
                      .replaceFirst('{}', l['adopted'] == true ? '${_signed(100 * (l['gain'] as num))}%p' : tr('변화 없음'))
                      .replaceFirst('{}', tr(l['detail'] as String)),
                  style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: cf['main'] == l['lever'] ? FontWeight.w800 : null)),
          ],
        if (zero.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(tr('거의 선출되지 않는 포켓몬 · {}').replaceFirst('{}', zero.join(', ')),
                style: TextStyle(color: cs.error, fontSize: 12.5)),
          ),
        if ((metrics['policy'] as List? ?? const []).isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('선출 계획 (같은 6마리로 상대별 선봉·후발을 시험)', style: theme.textTheme.titleSmall),
          for (final row in (metrics['policy'] as List).cast<Json>())
            if ((row['tried'] as int? ?? 0) > 0)
              Text(
                  row['adopted'] == true
                      ? tr('{} 상대 · 선봉 {} · 후발 {} · 채택 {}%p (95% {}~{}, {}판)')
                          .replaceFirst('{}', tr('${row['label']}'))
                          .replaceFirst('{}', (row['leads'] as List).join('+'))
                          .replaceFirst('{}', (row['back'] as List).join('+'))
                          .replaceFirst('{}', _signed(100 * (row['diff'] as num)))
                          .replaceFirst('{}', _signed(100 * (row['low'] as num)))
                          .replaceFirst('{}', _signed(100 * (row['high'] as num)))
                          .replaceFirst('{}', '${row['games']}')
                      : tr('{} 상대 · 기본 선출 유지 (더 나은 선출을 확인하지 못함)')
                          .replaceFirst('{}', tr('${row['label']}')),
                  style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: row['adopted'] == true ? FontWeight.w700 : null)),
        ],
        if ((metrics['cpuStyles'] as List? ?? const []).isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('마스터볼 CPU 플레이 스타일별', style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 4, children: [
            for (final st in (metrics['cpuStyles'] as List).cast<Json>())
              Chip(
                label: Text(tr('{} {} ({}판)')
                    .replaceFirst('{}', tr('${st['label']}'))
                    .replaceFirst('{}', pct(st['rate']))
                    .replaceFirst('{}', '${st['runs']}')),
                visualDensity: VisualDensity.compact,
              ),
          ]),
        ],
        if ((metrics['plans'] as List? ?? const []).isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('상대 전략별 선출 (실제 모의전에서 가장 많이 쓴 4마리)', style: theme.textTheme.titleSmall),
          for (final plan in (metrics['plans'] as List).cast<Json>().take(6))
            Text(
                tr('{} 상대 · 선봉 {} · 후발 {} · 첫 턴 {} · {}판 {}승')
                    .replaceFirst('{}', tr('${plan['against']}'))
                    .replaceFirst('{}', (plan['leads'] as List).join('+'))
                    .replaceFirst('{}', (plan['back'] as List).join('+'))
                    .replaceFirst('{}', (plan['opening'] as List).isEmpty ? '-' : (plan['opening'] as List).join(' / '))
                    .replaceFirst('{}', '${plan['runs']}')
                    .replaceFirst('{}', '${plan['win']}'),
                style: theme.textTheme.bodySmall),
        ],
        if ((metrics['lossTags'] as List? ?? const []).isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('진 판에서 실제로 일어난 일', style: theme.textTheme.titleSmall),
          for (final t in (metrics['lossTags'] as List).cast<Json>().take(4))
            Text(
                tr('{} · 진 판의 {}')
                    .replaceFirst('{}', tr(t['label'] as String))
                    .replaceFirst('{}', fmtPct(100 * (t['share'] as num))),
                style: theme.textTheme.bodySmall),
        ],
        if (causes.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text('자주 지는 이유', style: theme.textTheme.titleSmall),
          for (final c in causes.take(3))
            Text(
                tr('{} · 진 판의 {} · 상대가 전개했을 때 {} 패배')
                    .replaceFirst('{}', tr(c['label'] as String))
                    .replaceFirst('{}', fmtPct(100 * (c['shareOfLosses'] as num)))
                    .replaceFirst('{}', fmtPct(100 * (c['lossRateWhenUsed'] as num))),
                style: theme.textTheme.bodySmall),
        ],
        for (final w in warnings)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text('⚠ ${tr(w)}', style: TextStyle(color: cs.error, fontSize: 12.5)),
          ),
      ]),
    );
  }
}

String _signed(num v) => '${v >= 0 ? '+' : ''}${v.toStringAsFixed(1)}';
