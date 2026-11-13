import 'dart:convert';
import 'dart:io';

import 'package:champions_meta_lab/pages/parties_page.dart';
import 'package:champions_meta_lab/pages/party_simulation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('팀 자동 구성 결과: 비교표, 세트 최적화, 랭커 전적을 그린다', (tester) async {
    final data = jsonDecode(File('test/fixtures/auto_team.json').readAsStringSync()) as Map<String, dynamic>;
    final candidates = (data['candidates'] as List).cast<Map<String, dynamic>>();
    (data['evaluation'] as Map<String, dynamic>)['rosterSearch'] = {
      'rounds': 2, 'tested': 12, 'accepted': 1,
    };
    final members = (candidates.first['members'] as List).cast<Map<String, dynamic>>();
    candidates.first['rosterSearch'] = [
      {
        'strategy': '순풍',
        'threats': [members[0]],
        'swaps': [{'out': members[1], 'in': members[2]}],
        'before': {'wins': 8, 'runs': 21, 'strategyWins': 1, 'strategyRuns': 3},
        'after': {'wins': 12, 'runs': 21, 'strategyWins': 2, 'strategyRuns': 3},
      },
    ];
    final errors = <String>[];
    final previous = FlutterError.onError;
    FlutterError.onError = (details) => errors.add(details.toString());
    addTearDown(() {
      FlutterError.onError = previous;
      tester.view.reset();
    });
    for (final width in [1280.0, 390.0]) {
      tester.view.physicalSize = Size(width, 3000);
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: Column(children: [
                PartyEvaluationSummary(data['evaluation'] as Map<String, dynamic>, candidates: candidates),
                for (final c in candidates) PartyCard(party: c),
              ]),
            ),
          ),
        ),
      ));
      await tester.pump();
      expect(find.text('세트 최적화'), findsWidgets);
      expect(find.textContaining('12개 조합'), findsOneWidget);
      expect(find.text('독창성 (랭커 팀과 얼마나 다른가)'), findsOneWidget);
      expect(find.textContaining('선출만 변경 · +16.7%p'), findsOneWidget);
      final swaps = find.text('포켓몬 교체 내역');
      await tester.ensureVisible(swaps);
      await tester.tap(swaps);
      await tester.pumpAndSettle();
      expect(find.text('교체 확인전 · 8승/21판 → 12승/21판'), findsOneWidget);
      await tester.tap(swaps);
      await tester.pumpAndSettle();
    }
    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: errors.join('\n\n'));
  });
}
