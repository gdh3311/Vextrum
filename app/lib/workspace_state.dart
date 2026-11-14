import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'settings.dart';
import 'team_state.dart';

/// 팀의 버전 번호. 같은 구성이면 같은 번호 (되돌리기 후에도 일치) → 결과가 '지금 팀'의 것인지 판별한다.
int teamRevisionOf(List<Json> sets) {
  var h = 0x811c9dc5;
  for (final c in jsonEncode(sets).codeUnits) {
    h = ((h ^ c) * 0x01000193) & 0x7fffffff;
  }
  return h;
}

final teamRevisionProvider = Provider<int>((ref) => teamRevisionOf([for (final s in ref.watch(teamProvider)) s.set]));

/// 슬롯별 잠금: pokemon / moves / item / ability / nature / points / mega
const lockFields = ['pokemon', 'moves', 'item', 'ability', 'nature', 'points'];
const lockLabels = {
  'pokemon': '포켓몬',
  'moves': '기술',
  'item': '도구',
  'ability': '특성',
  'nature': '성격',
  'points': '능력 포인트',
};

class LockState extends StateNotifier<Map<String, List<Map<String, bool>>>> {
  LockState() : super(const {}) {
    _load();
  }
  static const _key = 'workspace_locks_v1';

  Future<void> _load() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_key);
      if (raw == null) return;
      final data = jsonDecode(raw) as Map<String, dynamic>;
      state = {
        for (final e in data.entries)
          e.key: [for (final m in (e.value as List)) Map<String, bool>.from(m as Map)]
      };
    } catch (_) {}
  }

  Future<void> _save() async {
    try {
      await (await SharedPreferences.getInstance()).setString(_key, jsonEncode(state));
    } catch (_) {}
  }

  List<Map<String, bool>> of(String team, int n) {
    final cur = state[team] ?? const [];
    return [for (var i = 0; i < n; i++) i < cur.length ? cur[i] : <String, bool>{}];
  }

  void toggle(String team, int slot, String field, int n) {
    final cur = of(team, n);
    cur[slot] = {...cur[slot], field: !(cur[slot][field] ?? false)};
    state = {...state, team: cur};
    _save();
  }

  /// 슬롯이 지워지거나 순서가 바뀔 때 잠금도 함께 옮긴다.
  void removeAt(String team, int slot, int n) {
    final cur = of(team, n)..removeAt(slot);
    state = {...state, team: cur};
    _save();
  }
}

final lockProvider = StateNotifierProvider<LockState, Map<String, List<Map<String, bool>>>>((ref) => LockState());

/// 잠긴 필드를 원래 세트 값으로 되돌린다 (서버 workbench.apply_locks 와 같은 규칙).
Json applyLocks(Json old, Json proposed, Map<String, bool> locks) {
  if ((locks['pokemon'] ?? false) && proposed['id'] != old['id']) {
    throw StateError('잠긴 포켓몬은 교체할 수 없습니다');
  }
  if (proposed['id'] != old['id']) return Json.from(proposed);
  final out = Json.from(proposed);
  for (final f in lockFields.skip(1)) {
    if ((locks[f] ?? false) && old.containsKey(f)) out[f] = old[f];
  }
  return out;
}

/// 되돌리기 / 다시 하기. 워크스페이스에서 한 편집만 기록한다.
class HistoryState {
  final List<List<Json>> undo;
  final List<List<Json>> redo;
  const HistoryState(this.undo, this.redo);
}

class History extends StateNotifier<HistoryState> {
  final Ref ref;
  History(this.ref) : super(const HistoryState([], []));

  List<Json> _now() => [for (final s in ref.read(teamProvider)) Json.from(s.set)];

  /// 편집 직전에 부른다.
  void record() {
    state = HistoryState([...state.undo, _now()].take(60).toList(), const []);
  }

