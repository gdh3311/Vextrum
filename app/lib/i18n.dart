/// 다국어: 앱 화면의 한국어 문구를 그리는 시점에 현재 언어로 바꾼다.
///
/// - 각 화면 파일은 `material.dart`의 Text/Tooltip 대신 이 파일의 Text/Tooltip을 쓴다
///   (`import 'package:flutter/material.dart' hide Text, Tooltip;`).
/// - 사전(`l10n_data.dart`)의 키는 한국어 원문이고, `{}`는 보간 자리다.
///   예: '{}위' → English '#{}', 日本語 '{}位'. 보간 자리에 들어간 조각도 다시 번역한다.
/// - 사전에 없는 문구는 한국어 그대로 보인다.
library;

import 'package:flutter/material.dart' as m;

import 'l10n_data.dart';

const languages = [('ko', '한국어'), ('en', 'English'), ('ja', '日本語')];

/// 현재 언어. 설정이 바뀌면 앱 전체를 다시 그리므로 전역 값으로 충분하다.
String currentLang = 'ko';

/// 포켓몬 이름 아래 영문 이름을 함께 보일지 (설정: 이름 표시)
bool showEnglishNames = true;

/// 언어를 바꾼 뒤 화면 전체를 다시 그린다. const 위젯은 보통 다시 그려지지 않으므로 모든 요소를 직접 표시한다.
void rebuildAllText() {
  void mark(m.Element e) {
    e.markNeedsBuild();
    e.visitChildren(mark);
  }

  m.WidgetsBinding.instance.addPostFrameCallback((_) => m.WidgetsBinding.instance.rootElement?.visitChildren(mark));
  m.WidgetsBinding.instance.scheduleFrame();
}

final _hangul = RegExp(r'[가-힣]');
final _cache = <String, Map<String, String>>{};
final _exact = <String, Map<String, String>>{};
final _templates = <String, List<(RegExp, String)>>{};

/// 숫자 뒤에 붙는 단위. 이 앞의 보간 자리는 숫자만 받는다 (예: '{}위'가 아무 문장 끝에나 걸리지 않게).
const _counters = ['위', '턴', '마리', '승', '패', '무', '판', '건', '개', '배', '타', '번', '%'];

void _build(String lang) {
  if (_exact.containsKey(lang)) return;
  final idx = lang == 'en' ? 1 : 2;
  final exact = <String, String>{};
  final templates = <(RegExp, String, int)>[];
  for (final row in l10nEntries) {
    final ko = row.$1;
    final target = idx == 1 ? row.$2 : row.$3;
    if (target.isEmpty) continue;
    if (!ko.contains('{}')) {
      exact[ko] = target;
      continue;
    }
    final parts = ko.split('{}');
    final b = StringBuffer('^');
    for (var i = 0; i < parts.length; i++) {
      b.write(RegExp.escape(parts[i]));
      if (i < parts.length - 1) {
        final next = parts[i + 1];
        final numeric = _counters.any(next.startsWith) || next.startsWith('/');
        b.write(numeric ? r'([-+]?\d[\d.,]*)' : r'(.+?)');
      }
    }
    b.write(r'$');
    templates.add((RegExp(b.toString(), dotAll: true), target, ko.replaceAll('{}', '').length));
  }
  // 고정 글자가 많은 템플릿부터 시도한다 (더 구체적인 쪽이 이긴다).
  templates.sort((a, b) => b.$3.compareTo(a.$3));
  _exact[lang] = exact;
  _templates[lang] = [for (final t in templates) (t.$1, t.$2)];
  _cache[lang] = {};
}

/// 한국어 문구를 현재 언어로 바꾼다. 번역이 없으면 원문을 돌려준다.
String tr(String s, [int depth = 0]) {
  final lang = currentLang;
  if (lang == 'ko' || s.isEmpty || !_hangul.hasMatch(s)) return s;
  _build(lang);
  final cache = _cache[lang]!;
  final hit = cache[s];
  if (hit != null) return hit;
  var out = _exact[lang]![s];
  if (out == null) {
    final trimmed = s.trim();
    if (trimmed != s && trimmed.isNotEmpty) {
      final inner = tr(trimmed, depth + 1);
      if (inner != trimmed) out = s.replaceFirst(trimmed, inner);
    }
  }
  if (out == null && depth < 4) {
    for (final (re, target) in _templates[lang]!) {
      final mt = re.firstMatch(s);
      if (mt == null) continue;
      final groups = [for (var i = 1; i <= mt.groupCount; i++) tr(mt.group(i)!, depth + 1)];
      var seq = 0;
      out = target.replaceAllMapped(RegExp(r'\{(\d*)\}'), (g) {
        final i = g.group(1)!.isEmpty ? seq++ : int.parse(g.group(1)!);
        return i < groups.length ? groups[i] : '';
      });
      break;
    }
  }
  out ??= s;
  if (cache.length > 6000) cache.clear();
  cache[s] = out;
  return out;
}

