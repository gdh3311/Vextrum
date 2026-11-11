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
    return Section(
      stable ? '전략별 안정성 순위' : '시뮬레이션 승률 순위',
      subtitle:
          "${evaluation['screened']}팀을 각각 ${evaluation['screenRuns']}판씩 평가하고, "
          "${evaluation['finalists']}팀을 새 상대군에서 ${evaluation['finalRuns']}판씩 다시 검증했습니다.",
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          stable
              ? tr('팀마다 같은 상대 로스터를 만납니다. {} CPU 기준으로 가장 어려웠던 전략의 승률이 높은 팀을 먼저 표시합니다.')
                  .replaceFirst('{}', tr(cpuLabels[evaluation['cpu']] ?? '하이퍼볼'))
              : tr('팀마다 같은 상대 로스터를 만납니다. {} CPU 기준 최종 검증 승률이 높은 팀을 먼저 표시합니다.')
                  .replaceFirst('{}', tr(cpuLabels[evaluation['cpu']] ?? '하이퍼볼')),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 12),
        CandidateComparison(candidates),
        const SizedBox(height: 6),
        for (final (i, team) in candidates.indexed)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Text("${i + 1}위 · ${team['name']} · ${_comparison(team['simulation'] as Json)}",
                style: Theme.of(context).textTheme.bodySmall),
          ),
      ]),
    );
  }

  static String _comparison(Json result) {
    final worst = (result['strategies'] as List).first as Json;
    return "전체 ${_winRate(result)} · 최저 ${_winRate(worst)} (${worst['label']})";
  }
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
