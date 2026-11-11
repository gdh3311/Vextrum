import 'package:champions_meta_lab/pages/battle_arena.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('받침에 맞는 조사를 고른다', () {
    expect(josa('한카리아스', '은', '는'), '는');
    expect(josa('대도각참', '은', '는'), '은');
    expect(josa('드래펀트', '은', '는'), '는');
    expect(josa('엘풍', '이', '가'), '이');
  });

  test('괄호로 끝나는 폼 이름은 괄호 앞 이름을 기준으로 한다', () {
    expect(josa('대쓰여너 (수컷)', '은', '는'), '는');
    expect(josa('로토무 (워시)', '을', '를'), '를');
  });

  test('한글이 아닌 이름은 받침 없는 조사', () {
    expect(josa('Garchomp', '은', '는'), '는');
  });
}
