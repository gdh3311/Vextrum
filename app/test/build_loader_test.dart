import 'dart:convert';
import 'dart:io';

import 'package:champions_meta_lab/pages/build_loader.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('팀 구성 진행 화면: 단계마다 장면과 문구를 그린다', (tester) async {
    final snapshots = (jsonDecode(File('test/fixtures/build_progress.json').readAsStringSync()) as List)
        .cast<Map<String, dynamic>>();
    final errors = <String>[];
    final previous = FlutterError.onError;
    FlutterError.onError = (details) => errors.add(details.toString());
    addTearDown(() {
      FlutterError.onError = previous;
      tester.view.reset();
    });
    for (final width in [1100.0, 360.0]) {
      tester.view.physicalSize = Size(width, 900);
      tester.view.devicePixelRatio = 1;
      for (final p in [null, ...snapshots]) {
        await tester.pumpWidget(MaterialApp(
          home: Scaffold(body: SingleChildScrollView(child: TeamBuildLoader(progress: p, onCancel: () {}))),
        ));
        await tester.pump(const Duration(milliseconds: 700));
        expect(find.byType(TeamBuildLoader), findsOneWidget);
        expect(find.textContaining('모의전'), findsWidgets);
      }
    }
    await tester.pumpWidget(const SizedBox());
    FlutterError.onError = previous;
    expect(errors, isEmpty, reason: errors.join('\n\n'));
  });
}
