import 'package:champions_meta_lab/arena_ui.dart';
import 'package:champions_meta_lab/api.dart';
import 'package:champions_meta_lab/main.dart';
import 'package:champions_meta_lab/pages/settings_page.dart';
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
    expect(find.text('앱 안에서 업데이트'), findsOneWidget);
    await tester.tap(find.byTooltip('닫기'));
    await tester.pumpAndSettle();

    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('last_read_app_update'), appVersion);
    expect(find.byTooltip('업데이트 내역'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('규칙 확인이 필요할 때만 설정에 알림을 표시한다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    Widget settings({required bool needsReview}) => ProviderScope(
          key: ValueKey(needsReview),
          overrides: [
            dataSyncProvider.overrideWith((ref) async => {
                  'regulation': 'M-D',
                  'ruleAlerts': [
                    if (needsReview)
                      {
                        'title': '참가 목록 확인 필요',
                        'text': '공식 참가 목록을 다시 확인하는 중입니다.',
                        'url': 'https://champions-news.pokemon-home.com/ko/page/878.html',
                      },
                  ],
                }),
            infoProvider.overrideWith((ref) async => {'generatedAt': '2026-11-25T04:00:00Z'}),
          ],
          child: const MaterialApp(home: Shell(location: '/settings', child: SettingsPage())),
        );

    await tester.pumpWidget(settings(needsReview: true));
    await tester.pumpAndSettle();
    expect(find.byTooltip('설정 · 배틀 규칙 확인 필요'), findsOneWidget);
    expect(find.text('배틀 규칙 알림'), findsOneWidget);
    expect(find.text('참가 목록 확인 필요'), findsOneWidget);
    expect(find.byTooltip('공식 공지 링크 복사'), findsOneWidget);

    await tester.pumpWidget(settings(needsReview: false));
    await tester.pumpAndSettle();
    expect(find.byTooltip('설정'), findsOneWidget);
    expect(find.text('배틀 규칙 알림'), findsNothing);
  });

  testWidgets('자동으로 반영한 내용은 배지 없이 설정에 보인다', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(ProviderScope(
      overrides: [
        dataSyncProvider.overrideWith((ref) async => {
              'regulation': 'M-D',
              'ruleAlerts': const [],
              'ruleNotes': [
                {'title': '밸런스 조정 적용 예정', 'text': '12월 02일 11:00 (한국 시간) 예상', 'url': 'https://example.com'},
              ],
            }),
        infoProvider.overrideWith((ref) async => {'generatedAt': '2026-11-25T04:00:00Z'}),
      ],
      child: const MaterialApp(home: Shell(location: '/settings', child: SettingsPage())),
    ));
    await tester.pumpAndSettle();
    expect(find.byTooltip('설정'), findsOneWidget); // 배지 없음
    expect(find.text('시즌·규정 자동 반영'), findsOneWidget);
    expect(find.text('밸런스 조정 적용 예정'), findsOneWidget);
  });
}
