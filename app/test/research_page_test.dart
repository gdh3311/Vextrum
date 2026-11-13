import 'dart:convert';
import 'dart:io';

import 'package:champions_meta_lab/pages/parties_page.dart';
import 'package:champions_meta_lab/pages/research_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('자동 연구: 상태, 발견한 팀, 배운 조합을 그린다', (tester) async {
    final data = jsonDecode(File('test/fixtures/research.json').readAsStringSync()) as Map<String, dynamic>;
    final errors = <String>[];
    final previous = FlutterError.onError;
    FlutterError.onError = (details) => errors.add(details.toString());
    addTearDown(() {
      FlutterError.onError = previous;
      tester.view.reset();
    });
    for (final width in [1280.0, 380.0]) {
      tester.view.physicalSize = Size(width, 3200);
      tester.view.devicePixelRatio = 1;
      await tester.pumpWidget(ProviderScope(
        child: MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: Column(children: [
                ResearchStatusCard(
                    status: data['status'] as Map<String, dynamic>, onControl: ({running, intensity}) async {}),
                for (final t in (data['teams'] as List).cast<Map<String, dynamic>>()) PartyCard(party: t),
                ResearchInsights(data['insights'] as Map<String, dynamic>),
              ]),
            ),
          ),
        ),
      ));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text('연구 상태'), findsOneWidget);
    }
    await tester.pumpWidget(const SizedBox());
    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: errors.join('\n\n'));
  });
}
