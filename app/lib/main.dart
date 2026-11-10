import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'api.dart';
import 'pages/enemy_page.dart';
import 'pages/joker_page.dart';
import 'pages/meta_page.dart';
import 'pages/pokemon_page.dart';
import 'pages/team_page.dart';

void main() => runApp(const ProviderScope(child: MetaLabApp()));

final _router = GoRouter(routes: [
  ShellRoute(
    builder: (context, state, child) => Shell(location: state.uri.path, child: child),
    routes: [
      GoRoute(path: '/', pageBuilder: (c, s) => const NoTransitionPage(child: MetaPage())),
      GoRoute(path: '/team', pageBuilder: (c, s) => const NoTransitionPage(child: TeamPage())),
      GoRoute(path: '/enemy', pageBuilder: (c, s) => const NoTransitionPage(child: EnemyPage())),
      GoRoute(path: '/jokers', pageBuilder: (c, s) => const NoTransitionPage(child: JokerPage())),
      GoRoute(
          path: '/pokemon/:id',
          pageBuilder: (c, s) => NoTransitionPage(child: PokemonPage(id: s.pathParameters['id']!))),
    ],
  ),
]);

class MetaLabApp extends StatelessWidget {
  const MetaLabApp({super.key});
  @override
  Widget build(BuildContext context) {
    ThemeData theme(Brightness b) {
      final cs = ColorScheme.fromSeed(seedColor: const Color(0xFF2F6FED), brightness: b);
      return ThemeData(
        colorScheme: cs,
        useMaterial3: true,
        fontFamilyFallback: const ['Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR', 'sans-serif'],
        cardTheme: CardTheme(
            elevation: 0,
            color: cs.surfaceContainerLow,
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14), side: BorderSide(color: cs.outlineVariant))),
        inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
      );
    }

    return MaterialApp.router(
      title: 'Champions Meta Lab',
      debugShowCheckedModeBanner: false,
      theme: theme(Brightness.light),
      darkTheme: theme(Brightness.dark),
      routerConfig: _router,
    );
  }
}

const _tabs = [
  ('/', Icons.leaderboard_outlined, Icons.leaderboard, '메타'),
  ('/team', Icons.groups_outlined, Icons.groups, '팀 빌더'),
  ('/enemy', Icons.sports_kabaddi_outlined, Icons.sports_kabaddi, '상대 분석'),
  ('/jokers', Icons.diamond_outlined, Icons.diamond, '조커 파인더'),
];

class Shell extends ConsumerWidget {
  final String location;
  final Widget child;
  const Shell({super.key, required this.location, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final fmt = ref.watch(formatProvider);
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final index = location.startsWith('/team')
        ? 1
        : location.startsWith('/enemy')
            ? 2
            : location.startsWith('/jokers')
                ? 3
                : 0;
    final isDetail = location.startsWith('/pokemon');
    return Scaffold(
      appBar: AppBar(
        leading: isDetail
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () => context.canPop() ? context.pop() : context.go('/'))
            : null,
        titleSpacing: isDetail ? 0 : 16,
        title: const Text('Champions Meta Lab', style: TextStyle(fontWeight: FontWeight.w800)),
        actions: [
          SegmentedButton<String>(
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: const [
              ButtonSegment(value: 'Doubles', label: Text('더블')),
              ButtonSegment(value: 'Singles', label: Text('싱글')),
            ],
            selected: {fmt},
            onSelectionChanged: (s) => ref.read(formatProvider.notifier).state = s.first,
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: Row(children: [
        if (wide)
          NavigationRail(
            selectedIndex: index,
            labelType: NavigationRailLabelType.all,
            onDestinationSelected: (i) => context.go(_tabs[i].$1),
            destinations: [
              for (final t in _tabs)
                NavigationRailDestination(icon: Icon(t.$2), selectedIcon: Icon(t.$3), label: Text(t.$4)),
            ],
          ),
        Expanded(child: child),
      ]),
      bottomNavigationBar: wide
          ? null
          : NavigationBar(
              selectedIndex: index,
              onDestinationSelected: (i) => context.go(_tabs[i].$1),
              destinations: [
                for (final t in _tabs)
                  NavigationDestination(icon: Icon(t.$2), selectedIcon: Icon(t.$3), label: t.$4),
              ],
            ),
    );
  }
}

/// 본문 공통 래퍼: 최대 폭 제한 + 스크롤
class PageBody extends StatelessWidget {
  final List<Widget> children;
  const PageBody({super.key, required this.children});
  @override
  Widget build(BuildContext context) => Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1180),
          child: ListView(padding: const EdgeInsets.all(16), children: children),
        ),
      );
}
