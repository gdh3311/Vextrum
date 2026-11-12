import 'dart:convert';
import 'dart:io';

import 'package:champions_meta_lab/pages/party_lab.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('추천 연구소 결과: 순위표, 조커 비교, 랭커 파티 전적을 그린다', (tester) async {
    final data = jsonDecode(File('test/fixtures/party_lab.json').readAsStringSync()) as Map<String, dynamic>;
    final errors = <String>[];
    final previous = FlutterError.onError;
    FlutterError.onError = (details) => errors.add(details.toString());
    addTearDown(() {
      FlutterError.onError = previous;
      tester.view.reset();
    });
    for (final width in [1280.0, 390.0]) {
      tester.view.physicalSize = Size(width, 2400);
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(ProviderScope(
        child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: PartyLabResults(data)))),
      ));
      await tester.pump();
      expect(find.text('추천 순위'), findsOneWidget);
      expect(find.byType(RankerMatchups), findsWidgets);
    }
    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: errors.join('\n\n'));
  });
}
