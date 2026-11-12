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
    }
    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: errors.join('\n\n'));
  });
}
