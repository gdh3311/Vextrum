import 'dart:math' as math;

import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'lab_icons.dart';
import 'i18n.dart';

const _scenes = [
  ('assets/arena.jpg', '야간 스타디움', Color(0xFFFFCA68), LabGlyph.moon),
  ('assets/arena-rain.jpg', '빗속 스타디움', Color(0xFF86EBDC), LabGlyph.cloud),
  ('assets/battlefield.jpg', '결승전 스타디움', Color(0xFFFFB185), LabGlyph.versus),
];

final arenaSceneProvider = StateProvider<int>((ref) => 0);

/// 설정 화면용: 경기장 이름 목록
List<String> get arenaSceneNames => [for (final s in _scenes) s.$2];
const _arenaInk = Color(0xFF0B1629);

class ArenaHero extends ConsumerWidget {
  const ArenaHero({super.key, required this.title, required this.subtitle});
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reduced = MediaQuery.disableAnimationsOf(context);
    final index = ref.watch(arenaSceneProvider).clamp(0, _scenes.length - 1);
    final (asset, name, accent, glyph) = _scenes[index];
    void change(int step) => ref.read(arenaSceneProvider.notifier).state =
        (index + step) % _scenes.length;

    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: LayoutBuilder(builder: (context, constraints) {
        final compact = constraints.maxWidth < 650;
        final art = _ArenaArt(
            asset: asset, accent: accent, compact: compact, reduced: reduced);
        final controls = _SceneControls(
          name: name,
          accent: accent,
          glyph: glyph,
          previous: () => change(-1),
          next: () => change(1),
        );
        final intro = Padding(
          padding: EdgeInsets.fromLTRB(
              compact ? 17 : 30, compact ? 14 : 26, 16, compact ? 20 : 26),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Semantics(
              header: true,
              child: Text(title,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: compact ? 32 : 47,
                    height: 1.12,
                    letterSpacing: compact ? -.9 : -1.9,
                    fontWeight: FontWeight.w700,
                  )),
            ),
            const SizedBox(height: 8),
            Text(subtitle,
                style: const TextStyle(
                  color: Color(0xFFCCDFEF),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                )),
            const SizedBox(height: 19),
            Wrap(spacing: 8, runSpacing: 8, children: [
              FilledButton.icon(
                onPressed: () => context.go('/team'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFFFFCD6B),
                  foregroundColor: const Color(0xFF142038),
                ),
                icon: const LabIcon(LabGlyph.team, size: 19),
                label: const Text('팀 빌더'),
              ),
              OutlinedButton.icon(
                onPressed: () => context.go('/enemy'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  backgroundColor: const Color(0xAA0C1A2E),
                  side: const BorderSide(color: Color(0x80B6D8EB)),
                ),
                icon: const LabIcon(LabGlyph.versus, size: 18),
                label: const Text('실전 상대 분석'),
              ),
            ]),
          ]),
        );
        return Material(
          color: _arenaInk,
          clipBehavior: Clip.antiAlias,
          borderRadius: BorderRadius.circular(22),
          child: compact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                      SizedBox(
                        height: 168,
                        child: Stack(children: [
                          Positioned.fill(child: art),
                          Positioned(right: 10, bottom: 4, child: controls),
                        ]),
                      ),
                      intro,
                    ])
              : Stack(children: [
                  Positioned.fill(child: art),
                  Container(
                    constraints: const BoxConstraints(minHeight: 266),
                    alignment: Alignment.centerLeft,
                    child: FractionallySizedBox(
                      widthFactor: .59,
                      alignment: Alignment.centerLeft,
                      child: intro,
                    ),
                  ),
                  Positioned(right: 14, bottom: 14, child: controls),
                ]),
        );
      }),
    );
  }
}

class _ArenaArt extends StatelessWidget {
  const _ArenaArt(
      {required this.asset,
      required this.accent,
      required this.compact,
      required this.reduced});
  final String asset;
  final Color accent;
  final bool compact;
  final bool reduced;

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: AnimatedSwitcher(
          duration: reduced ? Duration.zero : const Duration(milliseconds: 460),
          switchInCurve: Curves.easeOutCubic,
          layoutBuilder: (current, previous) => Stack(
            fit: StackFit.expand,
            children: [...previous, if (current != null) current],
          ),
          child: Stack(key: ValueKey(asset), fit: StackFit.expand, children: [
            Image.asset(asset,
                fit: BoxFit.cover,
                alignment: Alignment(1, compact ? -.22 : -.52),
                excludeFromSemantics: true),
            if (asset == 'assets/battlefield.jpg')
              Positioned(
                right: compact ? 14 : 32,
                bottom: compact ? 23 : 31,
                child: _FinalsArt(compact: compact),
              ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: compact
                    ? const LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          Colors.transparent,
                          _arenaInk
                        ],
                        stops: [0, .58, 1],
                      )
                    : const LinearGradient(
                        colors: [
                          _arenaInk,
                          Color(0xD40B1629),
                          Color(0x350B1629),
                          Colors.transparent
                        ],
                        stops: [0, .32, .64, 1],
                      ),
              ),
            ),
            if (!reduced)
              IgnorePointer(
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: const Duration(milliseconds: 1200),
                  curve: Curves.easeOutCubic,
                  builder: (_, value, __) =>
                      CustomPaint(painter: _ArenaSparks(value, accent)),
                ),
              ),
          ]),
        ),
      );
}

