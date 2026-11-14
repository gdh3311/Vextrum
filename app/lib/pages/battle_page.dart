import 'dart:convert';

import '../lab_icons.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'sim_insights.dart';
import 'battle_console.dart';
import 'battle_report.dart';
import 'battle_arena.dart';
import 'parties_page.dart';
import 'team_switcher.dart';
import '../i18n.dart';

const _historyKey = 'battle_history_v1';
const _results = {'win': '승리', 'loss': '패배', 'draw': '무승부'};

typedef _Roster = ({String id, String name, List<Json> sets});

enum _BattleMode { manual, simulation, history }

enum _Rank {
  poke('몬스터볼', '기본 공격 위주로 행동합니다.'),
  great('슈퍼볼', '유리한 기술을 고르고 기회가 나면 전개합니다.'),
  ultra('하이퍼볼', '전략의 핵심 기술과 KO 기회를 노립니다.'),
  master('마스터볼', '공개된 정보로 두 포켓몬의 공격·방어·교체를 조합해 턴 종료까지 비교합니다.'),
  champion('챔피언', '공개된 기술과 지금까지의 행동을 보고, 방어·교체를 포함한 여러 대응을 최대 두 턴 앞까지 비교합니다.');

  const _Rank(this.label, this.description);
  final String label;
  final String description;

  static _Rank? fromKey(Object? key) =>
      values.where((rank) => rank.name == key).firstOrNull;
}

