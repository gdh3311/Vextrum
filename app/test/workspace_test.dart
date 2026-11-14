import 'dart:convert';
import 'dart:typed_data';

import 'package:champions_meta_lab/api.dart';
import 'package:champions_meta_lab/pages/workspace_page.dart';
import 'package:champions_meta_lab/team_state.dart';
import 'package:champions_meta_lab/workspace_state.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 서버 흉내: 포켓몬 상세와 빠른 분석. 빠른 분석은 요청마다 늦게 응답할 수 있다.
class _FakeServer implements HttpClientAdapter {
  final fastCalls = <int>[];
  Duration Function(int revision) delay = (_) => Duration.zero;

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) async {
    Object out;
    if (o.path.startsWith('/api/pokemon/')) {
      final id = o.path.split('/').last.split('?').first;
      out = {
        'id': id,
        'name': id,
        'ko': id,
        'sprite': id,
        'megas': [],
        'defaultSet': {'id': id, 'moves': ['Protect'], 'item': null},
      };
    } else if (o.path == '/api/workbench/fast') {
      final rev = (o.data as Map)['teamRevision'] as int;
      fastCalls.add(rev);
      await Future<void>.delayed(delay(rev));
      out = {
        'teamRevision': rev,
        'basis': 'static',
        'elapsedMs': 1,
        'hashes': {'speed': '$rev'},
        'members': [],
        'sections': {
          'legality': [],
          'strategy': {'tags': [], 'issues': []},
          'speed': {'order': [], 'control': [], 'priority': []},
          'types': {'warnings': [], 'rows': []},
          'balance': {'physical': 50, 'special': 50},
          'roles': [],
          'meta': {'matchups': []},
          'lead': null,
          'mega': [],
        },
      };
    } else {
      out = {};
    }
    return ResponseBody.fromString(jsonEncode(out), 200, headers: {
      Headers.contentTypeHeader: ['application/json'],
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  test('잠긴 포켓몬·항목은 추천 세트를 적용해도 바뀌지 않는다', () {
    final old = {'id': 'garchomp', 'item': 'Choice Scarf', 'moves': ['Earthquake']};
    final proposed = {'id': 'garchomp', 'item': 'Life Orb', 'moves': ['Dragon Claw']};
    final kept = applyLocks(old, proposed, {'item': true});
    expect(kept['item'], 'Choice Scarf');
    expect(kept['moves'], ['Dragon Claw']);
    expect(() => applyLocks(old, {'id': 'kingambit'}, {'pokemon': true}), throwsStateError);
    expect(applyLocks(old, {'id': 'kingambit'}, {'item': true})['id'], 'kingambit');
  });

  test('팀 버전 번호는 구성이 같으면 같고, 바뀌면 달라진다', () {
    final a = [
      {'id': 'garchomp', 'item': 'Choice Scarf'}
    ];
    final b = [
      {'id': 'garchomp', 'item': 'Life Orb'}
    ];
    expect(teamRevisionOf(a), teamRevisionOf([Map<String, dynamic>.from(a.first)]));
    expect(teamRevisionOf(a), isNot(teamRevisionOf(b)));
  });

  testWidgets('이전 버전의 결과에는 경고가 붙는다', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: Builder(builder: (c) => Column(children: [staleBanner(c, 1, 2), staleBanner(c, 2, 2)]))),
    ));
    expect(find.text('이 결과는 이전 버전 팀의 것입니다. 지금 팀으로 다시 실행하세요.'), findsOneWidget);
  });

  test('빠르게 여러 번 고쳐도 마지막 버전의 분석만 남는다', () async {
    SharedPreferences.setMockInitialValues({});
    final server = _FakeServer();
    dio.httpClientAdapter = server;
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final team = container.read(teamProvider.notifier);
    await Future<void>.delayed(const Duration(milliseconds: 50));
    await team.add('garchomp');
    // 첫 분석은 늦게, 두 번째는 빨리 응답 → 늦게 온 옛 결과가 새 결과를 덮으면 안 된다
    final firstRev = container.read(teamRevisionProvider);
    server.delay = (rev) => rev == firstRev ? const Duration(milliseconds: 300) : Duration.zero;
    final sub = container.listen(fastAnalysisProvider, (_, __) {});
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await team.add('kingambit');
    final lastRev = container.read(teamRevisionProvider);
    expect(lastRev, isNot(firstRev));
    await Future<void>.delayed(const Duration(milliseconds: 500));
    final value = container.read(fastAnalysisProvider).valueOrNull;
    expect(value?['teamRevision'], lastRev);
    sub.close();
  });

  testWidgets('워크스페이스는 넓은 화면·좁은 화면 모두 오류 없이 그린다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    dio.httpClientAdapter = _FakeServer();
    addTearDown(tester.view.reset);
    for (final width in [1400.0, 390.0]) {
      tester.view.physicalSize = Size(width, 2400);
      tester.view.devicePixelRatio = 1;
      final container = ProviderContainer();
      await tester.runAsync(() async {
        await Future<void>.delayed(const Duration(milliseconds: 50));
        await container.read(teamProvider.notifier).add('garchomp');
        await container.read(teamProvider.notifier).add('kingambit');
      });
      await tester.pumpWidget(UncontrolledProviderScope(
          container: container, child: const MaterialApp(home: Scaffold(body: WorkspacePage()))));
      for (var k = 0; k < 3; k++) {
        // 분석 요청은 화면이 처음 그려질 때 시작된다
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(tester.takeException(), isNull);
      expect(find.text('팀 워크스페이스'), findsOneWidget);
      expect(find.text('현재 팀'), findsOneWidget);
      expect(find.textContaining('교체 추천'), findsWidgets);
      expect(find.textContaining('정적 분석'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      container.dispose();
    }
  });
}
