import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

/// 팀의 한 자리. `set` 은 서버로 보내는 세트(id/moves/item/ability/nature/points/mega),
/// `detail` 은 편집 화면에 필요한 포켓몬 상세(배운 기술, 사용 통계 등).
class TeamSlot {
  final Json set;
  final Json detail;
  const TeamSlot(this.set, this.detail);
  TeamSlot withSet(Json s) => TeamSlot(s, detail);

  /// 화면에 보일 스프라이트 (메가 세트면 메가 폼)
  String get sprite {
    for (final m in (detail['megas'] as List).cast<Json>()) {
      if (m['name'] == set['mega']) return m['sprite'] as String;
    }
    return detail['sprite'] as String;
  }
}

class _SavedTeam {
  String name;
  List<TeamSlot> slots;
  _SavedTeam(this.name, this.slots);
}

/// 팀 전환 UI용 요약
class TeamSummary {
  final String name;
  final List<String> sprites;
  final List<Json> sets;
  const TeamSummary(this.name, this.sprites, this.sets);
}

final teamListProvider = StateProvider<List<TeamSummary>>((ref) => const [TeamSummary('팀 1', [], [])]);
final activeTeamIndexProvider = StateProvider<int>((ref) => 0);

/// 여러 팀을 저장하고 그중 하나를 '현재 팀'으로 쓴다. state 는 현재 팀의 슬롯 목록.
class TeamNotifier extends StateNotifier<List<TeamSlot>> {
  final Ref ref;
  final List<_SavedTeam> _teams = [_SavedTeam('팀 1', [])];
  int _active = 0;
  bool _loaded = false;
  late final Future<void> _initialLoad;

  TeamNotifier(this.ref) : super(const []) {
    _initialLoad = _load();
    ref.listen(formatProvider, (_, __) => _reloadDetails());
  }

  static const _key = 'teams_v2';
  static const _legacyKey = 'team_v1';

  List<TeamSlot> get _cur => _teams[_active].slots;
  String get activeName => _teams[_active].name;
  int get teamCount => _teams.length;

  void _publish({bool save = true}) {
    state = [..._cur];
    ref.read(teamListProvider.notifier).state = [
      for (final t in _teams)
        TeamSummary(t.name, [for (final s in t.slots) s.sprite], [for (final s in t.slots) s.set])
    ];
    ref.read(activeTeamIndexProvider.notifier).state = _active;
    if (save && _loaded) _save();
  }

