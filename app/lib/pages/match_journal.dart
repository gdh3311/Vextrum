import 'dart:convert';

import '../lab_icons.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter/services.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../widgets.dart';
import 'battle_preview.dart';
import '../i18n.dart';

const _key = 'personal_match_journal_v1';
const _predictionKey = 'personal_match_prediction_v1';
const _outcomes = {'win': '승리', 'loss': '패배', 'draw': '무승부'};

String _rosterKey(List<Json> roster) =>
    (roster.map((m) => m['id'] as String).toList()..sort()).join('|');

final matchJournalProvider =
    AsyncNotifierProvider<MatchJournal, List<Json>>(MatchJournal.new);
final _predictionProvider = FutureProvider<Json?>((ref) async {
  final data = (await SharedPreferences.getInstance()).getString(_predictionKey);
  return data == null ? null : jsonDecode(data) as Json;
});

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
    required this.teamMembers,
    required this.team,
    required this.enemy,
    required this.confirmed,
    required this.locked,
  });
  final String format;
  final String teamName;
  final List<Json> teamMembers;
  final List<Json> team;
  final List<Json> enemy;
  final List<String> confirmed;
  final List<String> locked;

  @override
  ConsumerState<MatchJournalPanel> createState() => _MatchJournalPanelState();
}

class _MatchJournalPanelState extends ConsumerState<MatchJournalPanel> {
  bool saving = false;

  Json? _matchingPrediction(Json? draft, List<Json> records) {
    if (draft == null || draft['format'] != widget.format ||
        draft['teamName'] != widget.teamName ||
        draft['teamKey'] != jsonEncode(widget.team) ||
        draft['enemyKey'] != _rosterKey(widget.enemy)) return null;
    final prediction = draft['prediction'] as Json?;
    if (prediction == null ||
        records.any((r) => (r['prediction'] as Json?)?['at'] == prediction['at'])) return null;
    return prediction;
  }

  Future<void> _predict() async {
    final format = widget.format;
    final name = widget.teamName;
    final team = widget.team;
    final enemy = widget.enemy;
    setState(() => saving = true);
    try {
      final res = await dio.post('/api/workbench/matchup/prediction', data: {
        'format': format, 'team': team, 'enemy': [for (final mon in enemy) mon['id']],
      });
      final prefs = await SharedPreferences.getInstance();
      if (!await prefs.setString(_predictionKey, jsonEncode({
        'teamKey': jsonEncode(team), 'enemyKey': _rosterKey(enemy),
        'teamName': name, 'format': format, 'prediction': res.data,
      }))) throw StateError('prediction write failed');
      if (mounted) ref.invalidate(_predictionProvider);
    } catch (error) {
      if (mounted) {
        final body = error is DioException ? error.response?.data : null;
        final message = body is Map ? body['detail'] : null;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(message is String ? message : '경기 전 예측을 저장하지 못했습니다.')));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _record() async {
    final format = widget.format;
    final team = widget.team;
    final name = widget.teamName;
    final enemy = widget.enemy;
    final locked = widget.locked;
    final prediction = _matchingPrediction(ref.read(_predictionProvider).valueOrNull,
        ref.read(matchJournalProvider).valueOrNull ?? const []);
    final teamMembers = widget.teamMembers;
    final confirmed = widget.confirmed;
    final draft = await showDialog<Json>(
      context: context,
      builder: (_) => _RecordDialog(
          team: teamMembers, sets: team, enemy: enemy, format: format,
          confirmed: confirmed, locked: locked),
    );
    if (draft == null || !mounted) return;
    setState(() => saving = true);
    try {
      await ref.read(matchJournalProvider.notifier).add({
        ...draft,
        'at': DateTime.now().toUtc().toIso8601String(),
        'format': format,
        'teamName': name,
        'team': team,
        'enemy': enemy,
        if (prediction != null) 'prediction': prediction,
        if (prediction != null) 'season': prediction['season'],
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
    final pending = ref.watch(_predictionProvider);
    final prediction = _matchingPrediction(pending.valueOrNull, journal.valueOrNull ?? const []);
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
        if (prediction != null) ...[
          const Text('경기 전 예측을 저장했습니다. 이번 경기 결과에 연결됩니다.'),
          Text('저장한 선봉 ${_names(prediction['lead'])} · 후발 ${_names(prediction['back'])}'),
        ],
        if (prediction?['simulation'] case final Json sim)
          Text('저장한 선출의 모의전 승점률 ${((sim['rate'] as num) * 100).round()}% · ${sim['games']}판'),
        if (prediction?['simulationUnavailable'] case final String message) Text(message),
        Wrap(spacing: 8, children: [
          OutlinedButton(
            onPressed: widget.enemy.length == 6 && widget.team.length == 6 &&
                    widget.confirmed.isEmpty && !saving && pending.hasValue && journal.hasValue
                ? _predict : null,
            child: Text(prediction == null ? '경기 전 예측 저장' : '예측 다시 저장'),
          ),
          FilledButton.tonalIcon(
            onPressed: widget.enemy.isEmpty ||
                    widget.team.isEmpty ||
                    saving ||
                    pending.isLoading ||
                    !journal.hasValue
                ? null
                : _record,
            icon: const LabIcon(LabGlyph.note),
            label: const Text('이번 경기 기록'),
          ),
          if (records.isNotEmpty)
            TextButton(onPressed: () => context.go('/workspace?tab=feedback'), child: const Text('워크스페이스에서 기록 분석')),
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
                      '${_outcomes[r['outcome']]} · ${r['teamName']} · ${DateTime.parse(r['at'] as String).toLocal().toIso8601String().split('T').first}'),
                  subtitle: Text([
                    '상대 ${(r['enemy'] as List).cast<Json>().map(monName).join(' · ')}',
                    if ((r['note'] as String? ?? '').isNotEmpty) r['note'],
                  ].join('\n')),
                ),
            ],
          ),
      ]),
    );
  }

  String _names(Object? ids) {
    final names = {for (final m in widget.teamMembers) m['id']: monName(m)};
    return (ids as List? ?? const []).map((id) => names[id] ?? id).join(' + ');
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
      final ids = (r['enemyLead'] as List? ?? const [])
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
  const _RecordDialog({required this.enemy, required this.team, required this.sets, required this.format,
      required this.confirmed, required this.locked});
  final List<Json> enemy;
  final List<Json> team;
  final List<Json> sets;
  final String format;
  final List<String> confirmed;
  final List<String> locked;

  @override
  State<_RecordDialog> createState() => _RecordDialogState();
}

