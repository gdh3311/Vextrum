import 'dart:convert';
import 'dart:io';

import 'package:champions_meta_lab/pages/auto_team_result.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _party() {
  final data = jsonDecode(File('test/fixtures/auto_team.json').readAsStringSync()) as Map<String, dynamic>;
  final party = (data['candidates'] as List).first as Map<String, dynamic>;
  party['holdout'] = {'rate': .62, 'runs': 27, 'coreCount': 21, 'strategies': []};
  party['warnings'] = ['쾌청에서 대쓰여너의 주력 기술이 약해집니다.'];
  final first = (party['members'] as List).first as Map<String, dynamic>;
  first['why'] = {
    'summary': '쾌청 시동 · 메타 상위 중 팀에서 가장 잘 상대함',
    'reasons': [
      {'kind': 'role', 'text': '역할 · 쾌청 시동'},
      {'kind': 'sim', 'text': '모의전 선출 100% · 선출 시 승률 75%'},
    ],
    'set': [
      {'part': '도구', 'label': '목탄', 'text': '불꽃 기술 1.2배 · 실전 채용 80%'},
      {'part': '기술', 'label': '분화', 'type': 'Fire', 'text': '자속 주력 (위력 150) · 상대 둘 다 공격'},
    ],
    'source': '실전 사용률 통계의 대표 세트',
  };
  return party;
}

Future<void> _pump(WidgetTester tester, Size size) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(ProviderScope(
    child: MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: AutoTeamCard(party: _party(), index: 0))),
    ),
  ));
  await tester.pump();
}

void main() {
  testWidgets('자동 구성 카드: 핵심 수치, 고른 이유, 포켓몬별 이유와 세트', (tester) async {
    await _pump(tester, const Size(1100, 2400));
    expect(find.text('1안'), findsOneWidget);
    expect(find.text('검증 승점률'), findsOneWidget);
    expect(find.text('이 팀을 고른 이유'), findsOneWidget);
    expect(find.textContaining('대쓰여너의 주력 기술이 약해집니다'), findsOneWidget);
    expect(find.text('쾌청 시동 · 메타 상위 중 팀에서 가장 잘 상대함'), findsOneWidget);
    expect(find.text('뽑은 이유'), findsNothing);

    await tester.tap(find.text('쾌청 시동 · 메타 상위 중 팀에서 가장 잘 상대함'));
    await tester.pump();
    expect(find.text('뽑은 이유'), findsOneWidget);
    expect(find.text('분화'), findsOneWidget);
    expect(find.textContaining('자속 주력 (위력 150)'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('좁은 화면에서도 넘치지 않는다', (tester) async {
    await _pump(tester, const Size(360, 2600));
    await tester.tap(find.text('쾌청 시동 · 메타 상위 중 팀에서 가장 잘 상대함'));
    await tester.pump();
    expect(find.text('목탄'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}
