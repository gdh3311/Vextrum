import 'dart:convert';

import '../lab_icons.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../widgets.dart';
import 'battle_preview.dart';

const _key = 'personal_match_journal_v1';
const _outcomes = {'win': '승리', 'loss': '패배', 'draw': '무승부'};

String _rosterKey(List<Json> roster) =>
    (roster.map((m) => m['id'] as String).toList()..sort()).join('|');

final matchJournalProvider =
    AsyncNotifierProvider<MatchJournal, List<Json>>(MatchJournal.new);

class MatchJournal extends AsyncNotifier<List<Json>> {
  @override
  Future<List<Json>> build() async {
    final saved = (await SharedPreferences.getInstance()).getString(_key);
    return saved == null ? [] : (jsonDecode(saved) as List).cast<Json>();
  }

  Future<void> add(Json record) async {
    final old = await future;
    final next = [record, ...old];
    final prefs = await SharedPreferences.getInstance();
    if (!await prefs.setString(_key, jsonEncode(next))) {
      throw StateError('journal write failed');
    }
    state = AsyncData(next);
  }
}

class MatchJournalPanel extends ConsumerStatefulWidget {
  const MatchJournalPanel({
    super.key,
    required this.format,
    required this.teamName,
    required this.team,
    required this.enemy,
    required this.confirmed,
    required this.locked,
  });
  final String format;
  final String teamName;
  final List<Json> team;
  final List<Json> enemy;
  final List<String> confirmed;
  final List<String> locked;

  @override
  ConsumerState<MatchJournalPanel> createState() => _MatchJournalPanelState();
}

class _MatchJournalPanelState extends ConsumerState<MatchJournalPanel> {
  bool saving = false;

  Future<void> _record() async {
    final format = widget.format;
    final team = widget.team;
    final name = widget.teamName;
    final enemy = widget.enemy;
    final locked = widget.locked;
    final draft = await showDialog<Json>(
      context: context,
      builder: (_) => _RecordDialog(
          enemy: enemy, format: format, confirmed: widget.confirmed),
    );
    if (draft == null || !mounted) return;
    setState(() => saving = true);
    try {
      await ref.read(matchJournalProvider.notifier).add({
        ...draft,
        'at': DateTime.now().toIso8601String(),
        'format': format,
        'teamName': name,
        'team': team,
        'myBring': locked,
        'enemy': enemy,
      });
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('내 실전 기록에 저장했습니다.')));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('실전 기록을 저장하지 못했습니다.')));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final journal = ref.watch(matchJournalProvider);
    final records = (journal.valueOrNull ?? [])
        .where((r) => r['format'] == widget.format)
        .toList();
    final teamKey = _rosterKey(widget.team);
    final enemyKey = _rosterKey(widget.enemy);
    final sameTeam = records
        .where((r) => _rosterKey((r['team'] as List).cast<Json>()) == teamKey)
        .toList();
    final matchup = sameTeam
        .where((r) => _rosterKey((r['enemy'] as List).cast<Json>()) == enemyKey)
        .toList();
    return Section(
      '내 실전 기록',
      subtitle: '게임에서 확인한 결과를 기기에 저장합니다. 가상 배틀 결과는 별도로 보관합니다.',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (journal.hasError) const Text('저장된 실전 기록을 불러오지 못했습니다.'),
        if (sameTeam.isNotEmpty) Text('이 구성으로 ${_summary(sameTeam)}'),
        if (matchup.isNotEmpty) ...[
          Text('같은 상대 구성과 ${_summary(matchup)}'),
          ..._observedLeads(matchup),
        ],
        Wrap(spacing: 8, children: [
          FilledButton.tonalIcon(
            onPressed: widget.enemy.isEmpty ||
                    widget.team.isEmpty ||
                    saving ||
                    !journal.hasValue
                ? null
                : _record,
            icon: const LabIcon(LabGlyph.note),
            label: const Text('이번 경기 기록'),
          ),
          if (records.isNotEmpty)
            TextButton.icon(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(
                    text: const JsonEncoder.withIndent('  ').convert(records)));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('실전 기록 JSON을 복사했습니다.')));
                }
              },
              icon: const LabIcon(LabGlyph.copy, size: 17),
              label: const Text('기록 복사'),
            ),
        ]),
        if (records.isNotEmpty)
          LabExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text('최근 경기 · ${records.length}건'),
            children: [
              for (final r in records.take(10))
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                      '${_outcomes[r['outcome']]} · ${r['teamName']} · ${(r['at'] as String).split('T').first}'),
                  subtitle: Text([
                    '상대 ${(r['enemy'] as List).cast<Json>().map(monName).join(' · ')}',
                    if ((r['note'] as String).isNotEmpty) r['note'],
                  ].join('\n')),
                ),
            ],
          ),
      ]),
    );
  }

  String _summary(List<Json> rows) =>
      '${rows.where((r) => r['outcome'] == 'win').length}승 '
      '${rows.where((r) => r['outcome'] == 'loss').length}패 '
      '${rows.where((r) => r['outcome'] == 'draw').length}무';

  List<Widget> _observedLeads(List<Json> records) {
    final expected = widget.format == 'Doubles' ? 2 : 1;
    final byId = {for (final m in widget.enemy) m['id']: monName(m)};
    final seen = <String, int>{};
    for (final r in records) {
      final ids = (r['enemyLead'] as List)
          .cast<String>()
          .where(byId.containsKey)
          .toList()
        ..sort();
      if (ids.length != expected) continue;
      final label = ids.map((id) => byId[id]).join(' + ');
      seen.update(label, (value) => value + 1, ifAbsent: () => 1);
    }
    final ranked = seen.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return [
      if (ranked.isNotEmpty)
        Text(
            '내 기록에서 본 선봉 · ${ranked.take(3).map((e) => '${e.key} ${e.value}회').join(' / ')}'),
    ];
  }
}