class BattlePage extends ConsumerWidget {
  const BattlePage({super.key, this.practice});
  final Json? practice;

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
        practice: practice,
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
  final Json? practice;
  const _BattlePractice({
    super.key,
    required this.format,
    required this.roster,
    required this.initialTeam,
    required this.names,
    this.practice,
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

  /// 화면이 재생할 새 배틀 이벤트와 재생 상태
  List<Json> playEvents = const [];
  int playId = 0;
  int seenLog = 0;
  bool playing = false;

  void _queuePlayback(Json result, {bool fresh = false}) {
    final logs = (result['log'] as List).cast<Json>();
    final total = (result['logCount'] as int?) ?? logs.length;
    final count = fresh ? logs.length : (total - seenLog).clamp(0, logs.length);
    playEvents = logs.sublist(logs.length - count);
    seenLog = total;
    playId++;
    playing = playEvents.isNotEmpty;
  }
  String? activity;
  bool get busy => activity != null;
  _BattleMode mode = _BattleMode.manual;
  _Rank rank = _Rank.master;
  String? error;
  int runs = 50;
  String teamName = '';
  String foeName = '';
  Json setup = {};
  String? cpuStyle;
  String? opponentPool;
  int? megaSlot;
  final scoutKey = GlobalKey();
  final arenaKey = GlobalKey();

  /// 다시 고르는 중인 자리 (null 이면 아직 명령이 없는 첫 자리)
  int? editing;

  void _showArena() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (arenaKey.currentContext case final context?) {
        Scrollable.ensureVisible(context,
            alignment: .02, duration: const Duration(milliseconds: 350), curve: Curves.easeOutCubic);
      }
    });
  }

  int get limit => widget.format == 'Doubles' ? 4 : 3;

  @override
  void initState() {
    super.initState();
    _load();
    final plan = widget.practice;
    final sample = plan?['sample'] as Json?;
    final team = widget.roster.where((r) => r.id == widget.initialTeam).firstOrNull;
    if (plan != null && sample != null && team != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final pick = [for (final key in ['lead', 'back'])
          for (final mon in (plan[key] as List).cast<Json>()) mon['id'] as String];
        _scout(team, seed: sample['seed'] as int, replayRank: _Rank.fromKey(plan['difficulty']),
            selection: pick, opponentStyle: sample['cpuStyle'] as String?, pool: sample['pool'] as String?);
      });
    }
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

  Future<void> _scout(_Roster team, {int? seed, _Rank? replayRank,
      List<String>? selection, String? opponentStyle, String? pool}) => _request(
          '/api/battle/scout', {..._body(team), if (seed != null) 'seed': seed,
            if (pool != null) 'opponentPool': pool},
          (result) async {
        setState(() {
          scouting = result;
          mode = _BattleMode.manual;
          rank = replayRank ?? rank;
          order = selection ?? (result['selection'] as List).cast<String>().toList();
          cpuStyle = opponentStyle;
          opponentPool = pool;
          megaSlot = null;
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
      if (!batch && cpuStyle != null) 'cpuStyle': cpuStyle,
      if (!batch && opponentPool != null) 'opponentPool': opponentPool,
    };
    await _request(batch ? '/api/battle/batch' : '/api/battle/start', body,
        (result) async {
      setState(() {
        teamName = team.name;
        foeName = batch
            ? '무작위 전략 파티'
            : (result['opponent'] as Json)['label'] as String;
        choices.clear();
        megaSlot = null;
        replacements.clear();
        editing = null;
        battle = batch ? null : result;
        if (!batch) _queuePlayback(result, fresh: true);
        if (batch) report = result;
        if (batch) scouting = null;
        setup = {...body, 'seed': result['seed']};
      });
      if (batch) await _record(result, 'batch');
      if (!batch) _showArena();
    }, loading: batch ? '$runs판의 전략별 배틀을 진행 중…' : '포켓몬을 내보내는 중…');
  }

  Future<void> _turn({required bool replace}) async {
    final current = battle!;
    final endpoint = replace ? 'replace' : 'turn';
    final phase = (current['replacement'] as Json?)?['phase'];
    await _request('/api/battle/${current['id']}/$endpoint', {
      'turn': current['turn'],
      if (replace && phase != null) 'phase': phase,
      if (!replace && megaSlot != null) 'megaSlot': megaSlot,
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
        megaSlot = null;
        replacements.clear();
        editing = null;
        _queuePlayback(result);
      });
      _showArena();
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
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                if (report!['memberStats'] != null) ...[SimulationInsights(report!), const SizedBox(height: 18)],
                BattleReport(
                key: ValueKey(report!['seed']),
                result: report!,
                onPractice: !canStart
                    ? null
                    : (example) => _scout(team,
                        seed: example['seed'] as int,
                        selection: (example['mine'] as List?)?.cast<String>(),
                        opponentStyle: example['cpuStyle'] as String?,
                        replayRank: _Rank.fromKey(report!['difficulty'])),
              )])),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            '가상 배틀은 명중·난수·우선도·교체와 날씨·순풍·날따름·와이드가드 등을 반영합니다. '
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
    final mine = {
      for (final m in (preview['player'] as List? ?? const []).cast<Json>()) m['id'] as String: m,
    };
    final count = team.sets.length < limit ? team.sets.length : limit;
    final width = widget.format == 'Doubles' ? 2 : 1;
    final cs = Theme.of(context).colorScheme;

    Widget mineCard(String id) {
      final index = order.indexOf(id);
      final picked = index >= 0;
      final lead = picked && index < width;
      final full = order.length >= count;
      final mon = mine[id];
      final name = mon == null ? (widget.names[id] ?? id) : _monName(mon);
      final color = lead ? const Color(0xFFFFC857) : cs.primary;
      return _PreviewCard(
        sprite: mon?['sprite'] as String?,
        name: name,
        types: (mon?['types'] as List?)?.cast<String>() ?? const [],
        badge: !picked ? null : lead ? '선봉 ${index + 1}' : '후발 ${index - width + 1}',
        badgeColor: color,
        selected: picked,
        dimmed: !picked && full,
        onTap: busy || (!picked && full)
            ? null
            : () => setState(() => order = picked ? order.where((n) => n != id).toList() : [...order, id]),
      );
    }

    Widget foeCard(Json mon) => _PreviewCard(
          sprite: mon['sprite'] as String?,
          name: _monName(mon),
          types: (mon['types'] as List?)?.cast<String>() ?? const [],
          caption: _role(mon),
          badgeColor: const Color(0xFFFF9E95),
          foe: true,
        );

    final board = LayoutBuilder(builder: (context, c) {
      final wide = c.maxWidth >= 760;
      Widget column(String title, String sub, List<Widget> cards, Color tone) => Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [tone.withOpacity(.14), tone.withOpacity(.03)]),
              border: Border.all(color: tone.withOpacity(.35)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: tone)),
              Text(sub, style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
              const SizedBox(height: 10),
              LayoutBuilder(builder: (context, cc) {
                final cols = cc.maxWidth >= 330 ? 3 : 2;
                final w = (cc.maxWidth - (cols - 1) * 8) / cols;
                return Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final card in cards) SizedBox(width: w, child: card),
                ]);
              }),
            ]),
          );
      final left = column('내 팀', '내 선출 · ${order.length}/$count', [for (final s in team.sets) mineCard(s['id'] as String)],
          const Color(0xFF7FE6DA));
      final right = column('상대 팀', foe['label'] as String, [for (final m in opponents) foeCard(m)], const Color(0xFFFF9E95));
      if (!wide) return Column(children: [left, const SizedBox(height: 10), right]);
      return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(child: left),
        const Padding(
          padding: EdgeInsets.fromLTRB(10, 90, 10, 0),
          child: Text('VS',
              style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: Color(0xFFFFD27A), letterSpacing: 1)),
        ),
        Expanded(child: right),
      ]);
    });

    return Section(
      '상대 파티 · ${foe['label']}',
      subtitle: foe['plan'] as String,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        board,
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(12)),
          child: Row(children: [
            Sprite((threat['foe'] as Json)['sprite'] as String, size: 40),
            const SizedBox(width: 6),
            const Icon(Icons.arrow_back_rounded, size: 18, color: Color(0xFFFF9E95)),
            Sprite((threat['counter'] as Json)['sprite'] as String, size: 40),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                  '경계 대상 ${_monName(threat['foe'] as Json)} · 추천 대응 ${_monName(threat['counter'] as Json)} (상성 점수 ${threat['score']}/100)',
                  style: const TextStyle(fontSize: 13.5)),
            ),
          ]),
        ),
        LabExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('상대 세트 상세'),
          children: [
            for (final mon in opponents)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Sprite(mon['sprite'] as String, size: 36),
                title: Text(_monName(mon)),
                subtitle: Text([
                  mon['itemKo'] ?? (mon['set'] as Json)['item'],
                  mon['abilityKo'] ?? (mon['set'] as Json)['ability'],
                  for (final m in (mon['moveInfo'] as List).cast<Json>()) m['ko'] ?? m['name'],
                ].whereType<String>().join(' · ')),
              ),
          ],
        ),
        Text('처음 $width마리가 선봉입니다. 바꾸려면 선출을 해제하고 원하는 순서로 다시 고르세요.',
            style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16)),
            onPressed: busy || order.length != count ? null : () => _start(team, batch: false),
            icon: const LabIcon(LabGlyph.play),
            label: const Text('이 선출로 시작'),
          ),
          TextButton(
            onPressed: busy ? null : () => setState(() => order = suggested.toList()),
            child: const Text('추천 선출 적용'),
          ),
        ]),
      ]),
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
    final field = (current['field'] as List).cast<String>();
    final replacement = current['replacement'] as Json?;
    final pivot = replacement?['kind'] == 'pivot';
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
    final playedRank = _Rank.fromKey(current['difficulty']) ?? rank;
    final prompt = replacement != null
        ? (pivot ? '교체할 포켓몬을 고르세요.' : '다음 포켓몬을 고르세요.')
        : winner != null
            ? null
            : options.isEmpty
                ? null
                : '${_monName(teams[0][active[0][options.first['slot'] as int]!]!)}${josa(_monName(teams[0][active[0][options.first['slot'] as int]!]!), '은', '는')} 무엇을 할까?';
    final foes = <int, Json>{
      for (final (slot, index) in active[1].indexed)
        if (index != null && teams[1][index] != null) slot: teams[1][index]!,
    };
    final locked = busy || playing;
    return Section(
      winner != null
          ? _results[winner]!
          : replacement != null
              ? (pivot ? '$turn턴 · 기술 후 교체' : '교체 포켓몬 선택')
              : '$turn턴 · 명령 선택',
      subtitle: '$teamName vs $foeName · CPU ${playedRank.label}',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        LayoutBuilder(builder: (context, box) {
          final arena = BattleReveal(
            key: ValueKey(current['id']),
            child: BattleArena(
              teams: teams,
              active: active,
              field: field,
              events: playEvents,
              playKey: playId,
              turn: turn,
              prompt: prompt,
              weather: current['weather'] as String? ?? '',
              terrain: current['terrain'] as String? ?? '',
              onPlayback: (on) {
                if (mounted && playing != on) setState(() => playing = on);
              },
            ),
          );
          final panel = AnimatedOpacity(
            duration: const Duration(milliseconds: 200),
            opacity: playing ? .45 : 1,
            child: IgnorePointer(
              ignoring: playing,
              child: _commandArea(current, teams, active, options, foes, replacement, vacancies, reserves, need,
                  swaps, pivot, winner, turn, locked),
            ),
          );
          // 넓은 화면은 실제 게임처럼 경기장 오른쪽에 명령 메뉴를 둔다.
          if (box.maxWidth >= 880 && winner == null) {
            return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: KeyedSubtree(key: arenaKey, child: arena)),
              const SizedBox(width: 14),
              SizedBox(width: box.maxWidth >= 1100 ? 400 : 350, child: panel),
            ]);
          }
          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            KeyedSubtree(key: arenaKey, child: arena),
            const SizedBox(height: 14),
            panel,
          ]);
        }),
        if (winner != null && !playing) ...[
          const SizedBox(height: 14),
          BattleResultBanner(
            winner: winner,
            turns: turn - 1,
            members: teams[0].whereType<Json>().toList(),
          ),
          _Result(current),
        ],
        const SizedBox(height: 6),
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


  Widget _commandArea(
      Json current,
      List<List<Json?>> teams,
      List<List<int?>> active,
      List<Json> options,
      Map<int, Json> foes,
      Json? replacement,
      List<int> vacancies,
      List<int> reserves,
      int need,
      Set<Object?> swaps,
      bool pivot,
      String? winner,
      int turn,
      bool locked) {
    final cs = Theme.of(context).colorScheme;
    if (winner != null) return const SizedBox();
    final endButton = TextButton(
      onPressed: locked
          ? null
          : () => setState(() {
                battle = null;
                choices.clear();
                replacements.clear();
              }),
      child: const Text('배틀 종료'),
    );
    if (replacement != null) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(pivot
            ? '교체할 포켓몬을 고르면 이번 턴의 남은 행동이 이어집니다.'
            : need == 1
                ? '대기 포켓몬 한 마리를 내보내세요.'
                : '빈 자리마다 다른 대기 포켓몬을 골라 주세요.'),
        for (final slot in vacancies)
          ReplacementPicker(
            slot: slot,
            bench: reserves,
            team: teams[0],
            chosen: replacements[slot],
            taken: replacements.values.toSet(),
            onPick: locked
                ? null
                : (index) => setState(() {
                      if (index == null) {
                        replacements.remove(slot);
                      } else {
                        replacements.removeWhere((key, value) => value == index);
                        replacements[slot] = index;
                      }
                    }),
          ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
          FilledButton.icon(
            style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16)),
            icon: const LabIcon(LabGlyph.swap),
            onPressed: locked || replacements.length != need ? null : () => _turn(replace: true),
            label: const Text('교체 확정'),
          ),
          endButton,
          if (activity != null) BattleLoading(activity!),
        ]),
      ]);
    }
    final slots = [for (final g in options) g['slot'] as int];
    final megaOptions = (battle?['megaOptions'] as List? ?? const []).cast<int>();
    final pending = slots.where((slot) => !choices.containsKey(slot)).firstOrNull;
    final now = editing != null && slots.contains(editing) ? editing : pending;
    final switchCount = choices.values.where((action) => action['kind'] == 'switch').length;
    final ready = !locked && choices.length == options.length && swaps.length == switchCount;
    Json mon(int slot) => teams[0][active[0][slot]!]!;

    String summary(Json action) {
      if (action['kind'] == 'switch') return '→ ${_monName(teams[0][action['target'] as int]!)}';
      final target = foes[action['target']];
      return target == null ? '${action['label']}' : '${action['label']} → ${_monName(target)}';
    }

    final steps = slots.length < 2
        ? const SizedBox()
        : Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Row(children: [
              for (final (i, slot) in slots.indexed) ...[
                if (i > 0) const SizedBox(width: 8),
                Expanded(
                  child: Material(
                    color: slot == now ? cs.primary.withOpacity(.16) : cs.surfaceContainer,
                    borderRadius: BorderRadius.circular(12),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: locked ? null : () => setState(() => editing = slot),
                      child: Container(
                        padding: const EdgeInsets.fromLTRB(6, 6, 10, 6),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: slot == now ? cs.primary : Colors.transparent, width: 1.4),
                        ),
                        child: Row(children: [
                          Sprite(mon(slot)['sprite'] as String, size: 30),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              choices[slot] == null
                                  ? (slot == now ? '고르는 중' : '대기')
                                  : summary(choices[slot]!),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                  color: choices[slot] == null ? cs.onSurfaceVariant : cs.primary),
                            ),
                          ),
                          if (choices[slot] != null) Icon(Icons.check_rounded, size: 16, color: cs.primary),
                        ]),
                      ),
                    ),
                  ),
                ),
              ],
            ]),
          );

    final Widget body;
    if (now != null) {
      final index = slots.indexOf(now);
      final group = options[index];
      body = GameCommandPanel(
        key: ValueKey((turn, now)),
        mon: mon(now),
        step: slots.length > 1 ? '${index + 1}/${slots.length}' : null,
        options: (group['options'] as List).cast<Json>(),
        selected: choices[now],
        foes: foes,
        team: teams[0],
        reserved: {
          for (final entry in choices.entries)
            if (entry.key != now && entry.value['kind'] == 'switch') entry.value['target'] as int,
        },
        onBack: index > 0 && !locked ? () => setState(() => editing = slots[index - 1]) : null,
        onSelected: locked
            ? null
            : (action) => setState(() {
                  if (action == null) {
                    choices.remove(now);
                  } else {
                    choices[now] = action;
                    if (megaSlot == now && action['kind'] != 'move') megaSlot = null;
                    editing = null;
                  }
                }),
      );
    } else {
      body = _ConfirmCard(
        lines: [for (final slot in slots) (mon(slot), summary(choices[slot]!))],
        onConfirm: ready ? () => _turn(replace: false) : null,
        onBack: locked ? null : () => setState(() => editing = slots.last),
      );
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      steps,
      if (megaOptions.isNotEmpty)
        Wrap(spacing: 8, children: [
          for (final slot in megaOptions)
            if (choices[slot] == null || choices[slot]?['kind'] == 'move')
              FilterChip(
                label: Text("${_monName(mon(slot))} · ${tr('메가진화')}"),
                selected: megaSlot == slot,
                onSelected: locked ? null : (selected) => setState(() => megaSlot = selected ? slot : null),
              ),
        ]),
      body,
      Wrap(spacing: 8, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
        endButton,
        if (MediaQuery.sizeOf(context).width >= 700)
          Text('단축키 · 1~4 기술 · S 교체 · Backspace 뒤로 · Enter 확정',
              style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
        if (activity != null) BattleLoading(activity!),
      ]),
    ]);
  }
}

