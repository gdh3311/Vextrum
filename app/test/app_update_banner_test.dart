import 'package:champions_meta_lab/app_updates.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Widget _wrap(Map<String, dynamic> next) =>
    MaterialApp(home: Scaffold(body: NewVersionBanner(next: next)));

void main() {
  testWidgets('배포판이 아니면 다운로드 페이지 링크만 보인다', (tester) async {
    await tester.pumpWidget(_wrap({'version': '9.0.0', 'url': 'https://example.com/r', 'inApp': false}));
    expect(find.text('새 버전 v9.0.0가 나왔습니다'), findsOneWidget);
    expect(find.text('https://example.com/r'), findsOneWidget);
    expect(find.text('업데이트'), findsNothing);
  });

  testWidgets('배포판이면 앱 안 업데이트 버튼을 보인다', (tester) async {
    await tester.pumpWidget(_wrap({'version': '9.0.0', 'url': 'https://example.com/r', 'inApp': true}));
    await tester.pump();
    expect(find.text('업데이트'), findsOneWidget);
    expect(find.textContaining('바뀐 파일만 받아 적용합니다'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 15)); // 서버 확인 요청의 시간 제한 타이머
  });
}
