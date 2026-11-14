import 'package:flutter/material.dart' hide Text, Tooltip;

import '../api.dart';
import '../lab_icons.dart';
import '../widgets.dart';
import '../i18n.dart';

String battleRecord(Json row) {
  final rate = fmtPct(100 * (row['win'] as int) / (row['runs'] as int));
  return "${row['win']}승 ${row['loss']}패 ${row['draw']}무 · 승률 $rate";
}

class BattleReport extends StatefulWidget {
  final Json result;
  final ValueChanged<int>? onPractice;

  const BattleReport({super.key, required this.result, this.onPractice});

  @override
  State<BattleReport> createState() => _BattleReportState();
}

class _BattleReportState extends State<BattleReport> {
  String? style;

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    final strategies = (result['strategies'] as List).cast<Json>();
    final measured = strategies.where((s) => (s['runs'] as int) >= 5).toList();
    final selected = strategies.where((s) => s['style'] == style).firstOrNull ??
        measured.firstOrNull ??
        strategies.first;
    final overall = (result['members'] as List).cast<Json>();
    final names = {
      for (final mon in overall)
        mon['id'] as String: (mon['ko'] ?? mon['name']) as String,
    };
    final runs = result['runs'] as int;
    final weakest = measured.firstOrNull;
    final strongest = measured.lastOrNull;
    final showExtremes = weakest != null &&
        strongest != null &&
        _rate(weakest) < _rate(strongest);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('$runs판 · ${battleRecord(result)} · 평균 ${result['avgTurns']}턴',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      _ResultBar(result),
      const SizedBox(height: 12),
      Text([
        if ((result['dataset'] as Json?)?['season'] case final season?)
          '$season 메타',
        '전략별 균등 표본',
        '양쪽 CPU 자동 선출·행동',
      ].join(' · ')),
      if (showExtremes)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Wrap(spacing: 8, runSpacing: 6, children: [
            _Highlight(
                LabGlyph.shield, '최저 승률 · ${_extremeLabel(measured, weakest)}'),
            _Highlight(
                LabGlyph.meta, '최고 승률 · ${_extremeLabel(measured, strongest)}'),
          ]),
        ),
      LabExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('전체 선출 분포'),
        subtitle: const Text('내 팀의 포켓몬별 선출·선봉 횟수'),
        children: [_Selection(rows: overall, runs: runs)],
      ),
      const SizedBox(height: 14),
      Text('전략별 상세', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 6),
      Wrap(spacing: 6, runSpacing: 6, children: [
        for (final row in strategies)
          ChoiceChip(
            selected: identical(selected, row),
            label: Text(
                "${row['label']} · ${fmtPct(_rate(row))} (${row['runs']}판)"),
            onSelected: (_) => setState(() => style = row['style'] as String),
          ),
      ]),
      const SizedBox(height: 12),
      _StrategyDetail(
        key: ValueKey(selected['style']),
        data: selected,
        names: names,
        onPractice: widget.onPractice,
      ),
    ]);
  }
}

double _rate(Json row) => 100 * (row['win'] as int) / (row['runs'] as int);

String _extremeLabel(List<Json> rows, Json sample) {
  final tied = rows
          .where((row) =>
              (row['win'] as int) * (sample['runs'] as int) ==
              (sample['win'] as int) * (row['runs'] as int))
          .length -
      1;
  return "${sample['label']}${tied > 0 ? ' 외 $tied개' : ''} ${fmtPct(_rate(sample))} (${sample['runs']}판)";
}

class _Highlight extends StatelessWidget {
  final LabGlyph icon;
  final String text;
  const _Highlight(this.icon, this.text);

  @override
  Widget build(BuildContext context) => Chip(
        avatar: LabIcon(icon, size: 16),
        label: Text(text),
      );
}

class _ResultBar extends StatelessWidget {
  final Json row;
  const _ResultBar(this.row);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ExcludeSemantics(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: Row(children: [
          for (final (key, color) in [
            ('win', cs.primary),
            ('draw', cs.outlineVariant),
            ('loss', cs.error),
          ])
            if ((row[key] as int) > 0)
              Expanded(
                  flex: row[key] as int,
                  child: ColoredBox(
                      color: color, child: const SizedBox(height: 8))),
        ]),
      ),
    );
  }
}

class _StrategyDetail extends StatelessWidget {
  final Json data;
  final Map<String, String> names;
  final ValueChanged<int>? onPractice;