/// 모든 명령을 고른 뒤의 확인 카드 (Enter 확정, Backspace 다시 고르기)
class _ConfirmCard extends StatefulWidget {
  const _ConfirmCard({required this.lines, required this.onConfirm, required this.onBack});
  final List<(Json, String)> lines;
  final VoidCallback? onConfirm;
  final VoidCallback? onBack;

  @override
  State<_ConfirmCard> createState() => _ConfirmCardState();
}

class _ConfirmCardState extends State<_ConfirmCard> {
  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_onKey);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_onKey);
    super.dispose();
  }

  bool _onKey(KeyEvent event) {
    if (event is! KeyDownEvent || !commandKeysAllowed()) return false;
    if (event.logicalKey == LogicalKeyboardKey.enter || event.logicalKey == LogicalKeyboardKey.numpadEnter) {
      widget.onConfirm?.call();
      return widget.onConfirm != null;
    }
    if (event.logicalKey == LogicalKeyboardKey.backspace || event.logicalKey == LogicalKeyboardKey.escape) {
      widget.onBack?.call();
      return widget.onBack != null;
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: cs.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: cs.primary.withOpacity(.7), width: 1.4),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('이번 턴 명령', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          for (final (mon, text) in widget.lines)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(children: [
                Sprite(mon['sprite'] as String, size: 32),
                const SizedBox(width: 6),
                Expanded(child: Text(text, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
              ]),
            ),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                icon: const LabIcon(LabGlyph.play),
                onPressed: widget.onConfirm,
                label: const Text('명령 확정 (Enter)'),
              ),
            ),
            const SizedBox(width: 8),
            OutlinedButton(
              style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 14)),
              onPressed: widget.onBack,
              child: const Text('다시 고르기'),
            ),
          ]),
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

