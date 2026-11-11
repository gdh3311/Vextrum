import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api.dart';
import '../lab_icons.dart';
import '../widgets.dart';

class BattleStage extends StatelessWidget {
  const BattleStage({super.key, required this.teams, required this.active});
  final List<List<Json?>> teams;
  final List<List<int?>> active;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Stack(children: [
        const Positioned.fill(
          child: Image(
              image: AssetImage('assets/battlefield.jpg'),
              fit: BoxFit.cover,
              alignment: Alignment(0, .37),
              excludeFromSemantics: true),
        ),
        const Positioned.fill(
          child: DecoratedBox(
              decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0x4010182D), Color(0x20081424), Color(0xE6091426)],
            ),
          )),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(8, 15, 8, 14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: _side(context, 0, const Color(0xFF80E6DD))),
            const Padding(
              padding: EdgeInsets.only(top: 16),
              child:
                  LabIcon(LabGlyph.versus, color: Color(0xFFFFD178), size: 22),
            ),
            Expanded(child: _side(context, 1, const Color(0xFFFFB1AB))),
          ]),
        ),
      ]),
    );
  }

  Widget _side(BuildContext context, int side, Color tone) {
    final duration = MediaQuery.disableAnimationsOf(context)
        ? Duration.zero
        : const Duration(milliseconds: 240);
    return Column(mainAxisSize: MainAxisSize.min, children: [
      Text(side == 0 ? '내 필드' : '상대 필드',
          style: TextStyle(
              color: tone, fontSize: 12, fontWeight: FontWeight.w700)),
      const SizedBox(height: 4),
      LayoutBuilder(builder: (context, constraints) {
        final count = active[side].length;
        final slotWidth = constraints.maxWidth / math.max(count, 1);
        final size = math.min(slotWidth, 112.0);
        return Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              for (final index in active[side])
                SizedBox(
                  width: size,
                  child: AnimatedSwitcher(
                    duration: duration,
                    transitionBuilder: (child, animation) => FadeTransition(
                      opacity: animation,
                      child: ScaleTransition(
                          scale: Tween(begin: .88, end: 1.0).animate(animation),
                          child: child),
                    ),
                    child: index == null
                        ? SizedBox(
                            key: const ValueKey('vacant'),
                            height: size * .8 + 49)
                        : _BattleFighter(
                            key: ValueKey((side, index)),
                            mon: teams[side][index]!,
                            size: size,
                            tone: tone),
                  ),
                ),
            ]);
      }),
    ]);
  }
}

class _BattleFighter extends StatefulWidget {
  const _BattleFighter(
      {super.key, required this.mon, required this.size, required this.tone});
  final Json mon;
  final double size;
  final Color tone;

  @override
  State<_BattleFighter> createState() => _BattleFighterState();
}

class _BattleFighterState extends State<_BattleFighter> {
  int hit = 0;

  @override
  void didUpdateWidget(covariant _BattleFighter oldWidget) {
    super.didUpdateWidget(oldWidget);
    if ((widget.mon['hp'] as int) < (oldWidget.mon['hp'] as int)) hit++;
  }

  @override
  Widget build(BuildContext context) {
    final mon = widget.mon;
    final reduced = MediaQuery.disableAnimationsOf(context);
    final hp = mon['hp'] as int;
    final max = mon['maxHp'] as int;
    final fraction = (hp / math.max(max, 1)).clamp(0.0, 1.0);
    final size = widget.size;
    final sprite = Stack(alignment: Alignment.bottomCenter, children: [
      Positioned(
        bottom: 5,
        child: Container(
          width: size * .64,
          height: size * .15,
          decoration: BoxDecoration(
            color: widget.tone.withOpacity(.15),
            border: Border.all(color: widget.tone.withOpacity(.42)),
            borderRadius:
                BorderRadius.all(Radius.elliptical(size * .32, size * .09)),
          ),
        ),
      ),
      Sprite(mon['sprite'] as String, size: size * .8),
    ]);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 3),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        if (hit > 0 && !reduced)
          TweenAnimationBuilder<double>(
            key: ValueKey(hit),
            tween: Tween(begin: 1, end: 0),
            duration: const Duration(milliseconds: 370),
            child: sprite,
            builder: (context, value, child) => Transform.translate(
              offset: Offset(math.sin(value * math.pi * 5) * value * 5, 0),
              child: Stack(alignment: Alignment.center, children: [
                child!,
                if (value > .02)
                  IgnorePointer(
                      child: LabIcon(LabGlyph.spark,
                          size: size * .56,
                          color: const Color(0xFFFFD782)
                              .withOpacity(value * .85))),
              ]),
            ),
          )
        else
          sprite,
        Text('${mon['ko'] ?? mon['name']}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        TweenAnimationBuilder<double>(
          tween: Tween(end: fraction),
          duration: reduced ? Duration.zero : const Duration(milliseconds: 430),
          curve: Curves.easeOutCubic,
          builder: (_, value, __) => ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: value,
              minHeight: 5,
              backgroundColor: const Color(0xAA33465D),
              color: value <= .25
                  ? const Color(0xFFFF827B)
                  : value <= .5
                      ? const Color(0xFFFFC36B)
                      : widget.tone,
              semanticsLabel: '${mon['ko'] ?? mon['name']} HP',
              semanticsValue: '$hp / $max',
            ),
          ),
        ),
        Text('$hp / $max',
            style: const TextStyle(color: Color(0xFFDAE7F6), fontSize: 11)),
      ]),
    );
  }
}
