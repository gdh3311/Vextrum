import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../app_updates.dart';
import '../arena_ui.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../main.dart';
import '../settings.dart';
import '../team_state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'enemy_page.dart';

/// 이 기기에 저장된 기록 개수 (설정 화면 표시용)
final _storageProvider = FutureProvider.autoDispose<(int, int)>((ref) async {
  ref.watch(teamListProvider);
  try {
    final p = await SharedPreferences.getInstance();
    int count(String key) {
      final raw = p.getString(key);
      if (raw == null) return 0;
      final v = jsonDecode(raw);
      return v is List ? v.length : 0;
    }

    return (count('personal_match_journal_v1'), count('battle_history_v1'));
  } catch (_) {
    return (0, 0);
  }
});

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});
  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  late final _server = TextEditingController(text: ref.read(settingsNotifierProvider).apiBase ?? '');
  String? _serverStatus; // null | checking | ok:<version> | fail
  bool _refreshing = false;

  @override
  void dispose() {
    _server.dispose();
    super.dispose();
  }

  void _set(AppSettings Function(AppSettings) f) {
    final n = ref.read(settingsNotifierProvider.notifier);
    n.update(f(ref.read(settingsNotifierProvider)));
  }

  void _snack(String text) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _testServer() async {
    final base = _server.text.trim().isEmpty ? defaultApiBase : _server.text.trim().replaceAll(RegExp(r'/+$'), '');
    setState(() => _serverStatus = 'checking');
    try {
      final res = await Dio(BaseOptions(connectTimeout: const Duration(seconds: 6), receiveTimeout: const Duration(seconds: 10)))
          .get('$base/api/info');
      setState(() => _serverStatus = 'ok:${(res.data as Map)['dataVersion'] ?? ''}');
    } catch (_) {
      setState(() => _serverStatus = 'fail');
    }
  }

  void _applyServer() {
    final v = _server.text.trim();
    _set((s) => s.copyWith(apiBase: () => v.isEmpty ? null : v));
    _testServer();
  }

  void _invalidateData() {
    ref.invalidate(infoProvider);
    ref.invalidate(seasonMetaProvider);
    ref.invalidate(pokemonListProvider);
    ref.invalidate(itemsProvider);
    ref.invalidate(pokemonDetailProvider);
    ref.invalidate(labProvider);
    ref.invalidate(jokersProvider);
    ref.invalidate(partiesProvider);
    ref.invalidate(simulatedPartiesProvider);
  }

  Future<void> _refreshData() async {
    setState(() => _refreshing = true);
    try {
      final res = await dio.post('/api/refresh',
          options: Options(receiveTimeout: const Duration(minutes: 6), sendTimeout: const Duration(minutes: 1)));
      _invalidateData();
      if (mounted) _snack(tr('데이터를 갱신했습니다 · 버전 {}').replaceFirst('{}', '${(res.data as Map)['dataVersion']}'));
    } catch (_) {
      if (mounted) _snack('데이터를 갱신하지 못했습니다');
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  Future<void> _clearLocal() async {
    final ok = await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
              title: const Text('모든 로컬 데이터 지우기'),
              content: const Text('저장된 팀, 실전 기록, 배틀 기록과 설정을 모두 지웁니다. 되돌릴 수 없습니다.'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('취소')),
                FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: bad),
                    onPressed: () => Navigator.pop(c, true),
                    child: const Text('지우기')),
              ],
            ));
    if (ok != true) return;
    try {
      await (await SharedPreferences.getInstance()).clear();
    } catch (_) {}
    ref.invalidate(teamProvider);
    ref.invalidate(enemyProvider);
    ref.read(formatProvider.notifier).state = 'Doubles';
    ref.read(themeModeProvider.notifier).state = ThemeMode.dark;
    ref.read(arenaSceneProvider.notifier).state = 0;
    _server.clear();
    ref.read(settingsNotifierProvider.notifier).reset();
    if (mounted) _snack('로컬 데이터를 지웠습니다');
  }

  @override
  Widget build(BuildContext context) {
    final s = ref.watch(settingsNotifierProvider);
    final cs = Theme.of(context).colorScheme;
    final info = ref.watch(infoProvider);
    final teams = ref.watch(teamListProvider);
    final storage = ref.watch(_storageProvider).valueOrNull;
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant, height: 1.45);

    Widget row(String title, Widget control, {String? help, bool stack = false}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 10),
          child: LayoutBuilder(builder: (context, c) {
            final label = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600)),
              if (help != null) ...[const SizedBox(height: 3), Text(help, style: muted)],
            ]);
            if (stack || c.maxWidth < 640) {
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                label,
                const SizedBox(height: 10),
                control,
              ]);
            }
            return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
              Expanded(child: label),
              const SizedBox(width: 24),
              control,
            ]);
          }),
        );

    Widget seg<T>(T value, List<(T, String)> options, ValueChanged<T> onChanged) => SegmentedButton<T>(
          showSelectedIcon: false,
          segments: [for (final o in options) ButtonSegment(value: o.$1, label: Text(o.$2))],
          selected: {value},
          onSelectionChanged: (v) => onChanged(v.first),
        );

    final serverStatus = switch (_serverStatus) {
      null => null,
      'checking' => Text('확인 중…', style: muted),
      'fail' => const Text('연결할 수 없습니다', style: TextStyle(fontSize: 12.5, color: bad)),
      final ok => Text(tr('연결됨 · 데이터 {}').replaceFirst('{}', ok.substring(3)),
          style: const TextStyle(fontSize: 12.5, color: good)),
    };

    return PageBody(children: [
      const PageHeader('설정', subtitle: '언어, 화면, 데이터 연결을 설정합니다.', glyph: LabGlyph.spark),
      Section('언어와 표시',
          child: Column(children: [
            row(
              '언어',
              seg<String>(s.lang, [for (final l in languages) (l.$1, l.$2)], (v) => _set((x) => x.copyWith(lang: v))),
              help: '앱 화면 문구와 포켓몬·기술·도구 이름에 적용됩니다. 서버가 만드는 설명 문장은 아직 한국어로 표시됩니다.',
            ),
            const Divider(),
            row(
              '이름 표시',
              seg<bool>(s.showEnglish, const [(true, '현재 언어 + 영문'), (false, '현재 언어만')],
                  (v) => _set((x) => x.copyWith(showEnglish: v))),
            ),
            const Divider(),
            row(
              '화면 테마',
              seg<ThemeMode>(ref.watch(themeModeProvider),
                  const [(ThemeMode.system, '시스템 설정'), (ThemeMode.dark, '어둡게'), (ThemeMode.light, '밝게')],
                  (v) => ref.read(themeModeProvider.notifier).state = v),
            ),
            const Divider(),
            row(
              '글자 크기',
              seg<double>(s.textScale, const [(.9, '작게'), (1.0, '보통'), (1.15, '크게'), (1.3, '아주 크게')],
                  (v) => _set((x) => x.copyWith(textScale: v))),
            ),
            const Divider(),
            row(
              '애니메이션 줄이기',
              Switch(value: s.reduceMotion, onChanged: (v) => _set((x) => x.copyWith(reduceMotion: v))),
              help: '화면 전환과 경기장 효과의 움직임을 줄입니다.',
            ),
            const Divider(),
            row(
              '경기장 배경',
              seg<int>(ref.watch(arenaSceneProvider), [
                for (var i = 0; i < arenaSceneNames.length; i++) (i, arenaSceneNames[i]),
              ], (v) => ref.read(arenaSceneProvider.notifier).state = v),
            ),
          ])),
      Section('배틀',
          child: row(
            '기본 배틀 형식',
            seg<String>(ref.watch(formatProvider), const [('Doubles', '더블배틀'), ('Singles', '싱글배틀')],
                (v) => ref.read(formatProvider.notifier).state = v),
            help: '앱을 열 때 선택되는 형식입니다. 화면 왼쪽 메뉴에서도 바로 바꿀 수 있습니다.',
          )),
      Section('데이터와 연결',
          child: Column(children: [
            row(
              '서버 주소',
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(
                    child: TextField(
                      controller: _server,
                      style: const TextStyle(fontSize: 14),
                      decoration: InputDecoration(hintText: defaultApiBase, isDense: true),
                      onSubmitted: (_) => _applyServer(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(onPressed: _applyServer, child: const Text('적용')),
                  const SizedBox(width: 6),
                  OutlinedButton(onPressed: _testServer, child: const Text('연결 확인')),
                ]),
                const SizedBox(height: 6),
                Row(children: [
                  if (serverStatus != null) Expanded(child: serverStatus) else const Spacer(),
                  if (s.apiBase != null)
                    TextButton(
                        onPressed: () {
                          _server.clear();
                          _applyServer();
                        },
                        child: const Text('기본값으로')),
                ]),
              ]),
              help: '다른 기기에서 쓰려면 백엔드를 실행 중인 PC의 주소를 넣으세요. 예: http://192.168.0.10:8000',
              stack: true,
            ),
            const Divider(),
            row(
              '배틀 데이터',
              FilledButton.tonalIcon(
                onPressed: _refreshing ? null : _refreshData,
                icon: _refreshing
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.sync, size: 18),
                label: Text(_refreshing ? '갱신 중…' : '지금 갱신'),
              ),
              help: [
                if (info.valueOrNull != null)
                  tr('{} 기준 · 버전 {}')
                      .replaceFirst('{}', (info.value!['generatedAt'] as String).substring(0, 16).replaceFirst('T', ' '))
                      .replaceFirst('{}', '${info.value!['dataVersion']}'),
                if (info.valueOrNull?['provenance'] case final Map prov when prov['officialSeason'] != null)
                  tr('공식 시즌 {} · 레귤레이션 {} (메가진화 배틀당 1회, 도구 중복 금지) · 데이터 표기 시즌 {}')
                      .replaceFirst('{}', '${prov['officialSeason']}')
                      .replaceFirst('{}', '${prov['regulation']}')
                      .replaceFirst('{}', '${prov['sourceSeason']}'),
                if (info.valueOrNull?['provenance'] case final Map prov when prov['seasonMismatch'] == true)
                  tr('원본 데이터가 아직 새 시즌 폴더를 열지 않아, 순위·채용률은 원본이 표기한 시즌의 표본입니다.'),
                tr('순위는 사용률(%)이 아니라 순서입니다. 메타 가중치로만 씁니다.'),
                tr('원본 사이트에서 새 데이터를 받습니다. 1~2분 걸릴 수 있습니다.'),
              ].join('\n'),
            ),
          ])),
      Section('저장 공간',
          child: Column(children: [
            row(
              '이 기기에 저장된 데이터',
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(foregroundColor: bad),
                onPressed: _clearLocal,
                icon: const Icon(Icons.delete_outline, size: 18),
                label: const Text('모든 로컬 데이터 지우기'),
              ),
              help: storage == null
                  ? null
                  : tr('팀 {}개 · 실전 기록 {}건 · 배틀 기록 {}건')
                      .replaceFirst('{}', '${teams.where((t) => t.sets.isNotEmpty).length}')
                      .replaceFirst('{}', '${storage.$1}')
                      .replaceFirst('{}', '${storage.$2}'),
            ),
          ])),
      Section('정보',
          child: Column(children: [
            row('버전', Row(mainAxisSize: MainAxisSize.min, children: [
              Text(appVersion, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
              const SizedBox(width: 12),
              const UpdatesButton(compact: true),
            ])),
            const Divider(),
            row(
              '데이터 출처',
              const SizedBox(),
              help: [
                'Battle data provided by Pokémon Champions Battle Data (championsbattledata.com)',
                'Move data: Pokémon Showdown · Names: PokeAPI',
                tr('비공식 팬 도구입니다. Pokémon과 관련 상표는 각 권리자의 것입니다.'),
              ].join('\n'),
              stack: true,
            ),
          ])),
    ]);
  }
}