/// 선출 화면의 포켓몬 카드
class _PreviewCard extends StatelessWidget {
  const _PreviewCard({
    required this.sprite,
    required this.name,
    required this.types,
    required this.badgeColor,
    this.badge,
    this.caption,
    this.selected = false,
    this.dimmed = false,
    this.foe = false,
    this.onTap,
  });
  final String? sprite;
  final String name;
  final List<String> types;
  final String? badge;
  final Color badgeColor;
  final String? caption;
  final bool selected;
  final bool dimmed;
  final bool foe;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 150),
      opacity: dimmed ? .45 : 1,
      child: Material(
        color: selected ? badgeColor.withOpacity(.16) : cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Container(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: selected ? badgeColor : cs.outlineVariant, width: selected ? 2 : 1),
            ),
            child: Column(children: [
              Stack(clipBehavior: Clip.none, children: [
                Center(
                  child: sprite == null
                      ? const SizedBox(height: 64)
                      : (foe ? Sprite(sprite!, size: 64) : Transform.flip(flipX: true, child: Sprite(sprite!, size: 64))),
                ),
                if (badge != null)
                  Positioned(
                    left: 0,
                    top: 0,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(color: badgeColor, borderRadius: BorderRadius.circular(8)),
                      child: Text(badge!,
                          style: const TextStyle(color: Color(0xFF0A1424), fontSize: 11.5, fontWeight: FontWeight.w800)),
                    ),
                  ),
              ]),
              const SizedBox(height: 4),
              Text(name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700)),
              const SizedBox(height: 3),
              TypeRow(types, dense: true),
              if (caption != null) ...[
                const SizedBox(height: 4),
                Text(caption!,
                    maxLines: 2,
                    textAlign: TextAlign.center,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant, height: 1.3)),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}
