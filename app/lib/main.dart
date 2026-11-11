import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'lab_icons.dart';
import 'api.dart';
import 'arena_ui.dart';
import 'pages/auto_team_page.dart';
import 'pages/battle_page.dart';
import 'pages/enemy_page.dart';
import 'pages/joker_page.dart';
import 'pages/meta_page.dart';
import 'pages/parties_page.dart';
import 'pages/pokemon_page.dart';
import 'pages/pokemon_overview.dart';
import 'pages/team_page.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SharedPreferences? prefs;
  try {
    prefs = await SharedPreferences.getInstance();
  } catch (_) {}
  final fmt = prefs?.getString('format');
  final dark = prefs?.getBool('dark');
  runApp(ProviderScope(
    overrides: [
      if (fmt == 'Singles' || fmt == 'Doubles') formatProvider.overrideWith((ref) => fmt!),
      if (dark != null) themeModeProvider.overrideWith((ref) => dark ? ThemeMode.dark : ThemeMode.light),
    ],
    observers: [_SettingsSaver(prefs)],
    child: const MetaLabApp(),
  ));
}

/// 배틀 형식과 화면 밝기를 바꿀 때마다 저장한다.
class _SettingsSaver extends ProviderObserver {
  final SharedPreferences? prefs;
  _SettingsSaver(this.prefs);
  @override
  void didUpdateProvider(ProviderBase provider, Object? previousValue, Object? newValue, ProviderContainer container) {
    if (provider == formatProvider && newValue is String) prefs?.setString('format', newValue);
    if (provider == themeModeProvider && newValue is ThemeMode) prefs?.setBool('dark', newValue == ThemeMode.dark);
  }
}

Page<void> _routePage(GoRouterState state, Widget child) => CustomTransitionPage<void>(
      key: state.pageKey,
      child: child,
      transitionDuration: const Duration(milliseconds: 230),
      reverseTransitionDuration: const Duration(milliseconds: 160),
      transitionsBuilder: (context, animation, _, page) {
        if (MediaQuery.disableAnimationsOf(context)) return page;
        final progress = animation.drive(CurveTween(curve: Curves.easeOutCubic));
        return FadeTransition(
          opacity: progress,
          child: SlideTransition(
            position: progress.drive(Tween(begin: const Offset(0, .012), end: Offset.zero)),
            child: page,
          ),
        );
      },
    );

final _router = GoRouter(routes: [
  ShellRoute(
    builder: (context, state, child) => Shell(location: state.uri.path, child: child),
    routes: [
      GoRoute(path: '/', pageBuilder: (c, s) => _routePage(s, const MetaPage())),
      GoRoute(path: '/team', pageBuilder: (c, s) => _routePage(s, const TeamPage())),
      GoRoute(path: '/team/auto', pageBuilder: (c, s) => _routePage(s, const AutoTeamPage())),
      GoRoute(path: '/enemy', pageBuilder: (c, s) => _routePage(s, const EnemyPage())),
      GoRoute(path: '/jokers', pageBuilder: (c, s) => _routePage(s, const JokerPage())),
      GoRoute(path: '/parties', pageBuilder: (c, s) => _routePage(s, const PartiesPage())),
      GoRoute(path: '/battle', pageBuilder: (c, s) => _routePage(s, const BattlePage())),
      GoRoute(
          path: '/pokemon/:id',
          pageBuilder: (c, s) {
            final id = s.pathParameters['id']!;
            final season = s.uri.queryParameters['season'];
            return _routePage(
              s, season == null
                  ? PokemonPage(id: id)
                  : PageBody(children: [PokemonOverview(id: id, season: season)]),
            );
          }),
    ],
  ),
]);

class MetaLabApp extends ConsumerWidget {
  const MetaLabApp({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
        title: 'Champions Meta Lab',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        themeMode: ref.watch(themeModeProvider),
        routerConfig: _router,
      );
}

const _tabs = [
  ('/', LabGlyph.meta, '메타', '메타', Color(0xFF78DACE)),
  ('/team', LabGlyph.team, '팀 빌더', '팀', Color(0xFF83B9FF)),
  ('/enemy', LabGlyph.versus, '상대 분석', '상대', Color(0xFFFF9C92)),
  ('/jokers', LabGlyph.crystal, '조커 파인더', '조커', Color(0xFFC3A6FF)),
  ('/parties', LabGlyph.archive, '파티 탐색', '파티', Color(0xFFFFCB6D)),
  ('/battle', LabGlyph.controller, '가상 배틀', '배틀', Color(0xFFA8DF98)),
];

class _Logo extends StatelessWidget {
  const _Logo();
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
        width: 39, height: 39,
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFFFFDB80), Color(0xFFEFA94D)]),
          borderRadius: BorderRadius.circular(11),
        ),
        child: const Center(child: LabIcon(LabGlyph.ball, size: 28, color: Color(0xFF1C2B41))),
      ),
      const SizedBox(width: 9),
      Flexible(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Text('CHAMPIONS', overflow: TextOverflow.ellipsis, style: TextStyle(
              color: cs.onSurfaceVariant, fontSize: 9, letterSpacing: 1.8, fontWeight: FontWeight.w700)),
          const Text('META LAB', overflow: TextOverflow.ellipsis,
              style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, letterSpacing: .65, height: 1.1)),
        ]),
      ),
    ]);
  }
}

