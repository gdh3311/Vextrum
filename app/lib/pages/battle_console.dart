import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api.dart';
import '../lab_icons.dart';
import '../widgets.dart';

class BattleReveal extends StatelessWidget {
  final Widget child;
  const BattleReveal({super.key, required this.child});

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: MediaQuery.disableAnimationsOf(context)
            ? Duration.zero
            : const Duration(milliseconds: 310),
        curve: Curves.easeOutCubic,
        child: child,
        builder: (context, value, content) => Opacity(
          opacity: value,
          child: Transform.translate(
              offset: Offset(0, (1 - value) * 10), child: content),
        ),
      );
}

typedef _Message = ({Json event, List<Json> effects});

List<_Message> _messages(List<Json> events) {
  final rows = <_Message>[];
  for (final event in events) {
    if ((event['kind'] == 'damage' || event['kind'] == 'detail') &&
        rows.isNotEmpty &&
        rows.last.event['kind'] == 'move') {
      rows.last.effects.add(event);
    } else {
      rows.add((event: event, effects: []));
    }
  }
  return rows;
}

class BattleMessages extends StatefulWidget {
  final List<Json> events;
  const BattleMessages(this.events, {super.key});

  @override
  State<BattleMessages> createState() => _BattleMessagesState();
}

class _BattleMessagesState extends State<BattleMessages> {
  bool expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final all = _messages(widget.events);
    final attacks = all.where((r) => r.event['kind'] == 'move').toList();
    final highlight =
        (attacks.isEmpty ? all : attacks).reversed.take(2).toList().reversed;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.outlineVariant),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${widget.events.first['turn']}턴 메시지',
            style: theme.textTheme.titleSmall),
        const SizedBox(height: 5),
        Semantics(
            liveRegion: true, child: _MessageRows(expanded ? all : highlight)),
        if (all.length > highlight.length)
          TextButton.icon(
            icon: LabIcon(expanded ? LabGlyph.up : LabGlyph.down, size: 14),
            onPressed: () => setState(() => expanded = !expanded),
            label: Text(expanded ? '요약만 보기' : '이 턴 전체 보기'),
          ),
      ]),
    );
  }
}

class BattleMessageHistory extends StatelessWidget {
  final List<Json> logs;
  const BattleMessageHistory(this.logs, {super.key});

  @override
  Widget build(BuildContext context) {
    final turns = <int, List<Json>>{};
    for (final event in logs) {
      turns.putIfAbsent(event['turn'] as int, () => []).add(event);
    }
    return LabExpansionTile(
      title: const Text('전체 턴 기록'),
      tilePadding: EdgeInsets.zero,
      expandedCrossAxisAlignment: CrossAxisAlignment.start,
      expandedAlignment: Alignment.centerLeft,
      children: [
        for (final entry in turns.entries.toList().reversed)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${entry.key}턴',
                  style: Theme.of(context).textTheme.titleSmall),
              _MessageRows(_messages(entry.value)),
            ]),
          ),
      ],
    );
  }
}

class _MessageRows extends StatelessWidget {
  final Iterable<_Message> rows;
  const _MessageRows(this.rows);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final row in rows)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Padding(
              padding: const EdgeInsets.only(top: 2, right: 7),
              child: LabIcon(
                  switch (row.event['kind']) {
                    'move' => LabGlyph.bolt,
                    'entry' => LabGlyph.ball,
                    'field' => LabGlyph.cloud,
                    _ => LabGlyph.note,
                  },
                  size: 14,
                  color: row.event['side'] == 1 ? cs.error : cs.primary),
            ),
            Expanded(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(row.event['text'] as String,
                      style: theme.textTheme.bodyMedium),
                  if (row.effects.isNotEmpty)
                    Wrap(spacing: 5, runSpacing: 4, children: [
                      for (final event in row.effects)
                        if (event['kind'] == 'damage')
                          DecoratedBox(
                            decoration: BoxDecoration(
                              color: event['fainted'] == true
                                  ? cs.error.withOpacity(.13)
                                  : cs.surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 5, vertical: 2),
                              child: Text(
                                  "${event['target']} −${event['amount']} HP${event['fainted'] == true ? ' · 기절' : ''}",
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: event['fainted'] == true
                                        ? cs.error
                                        : cs.onSurface,
                                  )),
                            ),
                          )
                        else
                          Text(event['text'] as String,
                              style: theme.textTheme.bodySmall),
                    ]),
                ])),
          ]),
        ),
    ]);
  }
}

class BattleLoading extends StatefulWidget {
  final String label;
  const BattleLoading(this.label, {super.key});

  @override
  State<BattleLoading> createState() => _BattleLoadingState();
}