  Future<List<TeamSlot>> _slotsFor(List sets, String fmt, Map<String, Future<Json>> cache) async {
    final out = <TeamSlot>[];
    for (final s in sets.cast<Json>()) {
      try {
        final id = s['id'] as String;
        out.add(TeamSlot(s, await (cache[id] ??= fetchDetail(id, fmt))));
      } catch (_) {/* 더 이상 없는 포켓몬은 건너뛴다 */}
    }
    return out;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final fmt = ref.read(formatProvider);
      final cache = <String, Future<Json>>{};
      final raw = prefs.getString(_key);
      if (raw != null) {
        final data = jsonDecode(raw) as Json;
        final loaded = <_SavedTeam>[];
        for (final t in (data['teams'] as List).cast<Json>()) {
          loaded.add(_SavedTeam(t['name'] as String, await _slotsFor(t['sets'] as List, fmt, cache)));
        }
        if (loaded.isNotEmpty && _teams.every((t) => t.slots.isEmpty)) {
          _teams
            ..clear()
            ..addAll(loaded);
          _active = ((data['active'] ?? 0) as int).clamp(0, _teams.length - 1);
        }
      } else {
        final legacy = prefs.getString(_legacyKey); // 단일 팀 시절 저장분
        if (legacy != null && _cur.isEmpty) {
          _teams[0].slots = await _slotsFor(jsonDecode(legacy) as List, fmt, cache);
        }
      }
    } catch (_) {/* 저장된 팀을 못 읽으면 빈 팀으로 시작 */}
    _loaded = true;
    _publish();
  }

  /// 배틀 형식이 바뀌면 채용률 등 상세 데이터를 그 형식 기준으로 다시 받는다.
  Future<void> _reloadDetails() async {
    final fmt = ref.read(formatProvider);
    final cache = <String, Future<Json>>{};
    for (final t in _teams) {
      t.slots = await _slotsFor([for (final s in t.slots) s.set], fmt, cache);
    }
    _publish(save: false);
  }

  Future<void> _save({bool reportFailure = false}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = await prefs.setString(
          _key,
          jsonEncode({
            'active': _active,
            'teams': [
              for (final t in _teams)
                {
                  'name': t.name,
                  'sets': [for (final s in t.slots) s.set]
                }
            ]
          }));
      if (!saved && reportFailure) throw StateError('team write failed');
    } catch (_) {
      if (reportFailure) rethrow;
    }
  }

  // ---------- 현재 팀 편집 ----------
  bool get isFull => _cur.length >= 6;

  /// 가장 많이 쓰이는 세트로 추가한다. [set] 을 주면 그 세트로 추가(조커/교체 추천).
  Future<void> add(String id, {Json? set, int? replaceAt}) async {
    final target = _teams[_active];
    final detail = await fetchDetail(id, ref.read(formatProvider));
    final slot = TeamSlot(Json.from(set ?? detail['defaultSet'] as Json), detail);
    if (replaceAt != null && replaceAt < target.slots.length) {
      target.slots[replaceAt] = slot;
    } else if (target.slots.length < 6) {
      target.slots.add(slot);
    } else {
      return;
    }
    _publish();
  }

  void update(int i, Json set) {
    if (i >= _cur.length) return;
    _cur[i] = _cur[i].withSet(set);
    _publish();
  }

  void removeAt(int i) {
    if (i >= _cur.length) return;
    _cur.removeAt(i);
    _publish();
  }

  void clear() {
    _cur.clear();
    _publish();
  }

  /// 현재 팀을 주어진 세트들로 통째로 바꾼다 (텍스트 가져오기).
  Future<void> replaceWith(List<Json> sets) async {
    _teams[_active].slots = await _slotsFor(sets.take(6).toList(), ref.read(formatProvider), {});
    _publish();
  }

  // ---------- 팀 목록 ----------
  void select(int i) {
    if (i < 0 || i >= _teams.length) return;
    _active = i;
    _publish();
  }

  void create() {
    var n = _teams.length + 1;
    while (_teams.any((t) => t.name == '팀 $n')) {
      n++;
    }
    _teams.add(_SavedTeam('팀 $n', []));
    _active = _teams.length - 1;
    _publish();
  }

  Future<void> saveParty(String name, List<Json> sets, String format) async {
    await _initialLoad;
    final slots = await Future.wait([
      for (final set in sets)
        fetchDetail(set['id'] as String, format).then((detail) => TeamSlot(Json.from(set), detail)),
    ]);
    if (!mounted) return;
    final saved = _SavedTeam(name, slots);
    final previous = _teams[_active];
    _teams.add(saved);
    _active = _teams.length - 1;
    try {
      await _save(reportFailure: true);
    } catch (_) {
      final active = _teams[_active];
      _teams.remove(saved);
      _active = _teams.indexOf(active == saved ? previous : active).clamp(0, _teams.length - 1);
      _publish(save: false);
      rethrow;
    }
    _publish(save: false);
  }

  void rename(int i, String name) {
    if (name.trim().isEmpty) return;
    _teams[i].name = name.trim();
    _publish();
  }

  void duplicate(int i) {
    final src = _teams[i];
    _teams.insert(i + 1, _SavedTeam('${src.name} 복사본', [for (final s in src.slots) TeamSlot(Json.from(s.set), s.detail)]));
    _active = i + 1;
    _publish();
  }

  void delete(int i) {
    if (_teams.length == 1) {
      _teams[0]
        ..name = '팀 1'
        ..slots = [];
    } else {
      _teams.removeAt(i);
      if (_active >= _teams.length || _active > i) _active = (_active - 1).clamp(0, _teams.length - 1);
    }
    _publish();
  }
}

final teamProvider = StateNotifierProvider<TeamNotifier, List<TeamSlot>>((ref) => TeamNotifier(ref));

/// 팀이 바뀌면 자동으로 다시 분석한다.
final analysisProvider = FutureProvider<Json?>((ref) async {
  final team = ref.watch(teamProvider);
  final fmt = ref.watch(formatProvider);
  final topN = ref.watch(analysisTopNProvider);
  if (team.isEmpty) return null;
  final res = await dio.post('/api/team/analyze', data: {
    'format': fmt,
    'topN': topN,
    'team': [for (final s in team) s.set],
  });
  return res.data as Json;
});