class _FormatToggle extends ConsumerWidget {
  final bool expand;
  const _FormatToggle({this.expand = false});
  @override
  Widget build(BuildContext context, WidgetRef ref) => SegmentedButton<String>(
        showSelectedIcon: false,
        expandedInsets: expand ? EdgeInsets.zero : null,
        style: const ButtonStyle(visualDensity: VisualDensity.compact),
        segments: const [
          ButtonSegment(value: 'Doubles', label: Text('더블')),
          ButtonSegment(value: 'Singles', label: Text('싱글')),
        ],
        selected: {ref.watch(formatProvider)},
        onSelectionChanged: (s) => ref.read(formatProvider.notifier).state = s.first,
      );
}

class Shell extends ConsumerWidget {
  final String location;
  final Widget child;
  const Shell({super.key, required this.location, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final wide = MediaQuery.sizeOf(context).width >= 960;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final isDetail = location.startsWith('/pokemon');
    final isTeamDraft = location == '/team/auto';
    final found = _tabs.indexWhere((t) => t.$1 == location || location.startsWith('${t.$1}/'));
    final index = isDetail ? -1 : (found < 0 ? 0 : found);
    void back() => context.canPop() ? context.pop() : context.go(isTeamDraft ? '/team' : '/');
    void toggleTheme() => ref.read(themeModeProvider.notifier).state = dark ? ThemeMode.light : ThemeMode.dark;

    if (!wide) {
      return Scaffold(
        appBar: AppBar(
          automaticallyImplyLeading: false,
          leading: isDetail || isTeamDraft
              ? IconButton(tooltip: '뒤로', icon: const LabIcon(LabGlyph.back), onPressed: back)
              : null,
          titleSpacing: isDetail || isTeamDraft ? 0 : 16,
          title: const _Logo(),
        actions: [
          const _FormatToggle(),
          IconButton(
            tooltip: dark ? '밝은 화면' : '어두운 화면',
            onPressed: toggleTheme,
            icon: LabIcon(dark ? LabGlyph.sun : LabGlyph.moon, size: 19),
          ),
        ],
        ),
        body: child,
        bottomNavigationBar: NavigationBar(
          selectedIndex: index < 0 ? 0 : index,
          onDestinationSelected: (i) => context.go(_tabs[i].$1),
          destinations: [
            for (final t in _tabs)
              NavigationDestination(icon: LabIcon(t.$2, size: 22),
                  selectedIcon: LabIcon(t.$2, size: 22, color: cs.primary), label: t.$4),
          ],
        ),
      );
    }

    return Scaffold(
      body: Row(children: [
        Container(
          width: 218,
          decoration: BoxDecoration(
            color: cs.surfaceContainerLowest,
            border: Border(right: BorderSide(color: cs.outlineVariant)),
          ),
          padding: const EdgeInsets.fromLTRB(14, 24, 14, 15),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Padding(padding: EdgeInsets.only(left: 8), child: _Logo()),
            const SizedBox(height: 21),
            Expanded(child: ListView(padding: EdgeInsets.zero, children: [
              for (var i = 0; i < _tabs.length; i++)
                _NavItem(
                  icon: _tabs[i].$2,
                  accent: dark ? _tabs[i].$5 : cs.primary,
                  label: _tabs[i].$3,
                  selected: i == index,
                  onTap: () => context.go(_tabs[i].$1),
                ),
            ])),
            const Divider(),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.only(left: 8, bottom: 8),
              child: Text('배틀 형식', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            ),
            const _FormatToggle(expand: true),
            const SizedBox(height: 10),
            _NavItem(
                icon: dark ? LabGlyph.sun : LabGlyph.moon,
                accent: cs.primary,
                label: dark ? '밝은 화면' : '어두운 화면',
                selected: false,
                onTap: toggleTheme),
          ]),
        ),
        Expanded(
          child: Column(children: [
            if (isDetail)
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 14, 0, 0),
                  child: TextButton.icon(
                      onPressed: back, icon: const LabIcon(LabGlyph.back, size: 18), label: const Text('뒤로')),
                ),
              ),
            Expanded(child: child),
          ]),
        ),
      ]),
    );
  }
}

class _NavItem extends StatelessWidget {
  final LabGlyph icon;
  final String label;
  final bool selected;
  final Color accent;
  final VoidCallback onTap;
  const _NavItem({required this.icon, required this.label, required this.selected, required this.accent, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: AnimatedContainer(
        duration: MediaQuery.disableAnimationsOf(context) ? Duration.zero : const Duration(milliseconds: 180),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: selected ? accent.withOpacity(.40) : Colors.transparent),
          color: selected ? accent.withOpacity(.12) : Colors.transparent,
        ),
        child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
            child: Row(children: [
              Container(
                width: 32, height: 32,
                decoration: BoxDecoration(color: accent.withOpacity(.12), borderRadius: BorderRadius.circular(9)),
                child: Center(child: LabIcon(icon, size: 20, color: accent)),
              ),
              const SizedBox(width: 10),
              Text(label,
                  style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                      color: selected ? cs.onSurface : cs.onSurfaceVariant)),
            ]),
          ),
        ),
        ),
      ),
    );
  }
}

/// 본문 공통 래퍼: 최대 폭 제한 + 스크롤
class PageBody extends StatelessWidget {
  final List<Widget> children;
  const PageBody({super.key, required this.children});
  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 960;
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1280),
        child: ListView(
            padding: wide ? const EdgeInsets.fromLTRB(32, 28, 32, 40) : const EdgeInsets.all(16), children: children),
      ),
    );
  }
}

/// 페이지 제목 + 설명
class PageHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final LabGlyph glyph;
  const PageHeader(this.title, {super.key, this.subtitle, this.trailing, this.glyph = LabGlyph.ball});
  @override
  Widget build(BuildContext context) => ArenaHeader(
      title: title, subtitle: subtitle, trailing: trailing, glyph: glyph);
}
