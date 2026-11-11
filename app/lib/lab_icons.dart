import 'dart:math' as math;

import 'package:flutter/material.dart';

enum LabGlyph {
  ball,
  meta,
  team,
  versus,
  crystal,
  archive,
  controller,
  sun,
  moon,
  plus,
  back,
  forward,
  down,
  up,
  cross,
  search,
  spark,
  bolt,
  check,
  cloud,
  swap,
  copy,
  trash,
  download,
  upload,
  pencil,
  note,
  alert,
  info,
  help,
  box,
  stack,
  link,
  lock,
  unlock,
  book,
  dots,
  play,
  save,
  shield,
  star,
  starFill,
  repeat,
  tune,
  addList,
}

class LabIcon extends StatelessWidget {
  const LabIcon(this.glyph,
      {super.key, this.size, this.color, this.semanticLabel});

  final LabGlyph glyph;
  final double? size;
  final Color? color;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final theme = IconTheme.of(context);
    final edge = size ?? theme.size ?? 24;
    final ink = color ?? theme.color ?? Theme.of(context).colorScheme.onSurface;
    return Semantics(
      label: semanticLabel,
      child: CustomPaint(
        size: Size.square(edge),
        painter: _GlyphPainter(
            glyph, ink.withOpacity(ink.opacity * (theme.opacity ?? 1))),
      ),
    );
  }
}