class _RecordDialog extends StatefulWidget {
  const _RecordDialog(
      {required this.enemy, required this.format, required this.confirmed});
  final List<Json> enemy;
  final String format;
  final List<String> confirmed;

  @override
  State<_RecordDialog> createState() => _RecordDialogState();
}

class _RecordDialogState extends State<_RecordDialog> {
  final note = TextEditingController();
  late final lead = widget.confirmed.toSet();
  final back = <String>{};
  String? outcome;

  @override
  void dispose() {
    note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final leadSize = widget.format == 'Doubles' ? 2 : 1;
    Widget chips(Set<String> selection, int max,
            {Set<String> unavailable = const {}}) =>
        Wrap(spacing: 6, children: [
          for (final m in widget.enemy)
            if (!unavailable.contains(m['id']))
              FilterChip(
                label: Text(monName(m)),
                selected: selection.contains(m['id']),
                onSelected: (add) => setState(() {
                  final id = m['id'] as String;
                  if (!add) {
                    selection.remove(id);
                  } else if (selection.length < max) {
                    selection.add(id);
                    if (identical(selection, lead)) back.remove(id);
                  }
                }),
              ),
        ]);

    return AlertDialog(
      title: const Text('실전 결과 기록'),
      content: SingleChildScrollView(
        child: SizedBox(
          width: 460,
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Wrap(spacing: 8, children: [
                  for (final e in _outcomes.entries)
                    ChoiceChip(
                        label: Text(e.value),
                        selected: outcome == e.key,
                        onSelected: (_) => setState(() => outcome = e.key)),
                ]),
                const SizedBox(height: 8),
                const Text('실제로 본 상대 선봉'),
                chips(lead, leadSize),
                const SizedBox(height: 8),
                const Text('실제로 본 상대 후발'),
                chips(back, 2, unavailable: lead),
                const SizedBox(height: 8),
                TextField(
                  controller: note,
                  maxLength: 200,
                  decoration:
                      const InputDecoration(hintText: '예: 순풍을 먼저 막았어야 했음'),
                ),
              ]),
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('취소')),
        FilledButton(
          onPressed: outcome == null
              ? null
              : () => Navigator.pop(context, {
                    'outcome': outcome,
                    'enemyLead': lead.toList(),
                    'enemyBack': back.toList(),
                    'note': note.text.trim(),
                  }),
          child: const Text('저장'),
        ),
      ],
    );
  }
}
