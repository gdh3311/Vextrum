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
}

class TeamNotifier extends StateNotifier<List<TeamSlot>> {
  final Ref ref;
  TeamNotifier(this.ref) : super(const []) {
    _load();
  }

  static const _key = 'team_v1';

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_key);
      if (raw == null) return;
      final sets = (jsonDecode(raw) as List).cast<Json>();
      final fmt = ref.read(formatProvider);
      final slots = <TeamSlot>[];
      for (final s in sets) {
        slots.add(TeamSlot(s, await fetchDetail(s['id'] as String, fmt)));
      }
      if (state.isEmpty) state = slots;
    } catch (_) {/* 저장된 팀을 못 읽으면 빈 팀으로 시작 */}
  }

  Future<void> _save() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, jsonEncode([for (final s in state) s.set]));
    } catch (_) {}
  }

  bool get isFull => state.length >= 6;

  /// 가장 많이 쓰이는 세트로 추가한다. [set] 을 주면 그 세트로 추가(조커/교체 추천).
  Future<void> add(String id, {Json? set, int? replaceAt}) async {
    final detail = await fetchDetail(id, ref.read(formatProvider));
    final slot = TeamSlot(Json.from(set ?? detail['defaultSet'] as Json), detail);
    final next = [...state];
    if (replaceAt != null && replaceAt < next.length) {
      next[replaceAt] = slot;
    } else if (next.length < 6) {
      next.add(slot);
    } else {
      return;
    }
    state = next;
    _save();
  }

  void update(int i, Json set) {
    state = [
      for (var k = 0; k < state.length; k++) k == i ? state[k].withSet(set) : state[k]
    ];
    _save();
  }

  void removeAt(int i) {
    state = [
      for (var k = 0; k < state.length; k++)
        if (k != i) state[k]
    ];
    _save();
  }

  void clear() {
    state = const [];
    _save();
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
