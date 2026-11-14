import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'i18n.dart';

const appVersion = '1.19.0';

/// 기기에 저장하는 앱 설정. 배틀 형식·테마·경기장은 기존 provider(formatProvider 등)가 따로 들고 있다.
class AppSettings {
  final String lang; // ko | en | ja
  final bool showEnglish; // 이름 아래 영문 이름
  final double textScale;
  final bool reduceMotion;
  final String? apiBase; // null = 기본 주소

  const AppSettings({
    this.lang = 'ko',
    this.showEnglish = true,
    this.textScale = 1.0,
    this.reduceMotion = false,
    this.apiBase,
  });

  AppSettings copyWith({String? lang, bool? showEnglish, double? textScale, bool? reduceMotion,
          String? Function()? apiBase}) =>
      AppSettings(
        lang: lang ?? this.lang,
        showEnglish: showEnglish ?? this.showEnglish,
        textScale: textScale ?? this.textScale,
        reduceMotion: reduceMotion ?? this.reduceMotion,
        apiBase: apiBase != null ? apiBase() : this.apiBase,
      );

  static AppSettings load(SharedPreferences? p) {
    var lang = p?.getString('lang');
    if (lang == null) {
      // 처음 실행: 기기 언어를 따른다.
      final sys = WidgetsBinding.instance.platformDispatcher.locale.languageCode;
      lang = languages.any((l) => l.$1 == sys) ? sys : 'ko';
    }
    return AppSettings(
      lang: languages.any((l) => l.$1 == lang) ? lang : 'ko',
      showEnglish: p?.getBool('showEnglish') ?? true,
      textScale: (p?.getDouble('textScale') ?? 1.0).clamp(.85, 1.4),
      reduceMotion: p?.getBool('reduceMotion') ?? false,
      apiBase: p?.getString('apiBase'),
    );
  }

  Future<void> save() async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString('lang', lang);
      await p.setBool('showEnglish', showEnglish);
      await p.setDouble('textScale', textScale);
      await p.setBool('reduceMotion', reduceMotion);
      if (apiBase == null) {
        await p.remove('apiBase');
      } else {
        await p.setString('apiBase', apiBase!);
      }
    } catch (_) {}
  }

  /// 전역 상태(번역 언어, 이름 표시, 서버 주소·요청 헤더)에 반영한다.
  void apply() {
    currentLang = lang;
    showEnglishNames = showEnglish;
    configureApi(base: apiBase, lang: lang);
  }
}

class SettingsNotifier extends StateNotifier<AppSettings> {
  SettingsNotifier(super.initial) {
    state.apply();
  }

  void update(AppSettings next) {
    final redraw = next.lang != state.lang || next.showEnglish != state.showEnglish;
    next.apply();
    if (redraw) rebuildAllText();
    state = next;
    next.save();
  }

  void reset() => update(const AppSettings());
}

final settingsProvider = StateProvider<AppSettings>((ref) => const AppSettings());
final settingsNotifierProvider =
    StateNotifierProvider<SettingsNotifier, AppSettings>((ref) => SettingsNotifier(ref.read(settingsProvider)));

/// 서버 응답이 달라지는 조건 (언어, 서버 주소). 데이터 provider들이 이것을 watch해서 바뀌면 다시 받는다.
final apiContextProvider = Provider<(String, String)>((ref) {
  final s = ref.watch(settingsNotifierProvider);
  return (s.lang, s.apiBase ?? defaultApiBase);
});
