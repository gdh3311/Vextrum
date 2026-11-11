import 'dart:convert';

import '../lab_icons.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'battle_console.dart';
import 'battle_report.dart';
import 'battle_stage.dart';
import 'parties_page.dart';
import 'team_switcher.dart';

const _historyKey = 'battle_history_v1';
const _results = {'win': '승리', 'loss': '패배', 'draw': '무승부'};

typedef _Roster = ({String id, String name, List<Json> sets});

enum _BattleMode { manual, simulation, history }

enum _Rank {
  poke('몬스터볼', '기본 공격 위주로 행동합니다.'),
  great('슈퍼볼', '유리한 기술을 고르고 기회가 나면 전개합니다.'),
  ultra('하이퍼볼', '전략의 핵심 기술과 KO 기회를 노립니다.'),
  master('마스터볼', '두 포켓몬의 공격을 조율하고 유리한 교체를 찾습니다.'),
  champion('챔피언', '공격 조율과 교체에 더해 위험한 턴에는 방어를 노립니다.');

  const _Rank(this.label, this.description);
  final String label;
  final String description;

  static _Rank? fromKey(Object? key) =>
      values.where((rank) => rank.name == key).firstOrNull;
}

class BattlePage extends ConsumerWidget {
  const BattlePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final format = ref.watch(formatProvider);
    final data = ref.watch(partiesProvider);
    ref.watch(teamProvider);
    final teams = ref.watch(teamListProvider);
    final active = ref.watch(activeTeamIndexProvider);
    final pokemon =
        ref.watch(pokemonListProvider).valueOrNull ?? const <Json>[];
    return AsyncView<Json>(data, (d) {
      _Roster party(Json p) => (
            id: 'party:${p['id']}',
            name: '예시 팀 · ${p['name']}',
            sets: partySets(p)
          );
      final recommended =
          (d['recommended'] as List).cast<Json>().map(party).toList();
      final roster = [
        for (final (i, t) in teams.indexed)
          if (t.sets.isNotEmpty)
            (id: 'saved:$i', name: '저장 팀 · ${t.name}', sets: t.sets),
        ...recommended,
      ];
      return _BattlePractice(
        key: ValueKey(format),
        format: format,
        roster: roster,
        initialTeam: 'saved:$active',
        names: {
          for (final p in pokemon)
            p['id'] as String: (p['ko'] ?? p['name']) as String
        },
      );
    }, onRetry: () => ref.invalidate(partiesProvider));
  }
}

class _BattlePractice extends StatefulWidget {
  final String format;
  final List<_Roster> roster;
  final String initialTeam;
  final Map<String, String> names;
  const _BattlePractice({
    super.key,
    required this.format,
    required this.roster,
    required this.initialTeam,
    required this.names,
  });

  @override
  State<_BattlePractice> createState() => _BattlePracticeState();
}

class _BattlePracticeState extends State<_BattlePractice> {
  String? teamId;
  List<String> order = [];
  Json? scouting;
  Json? battle;
  Json? report;
  List<Json> history = [];
  final choices = <int, Json>{};
  final replacements = <int, int>{};
  String? activity;
  bool get busy => activity != null;
  _BattleMode mode = _BattleMode.manual;
  _Rank rank = _Rank.ultra;
  String? error;
  int runs = 50;
  String teamName = '';
  String foeName = '';
  Json setup = {};
  final scoutKey = GlobalKey();

