import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:champions_meta_lab/api.dart';
import 'package:champions_meta_lab/pages/parties_page.dart';
import 'package:champions_meta_lab/pages/research_page.dart';
import 'package:champions_meta_lab/pages/research_toggle.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _ResearchServer implements HttpClientAdapter {
  final requested = <bool>[];
  bool running = false;
  bool stopping = false;

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? body, Future<void>? cancel) async {
    expect(options.path, '/api/research/control');
    if (options.method == 'POST') {
      running = options.data['running'] as bool;
      requested.add(running);
      stopping = !running;
    }
    return ResponseBody.fromString(jsonEncode({'running': running, 'stopping': stopping}), 200,
        headers: {Headers.contentTypeHeader: ['application/json']});
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  testWidgets('자동 연구 스위치는 서버 상태를 표시하고 중지 중에는 재시작하지 않는다', (tester) async {
    final server = _ResearchServer();
    final previous = dio.httpClientAdapter;
    dio.httpClientAdapter = server;
    addTearDown(() => dio.httpClientAdapter = previous);
    await tester.pumpWidget(const ProviderScope(child: MaterialApp(home: Scaffold(body: ResearchToggle()))));
    await tester.pumpAndSettle();

    final toggle = find.byType(SwitchListTile);
    expect(tester.widget<SwitchListTile>(toggle).value, false);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(tester.widget<SwitchListTile>(toggle).value, true);
    await tester.tap(toggle);
    await tester.pumpAndSettle();
    expect(find.text('진행 중인 연구를 멈추는 중입니다.'), findsOneWidget);
    expect(tester.widget<SwitchListTile>(toggle).onChanged, isNull);
    expect(server.requested, [true, false]);

    server.stopping = false;
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(tester.widget<SwitchListTile>(toggle).value, false);
    expect(tester.widget<SwitchListTile>(toggle).onChanged, isNotNull);
  });

  testWidgets('자동 연구: 상태와 발견한 팀을 그린다', (tester) async {
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
                    status: data['status'] as Map<String, dynamic>, onControl: ({intensity}) async {}),
                for (final t in (data['teams'] as List).cast<Map<String, dynamic>>()) PartyCard(party: t),
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
