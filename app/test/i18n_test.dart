import 'package:champions_meta_lab/i18n.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() => currentLang = 'ko');

  test('한국어는 그대로 둔다', () {
    currentLang = 'ko';
    expect(tr('팀 빌더'), '팀 빌더');
  });

  test('정확히 일치하는 문구와 보간 템플릿을 번역한다', () {
    currentLang = 'en';
    expect(tr('팀 빌더'), 'Team Builder');
    expect(tr('12위'), '#12');
    expect(tr('3승 2패 1무 · 승률 50%'), '3W 2L 1D · win rate 50%');
    currentLang = 'ja';
    expect(tr('107위 → 47위'), '107位 → 47位');
    expect(tr('불꽃'), 'ほのお');
  });

  test('숫자 단위 템플릿은 숫자에만 걸린다', () {
    currentLang = 'en';
    expect(tr('사전에 없는 문장입니다 위'), '사전에 없는 문장입니다 위');
  });
}