  const _StrategyDetail(
      {super.key, required this.data, required this.names, this.onPractice});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final runs = data['runs'] as int;
    final foes = (data['foes'] as List).cast<Json>();
    final fought = foes.where((f) => (f['picked'] as int) > 0).toList();
    final lineups = (data['lineups'] as List).cast<Json>();
    final example = data['example'] as Json;
    final lost = example['result'] == 'loss';
    final leadSize = example['leadSize'] as int;
    final theirPicks = (example['foe'] as List).cast<String>();
    final ourPicks = (example['mine'] as List).cast<String>();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text("${data['label']} 상대 · ${battleRecord(data)}",
            style: theme.textTheme.titleMedium),
        Wrap(spacing: 6, runSpacing: 4, children: [
          if (data['activated'] case final int activated)
            Chip(
                label: Text('핵심 전략 발동 $activated/$runs판'),
                visualDensity: VisualDensity.compact),
          if (runs < 5)
            const Chip(
                label: Text('소표본 · 5판 미만'),
                visualDensity: VisualDensity.compact),
        ]),
        const SizedBox(height: 10),
        _ResultBar(data),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          expandedAlignment: Alignment.centerLeft,
          title: const Text('상대 운영과 대응법'),
          children: [
            Text('상대가 노리는 것', style: theme.textTheme.titleSmall),
            Text(data['plan'] as String),
            if (data['counterplay'] case final String counterplay) ...[
              const SizedBox(height: 8),
              Text('상대 전략의 일반적인 대응', style: theme.textTheme.titleSmall),
              Text(counterplay),
            ],
            const SizedBox(height: 8),
          ],
        ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          expandedAlignment: Alignment.centerLeft,
          title: const Text('내 선출 조합'),
          subtitle: Text("최다 선봉 · ${_names(lineups.first['lead'] as List)}"),
          children: [
            for (final row in lineups)
              Padding(
                padding: const EdgeInsets.only(bottom: 9),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text("선봉 ${_names(row['lead'] as List)}",
                          style: theme.textTheme.titleSmall),
                      if ((row['back'] as List).isNotEmpty)
                        Text("후발 ${_names(row['back'] as List)}"),
                      Text(
                          "${row['runs']}판 · ${row['win']}승 ${row['loss']}패 ${row['draw']}무",
                          style: theme.textTheme.bodySmall),
                    ]),
              ),
          ],
        ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('내 포켓몬별 선출·기여'),
          children: [
            _Selection(rows: (data['members'] as List).cast<Json>(), runs: runs)
          ],
        ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          expandedAlignment: Alignment.centerLeft,
          title: const Text('실제로 상대했던 포켓몬'),
          subtitle: Text('${fought.length}마리 · 패배한 판에 상대가 선출한 횟수순'),
          children: [
            for (final row in fought.take(5)) _FoeRow(row, names: names),
            if (fought.length > 5 || foes.length > fought.length)
              LabExpansionTile(
                tilePadding: EdgeInsets.zero,
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                expandedAlignment: Alignment.centerLeft,
                title:
                    Text('나머지 상대 포켓몬 ${foes.length - fought.take(5).length}마리'),
                children: [
                  for (final row in [
                    ...fought.skip(5),
                    ...foes.where((f) => f['picked'] == 0)
                  ])
                    _FoeRow(row, names: names),
                ],
              ),
          ],
        ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          expandedAlignment: Alignment.centerLeft,
          title: Text(lost ? '패배 사례' : '표본 경기'),
          subtitle: Text(
              "${example['turns']}턴 · 내 선봉 ${_names(ourPicks.take(leadSize))}"),
          children: [
            if (ourPicks.length > leadSize)
              Text('내 후발 ${_names(ourPicks.skip(leadSize))}'),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final mon in (example['opponent'] as List).cast<Json>())
                MonPill(mon,
                    caption: _position(
                        theirPicks.indexOf(mon['id'] as String), leadSize)),
            ]),
          ],
        ),
        if (onPractice != null)
          TextButton.icon(
            icon: const LabIcon(LabGlyph.repeat),
            label: const Text('이 매치업으로 연습'),
            onPressed: () => onPractice!(example['seed'] as int),
          ),
      ]),
    );
  }

  String _names(Iterable<dynamic> ids) =>
      ids.map((id) => names[id] ?? id).join(' · ');

  static String _position(int index, int leadSize) => index < 0
      ? '미선출'
      : index < leadSize
          ? '선봉'
          : '후발';
}

class _Selection extends StatelessWidget {
  final List<Json> rows;
  final int runs;
  const _Selection({required this.rows, required this.runs});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(children: [
      for (final row in rows)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(
                spacing: 8,
                runSpacing: 4,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  MonPill(row,
                      caption:
                          "선출 ${row['picked']}/$runs · 선봉 ${row['leads']}/$runs"),
                  if ((row['picked'] as int) > 0)
                    Text(
                        "총 준 피해 ${row['dealt']} · 받은 피해 ${row['taken']} · KO ${row['kos']}"),
                ]),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: (row['picked'] as int) / runs,
                backgroundColor: cs.surfaceContainerHighest,
                minHeight: 4,
              ),
            ),
          ]),
        ),
    ]);
  }
}

class _FoeRow extends StatelessWidget {
  final Json row;
  final Map<String, String> names;
  const _FoeRow(this.row, {required this.names});

  @override
  Widget build(BuildContext context) {
    final picked = row['picked'] as int;
    final victims = (row['victims'] as Json).entries.toList()
      ..sort((a, b) => (b.value as int).compareTo(a.value as int));
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Sprite(row['sprite'] as String, size: 36),
        const SizedBox(width: 8),
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text("${row['ko'] ?? row['name']}",
              style: Theme.of(context).textTheme.titleSmall),
          Text("등장 ${row['rostered']} · 선출 $picked · 선봉 ${row['leads']}"),
          if (picked > 0)
            Text(
                "내 전적 ${row['win']}승 ${row['loss']}패 ${row['draw']}무 · ${fmtPct(100 * (row['win'] as int) / picked)} · 상대 KO ${row['kos']}${picked < 5 ? ' · 소표본' : ''}",
                style: Theme.of(context).textTheme.bodySmall),
          if (victims.isNotEmpty)
            Text(
                "KO 대상 · ${victims.take(3).map((v) => "${names[v.key] ?? v.key} ${v.value}회").join(' · ')}",
                style: Theme.of(context).textTheme.bodySmall),
        ])),
      ]),
    );
  }
}
