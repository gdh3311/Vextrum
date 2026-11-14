import 'dart:convert';
import 'dart:typed_data';

import 'package:champions_meta_lab/api.dart';
import 'package:champions_meta_lab/pages/match_journal.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _PredictionServer implements HttpClientAdapter {
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? body, Future<void>? cancel) async {
    expect(options.path, '/api/workbench/matchup/prediction');
    return ResponseBody.fromString(jsonEncode({
      'at': 123,
      'season': 'M8',
      'lead': ['a', 'b'],
      'back': ['c', 'd'],
      'simulation': {'rate': .5, 'games': 18},
    }), 200, headers: {
      Headers.contentTypeHeader: ['application/json'],
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  testWidgets('경기 전 예측을 보관하고 화면에서 고정한 선출과 별도로 실제 선택을 기록한다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final old = dio.httpClientAdapter;
    dio.httpClientAdapter = _PredictionServer();
    addTearDown(() => dio.httpClientAdapter = old);
    tester.view.physicalSize = const Size(900, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final team = [
      for (final id in ['a', 'b', 'c', 'd', 'e', 'f'])
        <String, dynamic>{'id': id, 'name': '내 $id', 'moves': ['Protect']},
    ];
    final foe = [
      for (final id in ['u', 'v', 'w', 'x', 'y', 'z'])
        <String, dynamic>{'id': id, 'name': '상대 $id'},
    ];
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(home: Scaffold(body: MatchJournalPanel(
        format: 'Doubles', teamName: '예시 팀', team: team, teamMembers: team,
        enemy: foe, confirmed: const [], locked: const ['a', 'b', 'c', 'd'],
      ))),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('경기 전 예측 저장'));
    await tester.pumpAndSettle();
    expect(find.text('저장한 선봉 내 a + 내 b · 후발 내 c + 내 d'), findsOneWidget);
    await tester.tap(find.text('이번 경기 기록'));
    await tester.pumpAndSettle();
    expect(tester.widgetList<FilterChip>(find.byType(FilterChip)).where((chip) => chip.selected), isEmpty);

    await tester.tap(find.text('화면에서 고른 선출을 실제 선출로 입력'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('첫 턴에 선택한 기술·교체 (선택)'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(DropdownButtonFormField<String>).first);
    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Protect').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('패배'));
    await tester.tap(find.text('패배'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('저장'));
    await tester.pumpAndSettle();

    final record = container.read(matchJournalProvider).requireValue.single;
    expect(record['myLead'], ['a', 'b']);
    expect(record['myBack'], ['c', 'd']);
    expect(record['opening'], {'a': 'Protect'});
    expect(record['prediction']['at'], 123);
    expect(record['outcome'], 'loss');
    expect(find.text('경기 전 예측 저장'), findsOneWidget);
  });
}