class _FinalsArt extends StatelessWidget {
  const _FinalsArt({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final size = compact ? 104.0 : 156.0;
    return SizedBox(
      width: size * 1.96,
      height: size * 1.12,
      child: Stack(children: [
        Positioned(
          left: 0,
          bottom: size * .14,
          child: _FinalsSprite('venusaur',
              size: size * .90, light: const Color(0xFF64E3CD)),
        ),
        Positioned(
          right: 0,
          bottom: 0,
          child: _FinalsSprite('arcanine',
              size: size, light: const Color(0xFFFF825F)),
        ),
      ]),
    );
  }
}

class _FinalsSprite extends StatelessWidget {
  const _FinalsSprite(this.name, {required this.size, required this.light});

  final String name;
  final double size;
  final Color light;

  @override
  Widget build(BuildContext context) => SizedBox.square(
        dimension: size,
        child: Stack(alignment: Alignment.bottomCenter, children: [
          Positioned(
            bottom: 0,
            child: Container(
              width: size * .85,
              height: size * .19,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(size),
                color: const Color(0x9C071324),
                boxShadow: [
                  BoxShadow(color: light.withOpacity(.35), blurRadius: 16)
                ],
              ),
            ),
          ),
          Image.asset('assets/arena/$name.png',
              excludeFromSemantics: true, fit: BoxFit.contain),
        ]),
      );
}

class _SceneControls extends StatelessWidget {
  const _SceneControls({
    required this.name,
    required this.accent,
    required this.glyph,
    required this.previous,
    required this.next,
  });

  final String name;
  final Color accent;
  final LabGlyph glyph;
  final VoidCallback previous;
  final VoidCallback next;

  @override
  Widget build(BuildContext context) => Material(
        color: const Color(0xE4112138),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(24),
          side: const BorderSide(color: Color(0x507D9CB8)),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            onPressed: previous,
            tooltip: tr('이전 경기장'),
            color: Colors.white,
            icon: const LabIcon(LabGlyph.back, size: 17),
          ),
          LabIcon(glyph, size: 16, color: accent),
          const SizedBox(width: 6),
          Semantics(
              liveRegion: true,
              child: Text(name,
                  style: const TextStyle(
                    color: Color(0xFFF1F6FE),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ))),
          IconButton(
            onPressed: next,
            tooltip: tr('다음 경기장'),
            color: Colors.white,
            icon: const LabIcon(LabGlyph.forward, size: 17),
          ),
        ]),
      );
}

class _ArenaSparks extends CustomPainter {
  const _ArenaSparks(this.progress, this.accent);
  final double progress;
  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    final pulse = math.sin(math.pi * progress);
    final light = Paint()..color = accent.withOpacity(pulse * .8);
    for (final (x, y, radius) in const [
      (.62, .75, 1.7),
      (.71, .29, 1.3),
      (.93, .25, 2.0),
      (.87, .72, 1.2),
      (.80, .58, 1.7),
    ]) {
      final p = Offset(
          size.width * x + progress * 18, size.height * y - progress * 17);
      canvas.drawCircle(p, radius, light);
      canvas.drawLine(p.translate(-5, 3), p, light);
    }
  }

  @override
  bool shouldRepaint(_ArenaSparks oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.accent != accent;
}

class ArenaHeader extends StatelessWidget {
  const ArenaHeader(
      {super.key,
      required this.title,
      required this.glyph,
      this.subtitle,
      this.trailing});
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final LabGlyph glyph;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(19),
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [
              cs.primary.withOpacity(.10),
              cs.surfaceContainerLow,
              cs.surfaceContainerLow
            ]),
            border: Border.all(color: cs.outlineVariant),
            borderRadius: BorderRadius.circular(19),
          ),
          child: Stack(children: [
            Positioned(
              right: -18,
              top: -34,
              child: ExcludeSemantics(
                  child: LabIcon(LabGlyph.ball,
                      size: 155, color: cs.primary.withOpacity(.08))),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: LayoutBuilder(builder: (context, constraints) {
                final narrow = constraints.maxWidth < 470;
                final identity = Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: cs.primary.withOpacity(.12),
                          border:
                              Border.all(color: cs.primary.withOpacity(.26)),
                          borderRadius: BorderRadius.circular(13),
                        ),
                        child: Center(
                            child: LabIcon(glyph, size: 23, color: cs.primary)),
                      ),
                      const SizedBox(width: 13),
                      Expanded(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(title,
                                  style: TextStyle(
                                      fontSize: narrow ? 22 : 28,
                                      letterSpacing: -.7,
                                      fontWeight: FontWeight.w700)),
                              if (subtitle != null)
                                Text(subtitle!,
                                    style: TextStyle(
                                        fontSize: 13,
                                        color: cs.onSurfaceVariant)),
                            ]),
                      ),
                    ]);
                if (trailing == null) return identity;
                return narrow
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                            identity,
                            const SizedBox(height: 8),
                            trailing!,
                          ])
                    : Row(children: [
                        Expanded(child: identity),
                        const SizedBox(width: 12),
                        trailing!
                      ]);
              }),
            ),
          ]),
        ),
      ),
    );
  }
}
