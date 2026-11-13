import 'package:flutter/material.dart' hide Text, Tooltip;

import '../api.dart';
import '../widgets.dart';
import 'sim_insights.dart';
import '../i18n.dart';

class PartyEvaluationSummary extends StatelessWidget {
  final Json evaluation;
  final List<Json> candidates;
  const PartyEvaluationSummary(this.evaluation,
      {super.key, required this.candidates});

  @override
  Widget build(BuildContext context) {
    final stable = evaluation['objective'] == 'stability';
    final ranker = evaluation['objective'] == 'ranker' &&
        ((evaluation['rankerGames'] as num?) ?? 0) > 0;
    final search = evaluation['rosterSearch'] as Json?;
    return Section(
      ranker ? '메타·랭커 종합 순위' : stable ? '전략별 안정성 순위' : '시뮬레이션 승률 순위',
      subtitle:
          "${evaluation['screened']}팀을 각각 ${evaluation['screenRuns']}판씩 평가하고, "
          "${evaluation['finalists']}팀을 새 상대군에서 ${evaluation['finalRuns']}판씩 다시 검증했습니다.",
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          ranker
              ? '메타 상대군과 랭커 파티 전적을 반씩 반영합니다.'
              : stable
              ? tr('팀마다 같은 상대 로스터를 만납니다. {} CPU 기준으로 가장 어려웠던 전략의 승률이 높은 팀을 먼저 표시합니다.')
                  .replaceFirst('{}', tr(cpuLabels[evaluation['cpu']] ?? '하이퍼볼'))
              : tr('팀마다 같은 상대 로스터를 만납니다. {} CPU 기준 최종 검증 승률이 높은 팀을 먼저 표시합니다.')
                  .replaceFirst('{}', tr(cpuLabels[evaluation['cpu']] ?? '하이퍼볼')),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        if (search != null && (search['tested'] as int) > 0) ...[
          const SizedBox(height: 5),
          Text(
            '멤버 교체 실험 · ${search['rounds']}라운드 · ${search['tested']}개 조합 · ${search['accepted']}개 개선 확인',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
        const SizedBox(height: 12),
        CandidateComparison(candidates),
        const SizedBox(height: 6),
        for (final (i, team) in candidates.indexed)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Text("${i + 1}위 · ${team['name']} · ${_comparison(team['simulation'] as Json, ranker: ranker)}",
                style: Theme.of(context).textTheme.bodySmall),
          ),
      ]),
    );
  }

  static String _comparison(Json result, {required bool ranker}) {
    if (result['rankerRate'] case final num rate when ranker) {
      final meta = ((result['win'] as int) + .5 * (result['draw'] as int)) / (result['runs'] as int);
      return '종합 ${fmtPct(50 * (meta + rate))}';
    }
    final worst = (result['strategies'] as List).first as Json;
    return "전체 ${_winRate(result)} · 최저 ${_winRate(worst)} (${worst['label']})";
  }
}

class PartyRosterChanges extends StatelessWidget {
  const PartyRosterChanges(this.steps, {super.key});

  final List<Json> steps;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return LabExpansionTile(
      tilePadding: EdgeInsets.zero,
      expandedCrossAxisAlignment: CrossAxisAlignment.start,
      expandedAlignment: Alignment.centerLeft,
      title: const Text('포켓몬 교체 내역'),
      children: [
        for (final step in steps)
          Padding(
            padding: const EdgeInsets.only(bottom: 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${step['strategy']} 상대 대응', style: theme.textTheme.titleSmall),
              if ((step['threats'] as List).isNotEmpty)
                Text(
                  '패배 경기에서 주목한 상대 · ${(step['threats'] as List).map((m) => m['ko'] ?? m['name']).join(' · ')}',
                  style: theme.textTheme.bodySmall,
                ),
              for (final swap in (step['swaps'] as List).cast<Json>())
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Wrap(spacing: 8, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                    MonPill(swap['out'] as Json),
                    const Text('→'),
                    MonPill(swap['in'] as Json),
                  ]),
                ),
              Text('교체 확인전 · ${_record(step['before'] as Json)} → ${_record(step['after'] as Json)}'),
              Text(
                '해당 전략 상대 · ${_record(step['before'] as Json, strategy: true)} → ${_record(step['after'] as Json, strategy: true)}',
                style: theme.textTheme.bodySmall,
              ),
              if ((step['before'] as Json)['rankerRate'] case final num before)
                Text(
                  '랭커 상대 · ${fmtPct(100 * before)} → ${fmtPct(100 * (step['after'] as Json)['rankerRate'])}',
                  style: theme.textTheme.bodySmall,
                ),
            ]),
          ),
      ],
    );
  }

  static String _record(Json row, {bool strategy = false}) =>
      tr("${row[strategy ? 'strategyWins' : 'wins']}승/${row[strategy ? 'strategyRuns' : 'runs']}판");
}

