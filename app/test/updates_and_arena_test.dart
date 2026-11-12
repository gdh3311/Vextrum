import 'package:champions_meta_lab/arena_ui.dart';
import 'package:champions_meta_lab/main.dart';
import 'package:champions_meta_lab/settings.dart' show appVersion;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _app() => const ProviderScope(
      child: MaterialApp(
        home: Shell(
          location: '/',
          child: ArenaHero(title: '더블배틀 메타', subtitle: '랭킹 시즌 M7'),
        ),
      ),
    );

void main() {
  testWidgets('경기장을 바꿔도 메타 정보와 탐색 버튼은 보인다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(_app());
    await tester.pumpAndSettle();
    expect(find.text('야간 스타디움'), findsOneWidget);

    await tester.tap(find.byTooltip('다음 경기장'));
    await tester.pumpAndSettle();
    expect(find.text('빗속 스타디움'), findsOneWidget);
    await tester.tap(find.byTooltip('다음 경기장'));
    await tester.pumpAndSettle();
    expect(find.text('결승전 스타디움'), findsOneWidget);
    await tester.tap(find.byTooltip('다음 경기장'));
    await tester.pumpAndSettle();
    expect(find.text('야간 스타디움'), findsOneWidget);
    expect(find.text('랭킹 시즌 M7'), findsOneWidget);
    expect(find.text('실전 상대 분석'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('좁은 화면에서 업데이트를 읽고 확인 상태를 저장한다', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 640);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(_app());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('새 업데이트 보기'));
    await tester.pumpAndSettle();
    expect(find.text('업데이트 내역'), findsOneWidget);
    expect(find.text('더 잘 만드는 팀 자동 구성'), findsOneWidget);
    await tester.tap(find.byTooltip('닫기'));
    await tester.pumpAndSettle();

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('last_read_app_update'), appVersion);
    expect(find.byTooltip('업데이트 내역'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
