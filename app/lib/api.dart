import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

typedef Json = Map<String, dynamic>;

/// API 주소. `--dart-define=API_BASE=http://10.0.2.2:8000` 으로 바꿀 수 있다.
/// 웹에서 백엔드가 직접 앱을 서빙하는 경우(같은 출처)에는 그 주소를 그대로 쓴다.
String get apiBase {
  const fromEnv = String.fromEnvironment('API_BASE');
  if (fromEnv.isNotEmpty) return fromEnv;
  if (kIsWeb && Uri.base.port == 8000) return Uri.base.origin;
  return 'http://localhost:8000';
}

final dio = Dio(BaseOptions(baseUrl: apiBase, connectTimeout: const Duration(seconds: 10)));

String spriteUrl(String name) => '$apiBase/img/pokemon/${Uri.encodeComponent(name)}';
String itemUrl(String name) => '$apiBase/img/item/${Uri.encodeComponent(name)}';

/// 현재 포맷: Doubles(기본) / Singles
final formatProvider = StateProvider<String>((ref) => 'Doubles');

final infoProvider = FutureProvider<Json>((ref) async => (await dio.get('/api/info')).data as Json);

final metaProvider = FutureProvider<Json>((ref) async {
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/meta', queryParameters: {'format': fmt, 'top': 300})).data as Json;
});

final pokemonListProvider = FutureProvider<List<Json>>(
    (ref) async => ((await dio.get('/api/pokemon')).data as List).cast<Json>());

final itemsProvider =
    FutureProvider<List<Json>>((ref) async => ((await dio.get('/api/items')).data as List).cast<Json>());

final pokemonDetailProvider = FutureProvider.family<Json, String>((ref, id) async {
  final fmt = ref.watch(formatProvider);
  return (await dio.get('/api/pokemon/$id', queryParameters: {'format': fmt})).data as Json;
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
  bool operator ==(Object o) =>
      o is JokerFilter && o.minRank == minRank && o.topN == topN && o.role == role && o.type == type;
  @override
  int get hashCode => Object.hash(minRank, topN, role, type);
}

final jokerFilterProvider = StateProvider<JokerFilter>((ref) => const JokerFilter());

final jokersProvider = FutureProvider<Json>((ref) async {
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