class PartySimulationResult extends StatelessWidget {
  final Json result;
  final List<Json> members;
  const PartySimulationResult(this.result, {super.key, required this.members});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final runs = result['runs'] as int;
    final strategies = (result['strategies'] as List).cast<Json>();
    final strategyUse = (result['strategyUse'] as List? ?? []).cast<Json>();
    final weakest = strategies.first;
    final lead = result['lead'] as Json;
    final names = {
      for (final member in members)
        member['id']: member['ko'] ?? member['name'],
    };
    final leads =
        (lead['ids'] as List).map((id) => names[id] ?? id).join(' + ');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('검증 승률 ${_winRate(result)}', style: theme.textTheme.titleMedium),
        Text(
            "$runs판 · ${result['win']}승 ${result['loss']}패 ${result['draw']}무"),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(5),
          child: Row(children: [
            for (final (key, color) in [
              ('win', cs.primary),
              ('draw', cs.outlineVariant),
              ('loss', cs.error),
            ])
              if ((result[key] as int) > 0)
                Expanded(
                    flex: result[key] as int,
                    child: ColoredBox(
                        color: color, child: const SizedBox(height: 6))),
          ]),
        ),
        const SizedBox(height: 8),
        Text("가장 많이 쓴 선봉 · $leads (${lead['runs']}/$runs판)"),
        if (strategyUse.isNotEmpty)
          Text(
              '내 전략 전개 · ${strategyUse.map((s) => "${s['label']} ${s['runs']}/$runs판").join(' · ')}'),
        Text(
            "최저 승률 · ${weakest['label']} ${_winRate(weakest)} (${weakest['runs']}판)"),
        if (result['memberStats'] != null)
          LabExpansionTile(
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            expandedAlignment: Alignment.centerLeft,
            title: const Text('상세 통계 · 포켓몬별 활약, 선봉 조합, 위협'),
            children: [SimulationInsights(result), const SizedBox(height: 10)],
          ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          expandedAlignment: Alignment.centerLeft,
          title: const Text('전략별 전적과 대응법'),
          children: [_PartyStrategyTabs(strategies)],
        ),
      ]),
    );
  }
}

class _PartyStrategyTabs extends StatefulWidget {
  final List<Json> strategies;
  const _PartyStrategyTabs(this.strategies);

  @override
  State<_PartyStrategyTabs> createState() => _PartyStrategyTabsState();
}

class _PartyStrategyTabsState extends State<_PartyStrategyTabs> {
  String? style;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rows = widget.strategies;
    final active =
        rows.where((row) => row['style'] == style).firstOrNull ?? rows.first;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 6, runSpacing: 4, children: [
        for (final row in rows)
          ChoiceChip(
            label: Text("${row['label']} ${_winRate(row)}"),
            selected: identical(active, row),
            onSelected: (_) => setState(() => style = row['style'] as String),
          ),
      ]),
      const SizedBox(height: 7),
      Text(
          "${active['label']} · ${active['win']}승 ${active['loss']}패 ${active['draw']}무",
          style: theme.textTheme.titleSmall),
      const SizedBox(height: 3),
      Text(active['counterplay'] as String, style: theme.textTheme.bodySmall),
    ]);
  }
}

String _winRate(Json row) =>
    fmtPct(100 * (row['win'] as int) / (row['runs'] as int));
