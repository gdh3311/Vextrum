import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'settings.dart';

typedef Json = Map<String, dynamic>;

String pokemonPath(String id, [String? season]) =>
    Uri(path: '/pokemon/$id', queryParameters: season == null ? null : {'season': season}).toString();

/// 기본 API 주소. `--dart-define=API_BASE=http://10.0.2.2:8000` 으로 바꿀 수 있다.
/// 웹에서 백엔드가 직접 앱을 서빙하는 경우(같은 출처)에는 그 주소를 그대로 쓴다.
/// 설정 화면에서 다른 주소를 넣으면 그쪽이 우선한다.
String get defaultApiBase {
  const fromEnv = String.fromEnvironment('API_BASE');
  if (fromEnv.isNotEmpty) return fromEnv;
  if (kIsWeb && (kReleaseMode || Uri.base.port == 8000)) return Uri.base.origin;
  return 'http://localhost:8000';
}

String? _apiOverride;
String get apiBase => _apiOverride ?? defaultApiBase;

final dio = Dio(BaseOptions(baseUrl: defaultApiBase, connectTimeout: const Duration(seconds: 10)));

/// 서버 주소와 응답 언어(X-Lang: 포켓몬·기술·도구 이름을 그 언어로 받는다)를 정한다.
void configureApi({String? base, required String lang}) {
  final b = base?.trim();
  _apiOverride = (b == null || b.isEmpty) ? null : b.replaceAll(RegExp(r'/+$'), '');
  dio.options.baseUrl = apiBase;
  dio.options.headers['X-Lang'] = lang;
}

String spriteUrl(String name) => '$apiBase/img/pokemon/${Uri.encodeComponent(name)}';
String itemUrl(String name) => '$apiBase/img/item/${Uri.encodeComponent(name)}';

/// 현재 포맷: Doubles(기본) / Singles
final formatProvider = StateProvider<String>((ref) => 'Doubles');

final infoProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  return (await dio.get('/api/info')).data as Json;
});

final metaSeasonProvider = StateProvider<String?>((ref) => null);

final seasonMetaProvider = FutureProvider.family<Json, String?>((ref, season) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/meta',
          queryParameters: {'format': fmt, 'top': 300, if (season != null) 'season': season}))
      .data as Json;
});

final metaProvider = seasonMetaProvider(null);

final pokemonListProvider = FutureProvider<List<Json>>((ref) async {
  ref.watch(apiContextProvider);
  return ((await dio.get('/api/pokemon')).data as List).cast<Json>();
});

final itemsProvider = FutureProvider<List<Json>>((ref) async {
  ref.watch(apiContextProvider);
  return ((await dio.get('/api/items')).data as List).cast<Json>();
});

final pokemonDetailProvider = FutureProvider.family<Json, String>((ref, id) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/pokemon/$id', queryParameters: {'format': fmt})).data as Json;
});

final seasonDetailProvider = FutureProvider.autoDispose.family<Json, (String, String)>((ref, key) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/pokemon/${key.$1}', queryParameters: {'format': fmt, 'season': key.$2})).data as Json;
});

final partiesProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/parties', queryParameters: {'format': fmt})).data as Json;
});

final simulatedPartiesProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  final format = ref.watch(formatProvider);
  return (await dio.get('/api/parties/simulated', queryParameters: {'format': format})).data as Json;
});

class JokerFilter {
  final int minRank;
  final int topN;
  final String? role;
  final String? type;
  const JokerFilter({this.minRank = 50, this.topN = 20, this.role, this.type});
  JokerFilter copyWith({int? minRank, int? topN, String? Function()? role, String? Function()? type}) => JokerFilter(
      minRank: minRank ?? this.minRank,
      topN: topN ?? this.topN,
      role: role != null ? role() : this.role,
      type: type != null ? type() : this.type);
  @override
  bool operator ==(Object other) =>
      other is JokerFilter && other.minRank == minRank && other.topN == topN && other.role == role && other.type == type;
  @override
  int get hashCode => Object.hash(minRank, topN, role, type);
}

final jokerFilterProvider = StateProvider<JokerFilter>((ref) => const JokerFilter());

final jokersProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  final f = ref.watch(jokerFilterProvider);
  return (await dio.get('/api/jokers', queryParameters: {
    'format': fmt,
    'minRank': f.minRank,
    'topN': f.topN,
    if (f.role != null) 'role': f.role,
    if (f.type != null) 'type': f.type,
  }))
      .data as Json;
});

Future<Json> fetchDetail(String id, String fmt) async =>
    (await dio.get('/api/pokemon/$id', queryParameters: {'format': fmt})).data as Json;

/// 연구실: (포켓몬 id, 세트 JSON 문자열, 기준 메타 수) → 상성표·파트너·운용법
final labProvider = FutureProvider.family<Json, (String, String, int)>((ref, k) async {
  ref.watch(apiContextProvider);
  final fmt = ref.watch(formatProvider);
  return (await dio.post('/api/lab', data: {'format': fmt, 'id': k.$1, 'set': jsonDecode(k.$2), 'topN': k.$3})).data
      as Json;
});

Future<Json> fetchDuel(String fmt, Json me, Json foe) async =>
    (await dio.post('/api/duel', data: {'format': fmt, 'me': me, 'foe': foe})).data as Json;