class _GlyphPainter extends CustomPainter {
  const _GlyphPainter(this.glyph, this.color);
  final LabGlyph glyph;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 24, size.height / 24);
    final stroke = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.65
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final fill = Paint()..color = color;
    void path(List<double> xy, {bool closed = false, bool solid = false}) {
      final p = Path()..moveTo(xy[0], xy[1]);
      for (var i = 2; i < xy.length; i += 2) {
        p.lineTo(xy[i], xy[i + 1]);
      }
      if (closed) p.close();
      canvas.drawPath(p, solid ? fill : stroke);
    }

    void circle(double x, double y, double radius, {bool solid = false}) =>
        canvas.drawCircle(Offset(x, y), radius, solid ? fill : stroke);
    void rect(double x, double y, double w, double h, [double r = 1.5]) =>
        canvas.drawRRect(
            RRect.fromRectAndRadius(
                Rect.fromLTWH(x, y, w, h), Radius.circular(r)),
            stroke);
    void arc(double x, double y, double w, double h, double from,
            double sweep) =>
        canvas.drawArc(Rect.fromLTWH(x, y, w, h), from, sweep, false, stroke);
    void ball(double x, double y, double radius) {
      circle(x, y, radius);
      final hub = radius * .28;
      path([x - radius, y, x - hub, y]);
      path([x + hub, y, x + radius, y]);
      circle(x, y, hub);
    }

    switch (glyph) {
      case LabGlyph.ball:
        ball(12, 12, 8.7);
        arc(5.6, 5.6, 12.8, 12.8, math.pi * 1.15, .65);
      case LabGlyph.meta:
        path([
          3,
          20,
          3,
          13,
          8,
          13,
          8,
          20,
          8,
          8,
          15,
          8,
          15,
          20,
          15,
          12,
          21,
          12,
          21,
          20,
          3,
          20
        ]);
        path([9.5, 4.7, 12, 2.8, 14.5, 4.7]);
      case LabGlyph.team:
        ball(12, 7.2, 4.2);
        ball(6.4, 16.2, 4.2);
        ball(17.6, 16.2, 4.2);
      case LabGlyph.versus:
        path([3, 3, 8, 4.5, 17.2, 14.7, 14.6, 17.2, 4.5, 8], closed: true);
        path([21, 3, 19.5, 8, 15.9, 11.6]);
        path([12, 15.9, 7, 21, 3, 17, 8.1, 12]);
        path([14.5, 18.5, 18.5, 14.5, 21, 17, 17, 21]);
      case LabGlyph.crystal:
        path([12, 2.8, 20.5, 9.3, 16.8, 18, 12, 21.3, 7.2, 18, 3.5, 9.3],
            closed: true);
        path([3.5, 9.3, 12, 11.5, 20.5, 9.3]);
        path([12, 2.8, 8.6, 9.8, 12, 21.3, 15.4, 9.8, 12, 2.8]);
      case LabGlyph.archive:
        rect(4, 3.5, 16, 17);
        ball(12, 10, 3.4);
        path([8, 16.7, 16, 16.7]);
      case LabGlyph.controller:
        path([
          6,
          6,
          18,
          6,
          20,
          8,
          21.5,
          16,
          19,
          19,
          15.5,
          15.5,
          8.5,
          15.5,
          5,
          19,
          2.5,
          16,
          4,
          8
        ], closed: true);
        path([5.7, 10.6, 10.4, 10.6]);
        path([8.05, 8.3, 8.05, 13]);
        circle(16, 9.5, 1, solid: true);
        circle(18, 12, 1, solid: true);
      case LabGlyph.sun:
        circle(12, 12, 4.4);
        for (var i = 0; i < 8; i++) {
          final a = i * math.pi / 4;
          path([
            12 + math.cos(a) * 7,
            12 + math.sin(a) * 7,
            12 + math.cos(a) * 9.4,
            12 + math.sin(a) * 9.4
          ]);
        }
      case LabGlyph.moon:
        final p = Path()
          ..moveTo(15.5, 3.6)
          ..cubicTo(4, 1, .8, 15.3, 9.5, 19.7)
          ..cubicTo(14.5, 22.2, 19.5, 19.4, 21, 15)
          ..cubicTo(14, 17, 9.8, 9.7, 15.5, 3.6);
        canvas.drawPath(p, stroke);
      case LabGlyph.plus:
        path([5, 12, 19, 12]);
        path([12, 5, 12, 19]);
      case LabGlyph.back:
        path([11, 5, 4, 12, 11, 19]);
        path([4, 12, 20, 12]);
      case LabGlyph.forward:
        path([13, 5, 20, 12, 13, 19]);
        path([4, 12, 20, 12]);
      case LabGlyph.down:
        path([5, 9, 12, 16, 19, 9]);
      case LabGlyph.up:
        path([5, 15, 12, 8, 19, 15]);
      case LabGlyph.cross:
        path([6, 6, 18, 18]);
        path([18, 6, 6, 18]);
      case LabGlyph.search:
        circle(10.2, 10, 5.8);
        path([14.5, 14.3, 20, 20]);
      case LabGlyph.spark:
        path([
          11,
          2,
          13,
          8.5,
          19.5,
          11,
          13,
          13.5,
          11,
          20,
          8.5,
          13.5,
          2,
          11,
          8.5,
          8.5
        ], closed: true);
        path([19, 15.5, 19, 21.5]);
        path([16, 18.5, 22, 18.5]);
      case LabGlyph.bolt:
        path([13, 2.5, 4.5, 13.4, 11, 13.4, 10, 21.5, 19.5, 10.4, 13, 10.4],
            closed: true);
      case LabGlyph.check:
        path([4.5, 12, 9.4, 17, 19.5, 6.5]);
      case LabGlyph.cloud:
        path([3.5, 5.5, 20.5, 19.5]);
        arc(4, 7, 11, 10, 1.65, 2.7);
        arc(9, 5, 11, 11, 3.9, 2.75);
        path([8, 17, 14, 17]);
      case LabGlyph.swap:
      case LabGlyph.repeat:
        path([3, 8, 20, 8, 16.5, 4.5]);
        path([20, 8, 16.5, 11.5]);
        path([21, 16, 4, 16, 7.5, 12.5]);
        path([4, 16, 7.5, 19.5]);
        if (glyph == LabGlyph.repeat) {
          path([3, 8, 3, 12]);
          path([21, 16, 21, 12]);
        }
      case LabGlyph.copy:
        rect(8, 8, 12, 13);
        path([5, 16, 4, 16, 4, 3.5, 15.5, 3.5, 15.5, 5]);
      case LabGlyph.trash:
        path([4, 6, 20, 6]);
        path([8.5, 6, 9.5, 3.5, 14.5, 3.5, 15.5, 6]);
        path([6.5, 6, 8, 20.5, 16, 20.5, 17.5, 6]);
        path([10, 10, 10.5, 17]);
        path([14, 10, 13.5, 17]);
      case LabGlyph.download:
      case LabGlyph.upload:
        path([4, 15, 4, 20, 20, 20, 20, 15]);
        if (glyph == LabGlyph.download) {
          path([12, 3.5, 12, 15.5]);
          path([7.5, 11, 12, 15.5, 16.5, 11]);
        } else {
          path([12, 15.5, 12, 3.5]);
          path([7.5, 8, 12, 3.5, 16.5, 8]);
        }
      case LabGlyph.pencil:
        path([4, 20, 5.2, 15, 16.5, 3.7, 20.3, 7.5, 9, 18.8], closed: true);
        path([14.2, 6, 18, 9.8]);
      case LabGlyph.note:
        path([13, 4, 4, 4, 4, 20, 17, 20, 17, 15]);
        path([9, 16, 10, 12, 18, 4, 21, 7, 13, 15], closed: true);
      case LabGlyph.alert:
        path([12, 3, 21, 19.5, 3, 19.5], closed: true);
        path([12, 8, 12, 13]);
        circle(12, 16.3, 1, solid: true);
      case LabGlyph.info:
      case LabGlyph.help:
        circle(12, 12, 8.8);
        if (glyph == LabGlyph.help) {
          arc(8.5, 6, 7, 6, math.pi, math.pi * 1.5);
          path([12, 12, 12, 13.7]);
          circle(12, 17, .9, solid: true);
        } else {
          circle(12, 7.8, 1, solid: true);
          path([12, 11, 12, 16.8]);
        }
      case LabGlyph.box:
        path([5, 6, 19, 6, 21, 10, 19, 19, 5, 19, 3, 10], closed: true);
        path([3, 10, 21, 10]);
        path([10, 13, 14, 13]);
      case LabGlyph.stack:
        path([12, 4, 21, 9, 12, 14, 3, 9], closed: true);
        path([3, 13, 12, 18, 21, 13]);
        path([3, 17, 12, 22, 21, 17]);
      case LabGlyph.link:
        path([10, 8, 13.8, 4.2, 17, 4.2, 20, 7.2, 20, 10.3, 16.5, 14]);
        path([7.5, 10, 4, 13.5, 4, 16.8, 7.1, 19.8, 10.3, 19.8, 14, 16]);
        path([8.5, 15.5, 15.5, 8.5]);
      case LabGlyph.lock:
      case LabGlyph.unlock:
        rect(5, 10, 14, 10.5, 2);
        if (glyph == LabGlyph.lock) {
          arc(8, 3, 8, 8, math.pi, math.pi);
          path([8, 7, 8, 10]);
          path([16, 7, 16, 10]);
        } else {
          arc(8, 3, 8, 8, math.pi, math.pi);
          path([8, 7, 8, 10]);
        }
        path([12, 14.2, 12, 16.8]);
      case LabGlyph.book:
        path([
          12,
          7,
          8.5,
          4,
          3.5,
          4,
          3.5,
          18.5,
          8.5,
          18.5,
          12,
          21,
          15.5,
          18.5,
          20.5,
          18.5,
          20.5,
          4,
          15.5,
          4,
          12,
          7,
          12,
          21
        ]);
      case LabGlyph.dots:
        for (final x in [5.5, 12.0, 18.5]) {
          circle(x, 12, 1.5, solid: true);
        }
      case LabGlyph.play:
        path([7, 4.5, 19.5, 12, 7, 19.5], closed: true);
      case LabGlyph.save:
        path([4, 3.5, 17, 3.5, 20, 6.5, 20, 20.5, 4, 20.5], closed: true);
        path([8, 3.5, 8, 9, 15, 9, 15, 3.5]);
        path([8, 20.5, 8, 14, 16, 14, 16, 20.5]);
      case LabGlyph.shield:
        path([
          12,
          3.2,
          20,
          6.5,
          18.8,
          14.5,
          16,
          18.2,
          12,
          21,
          8,
          18.2,
          5.2,
          14.5,
          4,
          6.5
        ], closed: true);
        path([8.5, 12, 11, 14.5, 15.5, 9.8]);
      case LabGlyph.star:
      case LabGlyph.starFill:
        path([
          12,
          3,
          14.6,
          8.8,
          21,
          9.5,
          16.2,
          14,
          17.5,
          20.5,
          12,
          17.1,
          6.5,
          20.5,
          7.8,
          14,
          3,
          9.5,
          9.4,
          8.8
        ], closed: true, solid: glyph == LabGlyph.starFill);
      case LabGlyph.tune:
        path([4, 6, 20, 6]);
        path([4, 12, 20, 12]);
        path([4, 18, 20, 18]);
        path([8, 3.7, 8, 8.3]);
        path([15, 9.7, 15, 14.3]);
        path([10, 15.7, 10, 20.3]);
      case LabGlyph.addList:
        path([3.5, 6.5, 19, 6.5]);
        path([3.5, 11.5, 13, 11.5]);
        path([3.5, 16.5, 10.5, 16.5]);
        path([17, 12.5, 17, 21]);
        path([13, 16.7, 21, 16.7]);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_GlyphPainter oldDelegate) =>
      oldDelegate.glyph != glyph || oldDelegate.color != color;
}