  Future<void> undo() async {
    if (state.undo.isEmpty) return;
    final prev = state.undo.last;
    state = HistoryState(state.undo.sublist(0, state.undo.length - 1), [...state.redo, _now()]);
    await ref.read(teamProvider.notifier).replaceWith(prev);
  }

  Future<void> redo() async {
    if (state.redo.isEmpty) return;
    final next = state.redo.last;
    state = HistoryState([...state.undo, _now()], state.redo.sublist(0, state.redo.length - 1));
    await ref.read(teamProvider.notifier).replaceWith(next);
  }

  void reset() => state = const HistoryState([], []);
}

final historyProvider = StateNotifierProvider<History, HistoryState>((ref) => History(ref));

/// 빠른 분석: 팀이 바뀔 때마다 (정적 계산, 수십 ms). 응답의 revision 이 현재와 다르면 버린다.
final fastAnalysisProvider = FutureProvider<Json?>((ref) async {
  ref.watch(apiContextProvider);
  final team = ref.watch(teamProvider);
  final fmt = ref.watch(formatProvider);
  final rev = ref.watch(teamRevisionProvider);
  if (team.isEmpty) return null;
  final res = await dio.post('/api/workbench/fast', data: {
    'format': fmt,
    'teamRevision': rev,
    'team': [for (final s in team) s.set],
  });
  final body = res.data as Json;
  if (body['teamRevision'] != rev) return null; // 더 새 편집이 있다
  return body;
});

/// 모의전 작업 (교체 검증·매치업 검증·실험). 결과에는 어느 팀 버전의 결과인지가 붙는다.
class JobState {
  final String? id;
  final String state; // idle running done error cancelled
  final Json? progress;
  final Json? result;
  final String? error;
  final int? revision;
  const JobState({this.id, this.state = 'idle', this.progress, this.result, this.error, this.revision});
  bool get running => state == 'running';
}

class JobRunner extends StateNotifier<JobState> {
  JobRunner() : super(const JobState());
  Timer? _timer;

  Future<void> start(String path, Json body, int revision) async {
    await cancel();
    state = JobState(state: 'running', revision: revision, progress: const {'done': 0, 'total': 1, 'note': '시작'});
    try {
      final res = await dio.post(path, data: {...body, 'teamRevision': revision});
      final id = (res.data as Json)['id'] as String;
      state = JobState(id: id, state: 'running', revision: revision, progress: state.progress);
      _timer = Timer.periodic(const Duration(milliseconds: 800), (_) => _poll(id));
    } catch (e) {
      state = JobState(state: 'error', error: apiError(e), revision: revision);
    }
  }

  Future<void> _poll(String id) async {
    if (state.id != id) return;
    try {
      final v = (await dio.get('/api/workbench/job/$id')).data as Json;
      if (state.id != id) return; // 그 사이에 새 작업
      final s = v['state'] as String;
      state = JobState(
          id: id,
          state: s,
          revision: v['teamRevision'] as int?,
          progress: v['progress'] as Json?,
          result: v['result'] as Json?,
          error: v['error'] as String?);
      if (s != 'running') _timer?.cancel();
    } catch (e) {
      _timer?.cancel();
      state = JobState(id: id, state: 'error', error: apiError(e), revision: state.revision);
    }
  }

  Future<void> cancel() async {
    _timer?.cancel();
    final id = state.id;
    if (id != null && state.running) {
      try {
        await dio.post('/api/workbench/job/$id/cancel');
      } catch (_) {}
    }
    state = const JobState();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

final replaceJobProvider = StateNotifierProvider<JobRunner, JobState>((ref) => JobRunner());
final matchupJobProvider = StateNotifierProvider<JobRunner, JobState>((ref) => JobRunner());
final experimentJobProvider = StateNotifierProvider<JobRunner, JobState>((ref) => JobRunner());

String apiError(Object e) {
  try {
    final data = (e as dynamic).response?.data;
    if (data is Map && data['detail'] != null) return '${data['detail']}';
  } catch (_) {}
  return '서버에 연결할 수 없습니다';
}