  int get limit => widget.format == 'Doubles' ? 4 : 3;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final list = (jsonDecode(prefs.getString(_historyKey) ?? '[]') as List)
          .cast<Json>();
      if (mounted) setState(() => history = list);
    } catch (_) {
      // A missing or unreadable history does not stop practice.
    }
  }

  Future<void> _record(Json result, String mode) async {
    final entry = <String, dynamic>{
      'date': DateTime.now().toIso8601String(),
      'mode': mode,
      'format': widget.format,
      'team': teamName,
      'foe': foeName,
      'setup': setup,
      'result': result,
    };
    setState(() => history = [entry, ...history.take(19)]);
    try {
      final prefs = await SharedPreferences.getInstance();
      if (!await prefs.setString(_historyKey, jsonEncode(history))) {
        throw StateError('history write failed');
      }
    } catch (_) {
      if (mounted) setState(() => error = '배틀 결과를 기기에 저장하지 못했습니다.');
    }
  }

  Future<void> _request(
      String path, Json body, Future<void> Function(Json) onResult,
      {required String loading}) async {
    setState(() {
      activity = loading;
      error = null;
    });
    try {
      final res = await dio.post(path, data: body);
      if (mounted) await onResult(res.data as Json);
    } catch (e) {
      if (mounted) {
        setState(() {
          final status = e is DioException ? e.response?.statusCode : null;
          error = switch (status) {
            404 => '배틀 세션이 만료되었습니다. 새 배틀을 시작해 주세요.',
            422 => _validationMessage(e as DioException),
            _ => '배틀 요청에 실패했습니다. 연결을 확인하고 다시 시도해 주세요.',
          };
        });
      }
    } finally {
      if (mounted) setState(() => activity = null);
    }
  }

  String _validationMessage(DioException e) {
    final data = e.response?.data;
    final detail = data is Json ? data['detail'] : null;
    return detail is String && RegExp('[가-힣]').hasMatch(detail)
        ? detail
        : '선출이나 행동을 다시 확인해 주세요. 같은 대기 포켓몬을 동시에 교체할 수 없습니다.';
  }

  Json _body(_Roster team) => {
        'format': widget.format,
        'team': team.sets,
      };

  Future<void> _scout(_Roster team, {int? seed, _Rank? replayRank}) => _request(
          '/api/battle/scout', {..._body(team), if (seed != null) 'seed': seed},
          (result) async {
        setState(() {
          scouting = result;
          mode = _BattleMode.manual;
          rank = replayRank ?? rank;
          order = (result['selection'] as List).cast<String>().toList();
          battle = null;
          choices.clear();
          replacements.clear();
        });
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (scoutKey.currentContext case final context?) {
            Scrollable.ensureVisible(context);
          }
        });
      }, loading: '상대 트레이너를 찾는 중…');

  Future<void> _start(_Roster team, {required bool batch}) async {
    final body = {
      ..._body(team),
      'difficulty': rank.name,
      if (batch) 'runs': runs,
      if (!batch) 'manual': true,
      if (!batch) 'seed': scouting!['seed'],
      if (!batch) 'selection': order,
    };
    await _request(batch ? '/api/battle/batch' : '/api/battle/start', body,
        (result) async {
      setState(() {
        teamName = team.name;
        foeName = batch
            ? '무작위 전략 파티'
            : (result['opponent'] as Json)['label'] as String;
        choices.clear();
        replacements.clear();
        battle = batch ? null : result;
        if (batch) report = result;
        if (batch) scouting = null;
        setup = {...body, 'seed': result['seed']};
      });
      if (batch) await _record(result, 'batch');
    }, loading: batch ? '$runs판의 전략별 배틀을 진행 중…' : '포켓몬을 내보내는 중…');
  }

  Future<void> _turn({required bool replace}) async {
    final current = battle!;
    final endpoint = replace ? 'replace' : 'turn';
    await _request('/api/battle/${current['id']}/$endpoint', {
      'turn': current['turn'],
      if (replace)
        'choices': {
          for (final entry in replacements.entries) '${entry.key}': entry.value
        }
      else
        'actions': choices.values.toList(),
    }, (result) async {
      setState(() {
        battle = result;
        choices.clear();
        replacements.clear();
      });
      if (result['winner'] != null) await _record(result, 'manual');
    }, loading: replace ? '교체 포켓몬이 등장하는 중…' : '양쪽의 명령을 처리하는 중…');
  }

  _Roster? _roster(String? id) =>
      widget.roster.where((r) => r.id == id).firstOrNull;

  @override
  Widget build(BuildContext context) {
    final team =
        _roster(teamId ?? widget.initialTeam) ?? widget.roster.firstOrNull;
    final sets = team?.sets ?? const <Json>[];
    final ongoing = battle != null && battle!['winner'] == null;
    final manual = mode == _BattleMode.manual;
    final canStart = !busy && !ongoing && team != null;
    final visibleHistory = history.where((h) => h['format'] == widget.format);
    final theme = Theme.of(context);
    final compact = MediaQuery.sizeOf(context).width < 480;
    return PageBody(children: [
      PageHeader('가상 배틀',
          glyph: LabGlyph.controller,
          subtitle:
              '${widget.format == 'Doubles' ? '더블배틀 4마리 선출' : '싱글배틀 3마리 선출'} · 매판 새 상대를 만나 내 팀의 선출과 전략별 전적을 확인합니다.'),
      Align(
        alignment: Alignment.centerLeft,
        child: SegmentedButton<_BattleMode>(
          selectedIcon: const LabIcon(LabGlyph.check, size: 16),
          showSelectedIcon: !compact,
          style: const ButtonStyle(visualDensity: VisualDensity.compact),
          segments: [
            const ButtonSegment(
                value: _BattleMode.manual, label: Text('직접 플레이')),
            ButtonSegment(
                value: _BattleMode.simulation,
                label: Text(compact ? '시뮬레이션' : '자동 시뮬레이션'),
                enabled: !ongoing && !busy),
            const ButtonSegment(value: _BattleMode.history, label: Text('기록')),
          ],
          selected: {mode},
          onSelectionChanged:
              busy ? null : (value) => setState(() => mode = value.first),
        ),
      ),
      const SizedBox(height: 14),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(error!, style: TextStyle(color: theme.colorScheme.error)),
        ),
      if (mode == _BattleMode.history) ...[
        if (visibleHistory.isEmpty)
          const Section('기록이 없습니다', child: Text('배틀을 완료하면 이 기기에 기록이 저장됩니다.')),
        for (final entry in visibleHistory)
          Section(
            '${entry['team']} vs ${entry['foe']}',
            subtitle: [
              (entry['date'] as String).split('T').first,
              entry['mode'] == 'batch' ? '자동 시뮬레이션' : '직접 플레이',
              if (_Rank.fromKey((entry['result'] as Json)['difficulty'])
                  case final savedRank?)
                savedRank.label,
            ].join(' · '),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if ((entry['result'] as Json)['strategies'] != null)
                LabExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: Text(battleRecord(entry['result'] as Json)),
                  children: [BattleReport(result: entry['result'] as Json)],
                )
              else
                _Result(entry['result'] as Json),
              TextButton.icon(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(
                      text: const JsonEncoder.withIndent('  ').convert(entry)));
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('배틀 데이터를 복사했습니다')));
                  }
                },
                icon: const LabIcon(LabGlyph.copy),
                label: const Text('데이터 복사 (JSON)'),
              ),
            ]),
          ),
      ] else ...[
        Section(
          '내 팀',
          subtitle: manual
              ? '상대 6마리를 보고 선출한 뒤, 매 턴 기술과 교체를 직접 고릅니다.'
              : '양쪽 CPU가 매판 자동 선출하고 싸웁니다. 전략별 강점과 약점, 선출 패턴을 확인합니다.',
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(
                spacing: 12,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  FilterDropdown(
                    value: team?.id,
                    allLabel: '내 파티 선택',
                    labels: {for (final r in widget.roster) r.id: r.name},
                    onChanged: (id) {
                      if (busy || ongoing) return;
                      setState(() {
                        teamId = id;
                        order = [];
                        scouting = battle = report = null;
                        choices.clear();
                      });
                    },
                  ),
                  Text('${sets.length}/6마리'),
                  DropdownButton<_Rank>(
                    icon: const LabIcon(LabGlyph.down, size: 17),
                    value: rank,
                    items: [
                      for (final level in _Rank.values)
                        DropdownMenuItem(
                            value: level, child: Text('CPU · ${level.label}')),
                    ],
                    onChanged: busy || ongoing
                        ? null
                        : (level) {
                            if (level != null) setState(() => rank = level);
                          },
                  ),
                ]),
            Text(rank.description, style: theme.textTheme.bodySmall),
            if (sets.isNotEmpty && sets.length < limit)
              Text('현재 팀은 ${sets.length}마리만 선출할 수 있어 인원 차이가 결과에 반영됩니다.'),
            const SizedBox(height: 10),
            Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  if (manual)
                    FilledButton.icon(
                      onPressed: canStart ? () => _scout(team) : null,
                      icon: const LabIcon(LabGlyph.play),
                      label: Text(scouting == null ? '상대 찾기' : '새 상대 찾기'),
                    ),
                  if (!manual)
                    FilledButton.icon(
                      onPressed:
                          canStart ? () => _start(team, batch: true) : null,
                      icon: const LabIcon(LabGlyph.repeat),
                      label: Text('$runs판 시뮬레이션'),
                    ),
                  if (!manual)
                    DropdownButton<int>(
                      icon: const LabIcon(LabGlyph.down, size: 17),
                      value: runs,
                      items: [
                        for (final n in [20, 50, 100, 200])
                          DropdownMenuItem(value: n, child: Text('$n판'))
                      ],
                      onChanged: busy || ongoing
                          ? null
                          : (n) => setState(() => runs = n ?? runs),
                    ),
                  if (!ongoing && activity != null) BattleLoading(activity!),
                ]),
          ]),
        ),
        if (manual && scouting != null)
          if (team != null && battle == null)
            KeyedSubtree(
              key: scoutKey,
              child: BattleReveal(
                  key: ValueKey(scouting!['seed']),
                  child: _preview(scouting!, team)),
            ),
        if (manual && battle != null) _battleView(battle!),
        if (!manual && report != null)
          Section('반복 배틀 결과',
              subtitle:
                  '$teamName · ${_Rank.fromKey(report!['difficulty'])?.label ?? rank.label}',
              child: BattleReport(
                key: ValueKey(report!['seed']),
                result: report!,
                onPractice: !canStart
                    ? null
                    : (seed) => _scout(team,
                        seed: seed,
                        replayRank: _Rank.fromKey(report!['difficulty'])),
              )),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            '가상 배틀 수치는 앱의 근사 엔진과 CPU 행동 기준입니다. 명중·난수·우선도·교체, 날씨와 일부 필드·보조기를 반영합니다. '
            '선출 순서의 첫 메가 후보에 메가 상태를 적용하며, 장판·상태이상과 기술의 세부 효과는 제한됩니다.',
            style: theme.textTheme.bodySmall,
          ),
        ),
      ],
    ]);
  }

  Widget _preview(Json preview, _Roster team) {
    final foe = preview['opponent'] as Json;
    final threat = preview['threat'] as Json;
    final opponents = (foe['members'] as List).cast<Json>();
    final suggested = (preview['selection'] as List).cast<String>();
    final count = team.sets.length < limit ? team.sets.length : limit;
    final width = widget.format == 'Doubles' ? 2 : 1;
    return Section(
      '상대 파티 · ${foe['label']}',
      subtitle: foe['plan'] as String,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final mon in opponents) MonPill(mon, caption: _role(mon)),
        ]),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('상대 세트 상세'),
          children: [
            for (final mon in opponents)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(_monName(mon)),
                subtitle: Text([
                  mon['itemKo'] ?? (mon['set'] as Json)['item'],
                  mon['abilityKo'] ?? (mon['set'] as Json)['ability'],
                  for (final m in (mon['moveInfo'] as List).cast<Json>())
                    m['ko'] ?? m['name'],
                ].whereType<String>().join(' · ')),
              ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
            '경계 대상 ${_monName(threat['foe'] as Json)} · 추천 대응 ${_monName(threat['counter'] as Json)} (상성 점수 ${threat['score']}/100)'),
        const SizedBox(height: 12),
        Text('내 선출 · ${order.length}/$count',
            style: Theme.of(context).textTheme.titleSmall),
        Text('처음 $width마리가 선봉입니다. 바꾸려면 선출을 해제하고 원하는 순서로 다시 고르세요.'),
        Wrap(spacing: 6, runSpacing: 4, children: [
          for (final s in team.sets)
            _selectionChip(s['id'] as String, width, count),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: busy || order.length != count
                ? null
                : () => _start(team, batch: false),
            icon: const LabIcon(LabGlyph.play),
            label: const Text('이 선출로 시작'),
          ),
          TextButton(
            onPressed:
                busy ? null : () => setState(() => order = suggested.toList()),
            child: const Text('추천 선출 적용'),
          ),
        ]),
      ]),
    );
  }

  Widget _selectionChip(String id, int width, int count) {
    final index = order.indexOf(id);
    final position = index < 0
        ? ''
        : index < width
            ? '선봉 ${index + 1} · '
            : '후발 ${index - width + 1} · ';
    return FilterChip(
      selected: index >= 0,
      showCheckmark: false,
      label: Text('$position${widget.names[id] ?? id}'),
      onSelected: busy || (index < 0 && order.length >= count)
          ? null
          : (add) => setState(() => order =
              add ? [...order, id] : order.where((n) => n != id).toList()),
    );
  }

  Widget _battleView(Json current) {
    final teams = (current['teams'] as List)
        .map((team) => (team as List).cast<Json?>())
        .toList();
    final active = (current['active'] as List)
        .map((side) => (side as List).cast<int?>())
        .toList();
    final options = (current['options'] as List).cast<Json>();
    final winner = current['winner'] as String?;
    final logs = (current['log'] as List).cast<Json>();
    final recent = logs.isEmpty
        ? const <Json>[]
        : logs.where((event) => event['turn'] == logs.last['turn']).toList();
    final field = (current['field'] as List).cast<String>();
    final replacement = current['replacement'] as Json?;
    final vacancies = (replacement?['slots'] as List? ?? []).cast<int>();
    final reserves = (replacement?['bench'] as List? ?? []).cast<int>();
    final need =
        vacancies.length < reserves.length ? vacancies.length : reserves.length;
    final swaps = choices.values
        .where((action) => action['kind'] == 'switch')
        .map((action) => action['target'])
        .toSet();
    final foe = current['opponent'] as Json;
    final shown = teams[1].whereType<Json>().map((mon) => mon['id']).toSet();
    final turn = current['turn'] as int;
    final targets = {
      for (final (slot, index) in active[1].indexed)
        if (index != null) slot: _monName(teams[1][index]!),
    };
    final playedRank = _Rank.fromKey(current['difficulty']) ?? rank;
    return Section(
      winner != null
          ? _results[winner]!
          : replacement != null
              ? '교체 포켓몬 선택'
              : '$turn턴 · 명령 선택',
      subtitle: '$teamName vs $foeName · CPU ${playedRank.label}',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        BattleReveal(
          key: ValueKey(current['id']),
          child: BattleStage(teams: teams, active: active),
        ),
        const SizedBox(height: 8),
        if (field.isNotEmpty)
          Wrap(spacing: 6, runSpacing: 4, children: [
            for (final condition in field)
              Chip(
                avatar: const LabIcon(LabGlyph.spark, size: 15),
                label: Text(condition),
                visualDensity: VisualDensity.compact,
              ),
          ]),
        if (recent.isNotEmpty)
          AnimatedSwitcher(
            duration: MediaQuery.disableAnimationsOf(context)
                ? Duration.zero
                : const Duration(milliseconds: 200),
            layoutBuilder: (current, previous) =>
                current ?? const SizedBox.shrink(),
            child: BattleMessages(
              recent,
              key: ValueKey((turn, logs.length, replacement != null)),
            ),
          ),
        const SizedBox(height: 12),
        if (replacement != null) ...[
          Text(need == 1 ? '대기 포켓몬 한 마리를 내보내세요.' : '빈 자리마다 다른 대기 포켓몬을 골라 주세요.'),
          for (final slot in vacancies)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text('${slot + 1}번 자리'),
                    for (final index in reserves)
                      ChoiceChip(
                        label: Text(_monName(teams[0][index]!)),
                        selected: replacements[slot] == index,
                        onSelected: busy
                            ? null
                            : (selected) => setState(() {
                                  if (selected) {
                                    replacements.removeWhere(
                                        (key, value) => value == index);
                                    replacements[slot] = index;
                                  } else {
                                    replacements.remove(slot);
                                  }
                                }),
                      ),
                  ]),
            ),
        ] else
          for (final group in options)
            BattleCommandMenu(
              key: ValueKey((turn, group['slot'])),
              name: _monName(teams[0][active[0][group['slot'] as int]!]!),
              options: (group['options'] as List).cast<Json>(),
              selected: choices[group['slot']],
              targets: targets,
              reserved: {
                for (final entry in choices.entries)
                  if (entry.key != group['slot'] &&
                      entry.value['kind'] == 'switch')
                    entry.value['target'] as int,
              },
              onSelected: busy
                  ? null
                  : (action) => setState(() {
                        final slot = group['slot'] as int;
                        if (action == null) {
                          choices.remove(slot);
                        } else {
                          choices[slot] = action;
                        }
                      }),
            ),
        if (winner == null)
          Wrap(
              spacing: 8,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                FilledButton.icon(
                  icon: LabIcon(
                      replacement == null ? LabGlyph.play : LabGlyph.swap),
                  onPressed: busy ||
                          (replacement != null
                              ? replacements.length != need
                              : choices.length != options.length ||
                                  swaps.length !=
                                      choices.values
                                          .where((action) =>
                                              action['kind'] == 'switch')
                                          .length)
                      ? null
                      : () => _turn(replace: replacement != null),
                  label: Text(replacement == null ? '명령 확정' : '교체 확정'),
                ),
                TextButton(
                  onPressed: busy
                      ? null
                      : () => setState(() {
                            battle = null;
                            choices.clear();
                            replacements.clear();
                          }),
                  child: const Text('배틀 종료'),
                ),
                if (activity != null) BattleLoading(activity!),
              ])
        else
          _Result(current),
        LabExpansionTile(
          title: Text('상대 로스터 · ${foe['label']}'),
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final mon in (foe['members'] as List).cast<Json>())
                MonPill(mon,
                    caption: shown.contains(mon['id'])
                        ? '출전 확인'
                        : winner == null
                            ? '선출 미공개'
                            : '미선출'),
            ]),
          ],
        ),
        if (logs.isNotEmpty) BattleMessageHistory(logs),
      ]),
    );
  }
}

String _monName(Json mon) => (mon['ko'] ?? mon['name']) as String;

String _role(Json mon) {
  final types =
      (mon['covers'] as List).cast<String>().map((t) => typeKo[t] ?? t);
  final why = mon['why'] as String;
  return types.isEmpty ? why : '${types.join('·')} $why';
}

class _Result extends StatelessWidget {
  final Json result;
  const _Result(this.result);

  @override
  Widget build(BuildContext context) {
    final runs = result['runs'] as int?;
    final members =
        runs == null ? result['teams'][0] as List : result['members'] as List;
    final wins = result['win'] as int?;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(runs == null
          ? "${_results[result['winner']]} · ${(result['turn'] as int) - 1}턴"
          : "$runs판 · $wins승 ${result['loss']}패 ${result['draw']}무 · 승률 ${fmtPct(100 * wins! / runs)} · 평균 ${result['avgTurns']}턴"),
      const SizedBox(height: 6),
      for (final m in members.cast<Json>())
        Text(
            "${m['ko'] ?? m['name']} · 준 피해 ${m['dealt']} · 받은 피해 ${m['taken']} · KO ${m['kos']}"),
    ]);
  }
}