class _BattleLoadingState extends State<BattleLoading>
    with SingleTickerProviderStateMixin {
  late final _orbit = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 950));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _orbit
        ..stop()
        ..value = 0;
    } else if (!_orbit.isAnimating) {
      _orbit.repeat();
    }
  }

  @override
  void dispose() {
    _orbit.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Semantics(
      liveRegion: true,
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        AnimatedBuilder(
          animation: _orbit,
          builder: (context, child) {
            final angle = 2 * math.pi * _orbit.value;
            return SizedBox.square(
              dimension: 38,
              child: Stack(alignment: Alignment.center, children: [
                Container(
                  width: 31,
                  height: 31,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: color.withOpacity(.24)),
                  ),
                ),
                Transform.rotate(
                  angle: math.sin(angle) * .38,
                  child: LabIcon(LabGlyph.ball, size: 25, color: color),
                ),
                Transform.translate(
                  offset: Offset(15 * math.cos(angle), 15 * math.sin(angle)),
                  child: LabIcon(LabGlyph.spark, size: 12, color: color),
                ),
              ]),
            );
          },
        ),
        const SizedBox(width: 6),
        Flexible(child: Text(widget.label)),
      ]),
    );
  }
}

class BattleCommandMenu extends StatefulWidget {
  final String name;
  final List<Json> options;
  final Json? selected;
  final Map<int, String> targets;
  final Set<int> reserved;
  final ValueChanged<Json?>? onSelected;

  const BattleCommandMenu({
    super.key,
    required this.name,
    required this.options,
    required this.selected,
    required this.targets,
    required this.reserved,
    required this.onSelected,
  });

  @override
  State<BattleCommandMenu> createState() => _BattleCommandMenuState();
}

class _BattleCommandMenuState extends State<BattleCommandMenu> {
  String? move;
  bool switching = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final moves = <String, List<Json>>{};
    final swaps = <Json>[];
    for (final option in widget.options) {
      if (option['kind'] == 'switch') {
        swaps.add(option);
      } else {
        moves
            .putIfAbsent((option['move'] ?? 'wait') as String, () => [])
            .add(option);
      }
    }
    final candidates = moves[move] ?? const <Json>[];
    final selected = widget.selected;
    final enabled = widget.onSelected != null;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(widget.name, style: theme.textTheme.titleSmall),
        if (selected != null)
          Text('선택 · ${_label(selected)}',
              style: TextStyle(color: theme.colorScheme.primary)),
        const SizedBox(height: 7),
        Wrap(spacing: 6, runSpacing: 5, children: [
          for (final entry in moves.entries)
            ChoiceChip(
              avatar: LabIcon(LabGlyph.bolt,
                  size: 15, color: typeColor[entry.value.first['type']]),
              label: Text(_label(entry.value.first, withTarget: false)),
              selected: !switching && move == entry.key,
              onSelected: !enabled
                  ? null
                  : (_) {
                      setState(() {
                        move = entry.key;
                        switching = false;
                      });
                      if (entry.value.length == 1) {
                        widget.onSelected!(entry.value.single);
                      } else if (selected?['move'] != entry.key) {
                        widget.onSelected!(null);
                      }
                    },
            ),
          if (swaps.isNotEmpty)
            ChoiceChip(
              avatar: const LabIcon(LabGlyph.swap, size: 15),
              label: const Text('포켓몬 교체'),
              selected: switching,
              onSelected: !enabled
                  ? null
                  : (active) {
                      setState(() => switching = active);
                      if (active && selected?['kind'] != 'switch') {
                        widget.onSelected!(null);
                      }
                    },
            ),
        ]),
        if (switching || candidates.length > 1) ...[
          const SizedBox(height: 7),
          Text(switching ? '교체할 포켓몬' : '기술을 사용할 대상'),
          Wrap(spacing: 6, runSpacing: 5, children: [
            for (final option in switching ? swaps : candidates)
              ChoiceChip(
                label: Text(switching
                    ? option['label'] as String
                    : widget.targets[option['target']] ?? '상대 필드'),
                selected: identical(selected, option),
                onSelected: !enabled ||
                        (switching &&
                            widget.reserved.contains(option['target']))
                    ? null
                    : (_) => widget.onSelected!(option),
              ),
          ]),
        ],
      ]),
    );
  }

  String _label(Json option, {bool withTarget = true}) => [
        option['label'],
        if (option['scope'] == 'all') '· 아군 포함',
        if (option['scope'] == 'foes') '· 상대 전체',
        if (withTarget &&
            option['kind'] == 'move' &&
            widget.targets.containsKey(option['target']))
          "→ ${widget.targets[option['target']]}",
      ].join(' ');
}
