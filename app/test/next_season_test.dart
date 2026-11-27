import 'package:champions_meta_lab/api.dart';
import 'package:champions_meta_lab/pages/next_season_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('버전 비교', () {
    expect(newerVersion('1.23.0', '1.22.0'), isTrue);
    expect(newerVersion('1.22.0', '1.22.0'), isFalse);
    expect(newerVersion('1.9.0', '1.22.0'), isFalse);
    expect(newerVersion(null, '1.22.0'), isFalse);
  });

  testWidgets('다음 시즌 화면: 변경·새 포켓몬·내 팀 영향을 보여 준다', (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    addTearDown(tester.view.resetPhysicalSize);
    final mon = {'id': 'garchomp', 'name': 'Garchomp', 'ko': '한카리아스', 'sprite': 'Garchomp', 'rank': 3, 'pct': 64.2};
    await tester.pumpWidget(ProviderScope(
      overrides: [
        nextSeasonProvider.overrideWith((ref) async => {
              'available': true,
              'at': '2026-12-02T02:01:00+00:00',
              'regulation': 'M-D',
              'changes': [
                {'at': '2026-12-02T02:00:00+00:00', 'kind': 'balance', 'title': '12월 2일 밸런스', 'url': 'u',
                 'estimated': true, 'details': ['기술 · 스톤샤워: 명중률 90%→95%']},
              ],
              'balance': {
                'moves': [
                  {'move': 'Rock Slide', 'ko': '스톤샤워', 'users': [mon],
                   'changes': [{'field': 'accuracy', 'label': '명중률', 'before': 90, 'after': 95}]},
                ],
                'learn': const [],
                'abilities': const [],
              },
              'newcomers': [
                {'id': 'heatran', 'name': 'Heatran', 'ko': '히드런', 'sprite': 'sd-heatran', 'provisional': true,
                 'mega': null, 'types': ['Fire', 'Steel'], 'speed': 97, 'ability': 'Flash Fire', 'average': 57.4,
                 'beats': [mon], 'threats': [mon]},
              ],
              'team': {
                'members': [{...mon, 'notes': ['스톤샤워: 명중률 90→95']}],
                'newcomers': [
                  {'id': 'heatran', 'ko': '히드런', 'sprite': 'sd-heatran', 'covered': false,
                   'best': {'ko': '한카리아스', 'score': 50.0}, 'answers': const []},
                ],
              },
              'note': '추정입니다',
            }),
      ],
      child: const MaterialApp(home: Scaffold(body: NextSeasonPage())),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('다음 시즌 미리보기'), findsOneWidget);
    expect(find.text('다음 시즌 규칙으로 팀 자동 구성'), findsOneWidget);
    expect(find.text('히드런'), findsWidgets);
    expect(find.textContaining('스톤샤워: 명중률 90→95'), findsWidgets);
    expect(find.textContaining('확실한 대응 포켓몬이 없음'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