class _RecordDialogState extends State<_RecordDialog> {
  final note = TextEditingController();
  final turnNote = TextEditingController();
  final keyTurn = TextEditingController();
  late final lead = widget.confirmed.toSet();
  final back = <String>{};
  int get leadSize => widget.format == 'Doubles' ? 2 : 1;
  final myLead = <String>{};
  final myBack = <String>{};
  final opening = <String, String>{};
  String? outcome;
  String? lossReason;

  @override
  void dispose() {
    note.dispose();
    turnNote.dispose();
    keyTurn.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget chips(Set<String> selection, int max,
            {List<Json>? members, Set<String> unavailable = const {}, Set<String>? removeFrom}) =>
        Wrap(spacing: 6, children: [
          for (final m in members ?? widget.enemy)
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
                    removeFrom?.remove(id);
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
                if (widget.locked.length == leadSize + 2)
                  TextButton(
                    onPressed: () => setState(() {
                      myLead..clear()..addAll(widget.locked.take(leadSize));
                      myBack..clear()..addAll(widget.locked.skip(leadSize));
                    }),
                    child: const Text('화면에서 고른 선출을 실제 선출로 입력'),
                  ),
                const Text('내 실제 선봉'),
                chips(myLead, leadSize, members: widget.team, removeFrom: myBack),
                const Text('내 실제 후발'),
                chips(myBack, 2, members: widget.team, unavailable: myLead),
                if (myLead.isNotEmpty)
                  LabExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: const Text('첫 턴에 선택한 기술·교체 (선택)'),
                    children: [
                      for (final mon in widget.team.where((m) => myLead.contains(m['id'])))
                        _openingAction(mon),
                    ],
                  ),
                const SizedBox(height: 8),
                const Text('실제로 본 상대 선봉'),
                chips(lead, leadSize, removeFrom: back),
                const SizedBox(height: 8),
                const Text('실제로 본 상대 후발'),
                chips(back, 2, unavailable: lead),
                const SizedBox(height: 8),
                if (outcome == 'loss') ...[
                  const Text('직접 돌아본 패배 요인'),
                  Wrap(spacing: 6, children: [
                    for (final label in ['선출', '교체', '기술 선택', '팀 구성', '모르겠음'])
                      ChoiceChip(label: Text(label), selected: lossReason == label,
                          onSelected: (selected) => setState(() => lossReason = selected ? label : null)),
                  ]),
                ],
                TextField(controller: keyTurn, keyboardType: TextInputType.number,
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(2)],
                    decoration: const InputDecoration(labelText: '기억할 턴 번호 (선택)')),
                TextField(controller: turnNote, maxLength: 160,
                    decoration: const InputDecoration(labelText: '실제 행동',
                        hintText: '예 · 내 고릴타 교체, 상대 카디나르마 아머캐논')),
                TextField(
                  controller: note,
                  maxLength: 200,
                  decoration:
                      InputDecoration(hintText: tr('예: 순풍을 먼저 막았어야 했음')),
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
                    'myLead': myLead.toList(), 'myBack': myBack.toList(),
                    'opening': {for (final id in myLead) if (opening[id] != null) id: opening[id]},
                    if (outcome == 'loss' && lossReason != null) 'lossReason': lossReason,
                    if (int.tryParse(keyTurn.text) case final turn?) if (turn > 0) 'keyTurn': turn,
                    if (turnNote.text.trim().isNotEmpty) 'turnNote': turnNote.text.trim(),
                    'note': note.text.trim(),
                  }),
          child: const Text('저장'),
        ),
      ],
    );
  }

  Widget _openingAction(Json mon) {
    final id = mon['id'] as String;
    final set = widget.sets.firstWhere((s) => s['id'] == id);
    final moveList = (set['moves'] as List? ?? const []).cast<String>().toSet();
    final details = (mon['learnset'] as List? ?? const []).whereType<Json>();
    final names = {for (final m in details) m['name']: m['ko']};
    return DropdownButtonFormField<String>(
      key: ValueKey(id),
      value: opening[id],
      isExpanded: true,
      decoration: InputDecoration(labelText: monName(mon)),
      items: [
        const DropdownMenuItem(value: '', child: Text('기억나지 않음')),
        const DropdownMenuItem(value: 'switch', child: Text('교체')),
        for (final move in moveList)
          DropdownMenuItem(value: move, child: Text('${names[move] ?? move}')),
      ],
      onChanged: (value) => setState(() {
        if (value == null || value.isEmpty) {
          opening.remove(id);
        } else {
          opening[id] = value;
        }
      }),
    );
  }
}