final analysisTopNProvider = StateProvider<int>((ref) => 20);

// ---------------------------------------------------------------- 텍스트 내보내기 / 가져오기

const _statLabel = {'hp': 'HP', 'atk': 'Atk', 'def': 'Def', 'spa': 'SpA', 'spd': 'SpD', 'spe': 'Spe'};

/// Showdown 형식에 가까운 텍스트로 내보낸다. 능력 포인트는 `SPs:` 줄에 적는다.
String exportTeamText(List<TeamSlot> team) {
  final b = StringBuffer();
  for (final s in team) {
    final set = s.set;
    b.writeln('${s.detail['name']}${set['item'] != null ? ' @ ${set['item']}' : ''}');
    if (set['ability'] != null) b.writeln('Ability: ${set['ability']}');
    b.writeln('Level: 50');
    final pts = (set['points'] ?? const {}) as Map;
    final parts = [
      for (final k in _statLabel.keys)
        if (((pts[k] ?? 0) as num) > 0) '${pts[k]} ${_statLabel[k]}'
    ];
    if (parts.isNotEmpty) b.writeln('SPs: ${parts.join(' / ')}');
    if (set['nature'] != null) b.writeln('${set['nature']} Nature');
    for (final m in (set['moves'] as List? ?? const [])) {
      b.writeln('- $m');
    }
    b.writeln();
  }
  return b.toString().trimRight();
}

/// 텍스트를 세트 목록으로 읽는다. 이름을 못 찾은 포켓몬은 [unknown] 에 담는다.
List<Json> importTeamText(String text, List<Json> allPokemon, List<String> unknown) {
  String norm(String s) => s.toLowerCase().replaceAll(RegExp('[^a-z0-9]'), '');
  final byName = {for (final p in allPokemon) norm(p['name'] as String): p};
  final byKo = {for (final p in allPokemon) (p['ko'] ?? '') as String: p};
  final labelToKey = {for (final e in _statLabel.entries) e.value.toLowerCase(): e.key};
  final sets = <Json>[];
  for (final block in text.replaceAll('\r', '').split(RegExp(r'\n\s*\n'))) {
    final lines = block.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
    if (lines.isEmpty) continue;
    final head = lines.first.split('@');
    var name = head.first.replaceAll(RegExp(r'\((M|F)\)'), '').trim();
    final nick = RegExp(r'\(([^)]+)\)\s*$').firstMatch(name); // "별명 (Species)"
    if (nick != null && !byKo.containsKey(name)) name = nick.group(1)!.trim();
    final p = byName[norm(name)] ?? byKo[name];
    if (p == null) {
      unknown.add(name);
      continue;
    }
    final item = head.length > 1 ? head[1].trim() : null;
    final set = <String, dynamic>{'id': p['id'], 'item': item, 'moves': <String>[], 'mega': null};
    final points = {for (final k in _statLabel.keys) k: 0};
    var hasPoints = false;
    for (final l in lines.skip(1)) {
      if (l.startsWith('-')) {
        (set['moves'] as List).add(l.substring(1).trim());
      } else if (l.toLowerCase().startsWith('ability:')) {
        set['ability'] = l.substring(8).trim();
      } else if (l.endsWith(' Nature')) {
        set['nature'] = l.substring(0, l.length - 7).trim();
      } else if (RegExp(r'^(SPs|EVs):', caseSensitive: false).hasMatch(l)) {
        final isEv = l.toLowerCase().startsWith('evs');
        for (final part in l.substring(4).split('/')) {
          final m = RegExp(r'(\d+)\s*([A-Za-z]+)').firstMatch(part);
          final key = m == null ? null : labelToKey[m.group(2)!.toLowerCase()];
          if (key != null) {
            final v = int.parse(m!.group(1)!);
            points[key] = (isEv ? (v / 8).round() : v).clamp(0, 32);
            hasPoints = true;
          }
        }
      }
    }
    if (hasPoints) set['points'] = points;
    if ((set['moves'] as List).isEmpty) set.remove('moves');
    for (final m in (p['megas'] as List? ?? const []).cast<Json>()) {
      if (item != null && m['stone'] == item) set['mega'] = m['name'];
    }
    sets.add(set);
  }
  return sets;
}
