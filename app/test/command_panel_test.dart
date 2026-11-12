import 'package:champions_meta_lab/pages/battle_arena.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _mon(String id) =>
    {'id': id, 'name': id, 'ko': id, 'sprite': '', 'types': ['Normal'], 'hp': 100, 'maxHp': 100};

void main() {
  testWidgets('숫자 키로 기술과 대상을 고르고 상성 표시가 붙는다', (tester) async {
    final picked = <Map<String, dynamic>?>[];
    final options = [
      {'kind': 'move', 'slot': 0, 'move': 'Tackle', 'label': '몸통박치기', 'type': 'Normal', 'target': 0, 'eff': 1},
      {'kind': 'move', 'slot': 0, 'move': 'Tackle', 'label': '몸통박치기', 'type': 'Normal', 'target': 1, 'eff': 1},
      {'kind': 'move', 'slot': 0, 'move': 'Close Combat', 'label': '인파이트', 'type': 'Fighting', 'target': 0, 'eff': 2},
      {'kind': 'move', 'slot': 0, 'move': 'Close Combat', 'label': '인파이트', 'type': 'Fighting', 'target': 1, 'eff': 0},
      {'kind': 'move', 'slot': 0, 'move': 'Protect', 'label': '방어', 'type': 'Normal'},
    ];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) => GameCommandPanel(
            mon: _mon('me'),
            options: options,
            selected: picked.isEmpty ? null : picked.last,
            foes: {0: _mon('a'), 1: _mon('b')},
            team: [_mon('me')],
            reserved: const {},
            onSelected: (a) => setState(() => picked.add(a)),
          ),
        ),
      ),
    ));
    expect(find.text('효과 굉장'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.digit3);
    await tester.pump();
    expect(picked.last?['move'], 'Protect');

    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.pump();
    expect(find.textContaining('대상 선택'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.pump();
    expect(picked.last?['move'], 'Close Combat');
    expect(picked.last?['target'], 1);
  });
}
