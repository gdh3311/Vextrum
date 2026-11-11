import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'lab_icons.dart';

const _arena = 'assets/arena.jpg';

class ArenaHero extends StatelessWidget {
  const ArenaHero({super.key, required this.title, required this.subtitle});
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    final reduced = MediaQuery.disableAnimationsOf(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: LayoutBuilder(builder: (context, constraints) {
        final compact = constraints.maxWidth < 560;
        return ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Stack(alignment: Alignment.centerLeft, children: [
            Positioned.fill(
              child: Image.asset(_arena,
                  fit: BoxFit.cover,
                  alignment: Alignment(compact ? .91 : 1, -.42),
                  excludeFromSemantics: true),
            ),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: [
                    const Color(0xFF071124).withOpacity(compact ? .95 : .78),
                    const Color(0xFF071124).withOpacity(compact ? .72 : .20),
                    Colors.transparent,
                  ], stops: const [
                    0,
                    .53,
                    1
                  ]),
                ),
              ),
            ),
            Positioned.fill(
              child: IgnorePointer(
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: reduced
                      ? Duration.zero
                      : const Duration(milliseconds: 1050),
                  curve: Curves.easeOutCubic,
                  builder: (_, value, __) =>
                      CustomPaint(painter: _ArenaSparks(value)),
                ),
              ),
            ),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 530),
              child: Padding(
                padding: EdgeInsets.symmetric(
                    horizontal: compact ? 19 : 30, vertical: compact ? 25 : 32),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(subtitle,
                          style: const TextStyle(
                              color: Color(0xFFB6D8EB),
                              fontSize: 12,
                              fontWeight: FontWeight.w600)),
                      const SizedBox(height: 7),
                      Text(title,
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: compact ? 29 : 44,
                              height: 1.08,
                              letterSpacing: compact ? -.8 : -1.7,
                              fontWeight: FontWeight.w700,
                              shadows: const [
                                Shadow(blurRadius: 16, color: Color(0xCC081322))
                              ])),
                      const SizedBox(height: 18),
                      Wrap(spacing: 8, runSpacing: 8, children: [
                        FilledButton.icon(
                          onPressed: () => context.go('/team'),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFFFFCB62),
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
              ),
            ),
          ]),
        );
      }),
    );
  }
}

class _ArenaSparks extends CustomPainter {
  const _ArenaSparks(this.progress);
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final pulse = math.sin(math.pi * progress);
    final light = Paint()
      ..color = const Color(0xFFFFC55D).withOpacity(pulse * .9);
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
      oldDelegate.progress != progress;
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
