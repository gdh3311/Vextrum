import 'package:champions_meta_lab/pages/calc_common.dart';
import 'package:champions_meta_lab/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('성격 표: 올라가는 능력 × 내려가는 능력 → 성격 이름, 대각선은 보정 없음', () {
    expect(natureFor('spe', 'atk'), 'Timid');
    expect(natureFor('atk', 'spa'), 'Adamant');
    expect(natureFor('spd', 'spe'), 'Sassy');
    expect(natureEffects[natureFor('def', 'def')], [null, null]);
    // 25칸이 서로 다른 성격 25개
    const stats = ['atk', 'def', 'spa', 'spd', 'spe'];
    expect({for (final a in stats) for (final b in stats) natureFor(a, b)}.length, 25);
  });

  test('스피드 계산: 배틀 엔진과 같은 순서로 내림', () {
    expect(speedOf(base: 100, points: 32, nature: 1), 145); // (100+32)×1.1 = 145.2
    expect(speedOf(base: 100, points: 32, nature: 1, scarf: true), 217);
    expect(speedOf(base: 100, points: 0, nature: 0, tailwind: true), 200);
    expect(speedOf(base: 100, points: 0, nature: -1, stage: -1), 60); // 90 × 2/3
    expect(speedOf(base: 81, points: 0, nature: 0, paralysis: true), 40);
    expect(stageMultiplier(2), 2);
    expect(stageMultiplier(-2), .5);
  });

  test('종족값: 레벨 50 실수치에서 되돌린다 (어흥염 95/115)', () {
    expect(speciesBase('hp', 170), 95);
    expect(speciesBase('atk', 135), 115);
  });
}