m.InlineSpan _span(m.InlineSpan span) {
  if (span is! m.TextSpan) return span;
  return m.TextSpan(
    text: span.text == null ? null : tr(span.text!),
    children: span.children?.map(_span).toList(),
    style: span.style,
    recognizer: span.recognizer,
    mouseCursor: span.mouseCursor,
    onEnter: span.onEnter,
    onExit: span.onExit,
    semanticsLabel: span.semanticsLabel,
    locale: span.locale,
    spellOut: span.spellOut,
  );
}

/// material Text와 같은 생성자. 그릴 때 문구를 번역한다.
class Text extends m.StatelessWidget {
  const Text(
    String this.data, {
    super.key,
    this.style,
    this.strutStyle,
    this.textAlign,
    this.textDirection,
    this.locale,
    this.softWrap,
    this.overflow,
    this.textScaler,
    this.maxLines,
    this.semanticsLabel,
    this.textWidthBasis,
    this.textHeightBehavior,
    this.selectionColor,
  }) : textSpan = null;

  const Text.rich(
    m.InlineSpan this.textSpan, {
    super.key,
    this.style,
    this.strutStyle,
    this.textAlign,
    this.textDirection,
    this.locale,
    this.softWrap,
    this.overflow,
    this.textScaler,
    this.maxLines,
    this.semanticsLabel,
    this.textWidthBasis,
    this.textHeightBehavior,
    this.selectionColor,
  }) : data = null;

  final String? data;
  final m.InlineSpan? textSpan;
  final m.TextStyle? style;
  final m.StrutStyle? strutStyle;
  final m.TextAlign? textAlign;
  final m.TextDirection? textDirection;
  final m.Locale? locale;
  final bool? softWrap;
  final m.TextOverflow? overflow;
  final m.TextScaler? textScaler;
  final int? maxLines;
  final String? semanticsLabel;
  final m.TextWidthBasis? textWidthBasis;
  final m.TextHeightBehavior? textHeightBehavior;
  final m.Color? selectionColor;

  @override
  m.Widget build(m.BuildContext context) {
    if (data != null) {
      return m.Text(tr(data!),
          style: style,
          strutStyle: strutStyle,
          textAlign: textAlign,
          textDirection: textDirection,
          locale: locale,
          softWrap: softWrap,
          overflow: overflow,
          textScaler: textScaler,
          maxLines: maxLines,
          semanticsLabel: semanticsLabel == null ? null : tr(semanticsLabel!),
          textWidthBasis: textWidthBasis,
          textHeightBehavior: textHeightBehavior,
          selectionColor: selectionColor);
    }
    return m.Text.rich(_span(textSpan!),
        style: style,
        strutStyle: strutStyle,
        textAlign: textAlign,
        textDirection: textDirection,
        locale: locale,
        softWrap: softWrap,
        overflow: overflow,
        textScaler: textScaler,
        maxLines: maxLines,
        semanticsLabel: semanticsLabel == null ? null : tr(semanticsLabel!),
        textWidthBasis: textWidthBasis,
        textHeightBehavior: textHeightBehavior,
        selectionColor: selectionColor);
  }
}

/// material Tooltip과 같은 사용법. 메시지를 번역한다.
class Tooltip extends m.StatelessWidget {
  const Tooltip({
    super.key,
    this.message,
    this.richMessage,
    this.child,
    this.waitDuration,
    this.preferBelow,
    this.verticalOffset,
    this.triggerMode,
    this.showDuration,
  });

  final String? message;
  final m.InlineSpan? richMessage;
  final m.Widget? child;
  final Duration? waitDuration;
  final bool? preferBelow;
  final double? verticalOffset;
  final m.TooltipTriggerMode? triggerMode;
  final Duration? showDuration;

  @override
  m.Widget build(m.BuildContext context) => m.Tooltip(
        message: richMessage == null ? tr(message ?? '') : null,
        richMessage: richMessage == null ? null : _span(richMessage!),
        waitDuration: waitDuration,
        preferBelow: preferBelow,
        verticalOffset: verticalOffset,
        triggerMode: triggerMode,
        showDuration: showDuration,
        child: child,
      );
}
