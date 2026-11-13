/// 팀 자동 구성 진행 화면.
///
/// 서버가 보내는 실제 진행 상황(단계, 진행률, 모의전 수, 지금 보고 있는 포켓몬, 시험 중인 변경)으로
/// 단계마다 다른 장면과 재치 있는 문구를 보여 준다.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart' hide Text, Tooltip;

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../widgets.dart';

const _stageIcons = {
  'research': LabGlyph.book,
  'draft': LabGlyph.team,
  'screen': LabGlyph.versus,
  'refine': LabGlyph.swap,
  'final': LabGlyph.star,
  'tune': LabGlyph.tune,
  'rankers': LabGlyph.crystal,
  'report': LabGlyph.note,
};

/// 단계별 문구. {N} = 스포트라이트 포켓몬, {T} = 메모(실제 데이터), {B} = 모의전 수
const _quips = <String, List<String>>{
  'research': [
    '랭커 노트를 몰래 훔쳐보는 중…',
    '“{T}” 조합이 왜 상위권에 많은지 연구하는 중…',
    '상위 랭커들의 파티를 한 장씩 넘겨보는 중…',
  ],
  'draft': [
    '{N}에게 팀에 들어올 생각이 있는지 묻는 중…',
    '“{T}” 전략에 맞는 6마리를 면접 보는 중…',
    '같은 약점을 가진 지원자 셋은 정중히 돌려보내는 중…',
    '메가스톤을 세 개 들고 온 팀을 설득하는 중…',
  ],
  'screen': [
    '모의전 {B}판째… 아직 아무도 울지 않았습니다',
    '{N} 몸 푸는 중…',
    'CPU가 순풍을 쓸지 진지하게 고민하는 중…',
    '같은 상대·같은 난수로 공정하게 붙이는 중…',
  ],
  'refine': [
    '“{T}” 상대 패배 기록을 보고 다른 멤버를 시험하는 중…',
    '한두 자리를 바꿔 같은 상대군과 다시 겨루는 중…',
    '좋아진 조합을 새 상대군에서 한 번 더 확인하는 중…',
  ],
  'final': [
    '최종 후보들끼리 진검승부 중…',
    '1차 승률 {T}, 진짜 실력인지 다시 확인하는 중…',
    '{N}이(가) 결승전 긴장감을 느끼는 중…',
  ],
  'tune': [
    '시험 중 · {T}',
    '{N}의 가방을 뒤져 도구를 바꿔 보는 중…',
    '능력 포인트를 한 칸씩 다시 찍어 보는 중…',
    '운이 좋았던 건지 진짜 좋아진 건지 새 상대로 확인하는 중…',
  ],
  'rankers': [
    '{T} 님의 파티와 연습 경기 중…',
    '랭커에게 혼나는 중… 이것도 공부입니다',
    '랭커 파티 상대 전적을 적는 중…',
  ],
  'report': [
    '결과를 보기 좋게 정리하는 중…',
    '패배 기록은 작은 글씨로… 농담입니다',
  ],
};

class TeamBuildLoader extends StatefulWidget {
  const TeamBuildLoader({super.key, required this.progress, this.onCancel});

  /// 서버의 진행 상황 (아직 없으면 null)
  final Json? progress;
  final VoidCallback? onCancel;

  @override
  State<TeamBuildLoader> createState() => _TeamBuildLoaderState();
}

class _TeamBuildLoaderState extends State<TeamBuildLoader> with SingleTickerProviderStateMixin {
  late final _clock = AnimationController(vsync: this, duration: const Duration(seconds: 4));
  Timer? _rotate;
  int _tick = 0;
  final _rng = math.Random();

  @override
  void initState() {
    super.initState();
    _rotate = Timer.periodic(const Duration(milliseconds: 2600), (_) {
      if (mounted) setState(() => _tick++);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _clock
        ..stop()
        ..value = 0;
    } else if (!_clock.isAnimating) {
      _clock.repeat();
    }
  }

  @override
  void dispose() {
    _rotate?.cancel();
    _clock.dispose();
    super.dispose();
  }

  String _quip(String stage, List<Json> spotlight, List<String> notes, int battles) {
    final pool = _quips[stage] ?? _quips['screen']!;
    final usable = pool
        .where((q) => (!q.contains('{N}') || spotlight.isNotEmpty) && (!q.contains('{T}') || notes.isNotEmpty))
        .toList();
    final template = usable[_tick % usable.length];
    final name = spotlight.isEmpty ? '' : (spotlight[_tick % spotlight.length]['name'] as String);
    final note = notes.isEmpty ? '' : notes[_tick % notes.length];
    return tr(template)
        .replaceAll('{N}', name)
        .replaceAll('{T}', note)
        .replaceAll('{B}', _thousands(battles));
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final p = widget.progress;
    final stage = (p?['stage'] as String?) ?? 'research';
    final stages = (p?['stages'] as List? ?? const [{'key': 'research', 'label': '랭커 파티 연구'}]).cast<Json>();
    final index = (p?['stageIndex'] as int?) ?? 0;
    final fraction = ((p?['fraction'] as num?) ?? 0).toDouble();
    final battles = (p?['battles'] as int?) ?? 0;
    final spotlight = (p?['spotlight'] as List? ?? const []).cast<Json>();
    final notes = (p?['notes'] as List? ?? const []).cast<String>();
    final elapsed = ((p?['elapsed'] as num?) ?? 0).round();
    final label = stages.length > index ? stages[index]['label'] as String : '';
    final quip = _quip(stage, spotlight, notes, battles);
    return Semantics(
      liveRegion: true,
      label: '$label · $quip',
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        clipBehavior: Clip.antiAlias,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF14253D), Color(0xFF0D1626)],
          ),
          border: Border.all(color: cs.primary.withOpacity(.35)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(
            height: 190,
            child: AnimatedBuilder(
              animation: _clock,
              builder: (context, _) => _Scene(
                stage: stage,
                t: _clock.value,
                spotlight: spotlight,
                notes: notes,
                tick: _tick,
                seed: _rng.hashCode,
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 14),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 380),
                transitionBuilder: (child, a) => FadeTransition(
                  opacity: a,
                  child: SlideTransition(
                      position: Tween(begin: const Offset(0, .35), end: Offset.zero).animate(a), child: child),
                ),
                child: Text(quip,
                    key: ValueKey(quip),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700, height: 1.35)),
              ),
              const SizedBox(height: 12),
              _Steps(stages: stages, index: index),
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: TweenAnimationBuilder<double>(
                  tween: Tween(end: fraction.clamp(0.0, 1.0)),
                  duration: const Duration(milliseconds: 600),
                  builder: (context, v, _) => LinearProgressIndicator(
                    value: v == 0 ? null : v,
                    minHeight: 8,
                    backgroundColor: Colors.white.withOpacity(.08),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                  child: Wrap(spacing: 10, runSpacing: 2, crossAxisAlignment: WrapCrossAlignment.center, children: [
                TweenAnimationBuilder<double>(
                  tween: Tween(end: battles.toDouble()),
                  duration: const Duration(milliseconds: 900),
                  builder: (context, v, _) => Text(
                      tr('모의전 {}판').replaceFirst('{}', _thousands(v.round())),
                      style: const TextStyle(
                          color: Color(0xFFFFD27A),
                          fontWeight: FontWeight.w800,
                          fontFeatures: [FontFeature.tabularFigures()])),
                ),
                Text('${(fraction * 100).round()}% · ${tr('{}초').replaceFirst('{}', '$elapsed')}',
                    style: TextStyle(color: Colors.white.withOpacity(.7), fontSize: 12.5)),
                  ]),
                ),
                if (widget.onCancel != null)
                  TextButton(
                    onPressed: widget.onCancel,
                    child: const Text('그만 보기'),
                  ),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }
}

String _thousands(int n) {
  final s = '$n';
  final out = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) out.write(',');
    out.write(s[i]);
  }
  return out.toString();
}

class _Steps extends StatelessWidget {
  const _Steps({required this.stages, required this.index});
  final List<Json> stages;
  final int index;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Wrap(spacing: 6, runSpacing: 6, children: [
      for (final (i, s) in stages.indexed)
        AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
          decoration: BoxDecoration(
            color: i == index
                ? cs.primary.withOpacity(.25)
                : i < index
                    ? Colors.white.withOpacity(.08)
                    : Colors.transparent,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: i == index ? cs.primary : Colors.white.withOpacity(.15)),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            LabIcon(i < index ? LabGlyph.check : _stageIcons[s['key']] ?? LabGlyph.spark,
                size: 13, color: i <= index ? Colors.white : Colors.white.withOpacity(.45)),
            const SizedBox(width: 4),
            Text(s['label'] as String,
                style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: i == index ? FontWeight.w800 : FontWeight.w500,
                    color: i <= index ? Colors.white : Colors.white.withOpacity(.45))),
          ]),
        ),
    ]);
  }
}

/// 단계마다 다른 장면
class _Scene extends StatelessWidget {
  const _Scene(
      {required this.stage,
      required this.t,
      required this.spotlight,
      required this.notes,
      required this.tick,
      required this.seed});
  final String stage;
  final double t;
  final List<Json> spotlight;
  final List<String> notes;
  final int tick;
  final int seed;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final w = box.maxWidth, h = box.maxHeight;
      return Stack(clipBehavior: Clip.hardEdge, children: [
        Positioned.fill(child: CustomPaint(painter: _Backdrop(t, stage))),
        ...switch (stage) {
          'research' || 'draft' || 'report' => _cards(w, h),
          'tune' => _workshop(w, h),
          _ => _duel(w, h),
        },
      ]);
    });
  }

  /// 초안: 포켓몬 카드가 한 장씩 날아와 자리를 잡는다. 연구: 돋보기가 카드 위를 훑는다.
  List<Widget> _cards(double w, double h) {
    final mons = spotlight.isEmpty ? const <Json>[] : spotlight;
    final n = math.max(1, mons.length);
    final cardW = math.min(84.0, (w - 40) / n - 8);
    final total = n * (cardW + 8) - 8;
    final left = (w - total) / 2;
    final out = <Widget>[];
    for (var i = 0; i < mons.length; i++) {
      // 카드마다 조금씩 늦게 도착한다.
      final arrive = ((t * 1.6 - i * .12) % 1.6).clamp(0.0, 1.0);
      final eased = Curves.easeOutBack.transform(math.min(1, arrive * 2.2));
      final bob = math.sin((t + i * .17) * 2 * math.pi) * 4;
      out.add(Positioned(
        left: left + i * (cardW + 8),
        top: h * .2 + (1 - eased) * -h * .6 + bob,
        width: cardW,
        height: cardW * 1.25,
        child: Transform.rotate(
          angle: (1 - eased) * (i.isEven ? -.5 : .5) + math.sin((t + i * .3) * 2 * math.pi) * .03,
          child: _Card(mon: mons[i], highlight: stage == 'report' || (tick + i) % n == 0),
        ),
      ));
    }
    if (stage == 'research') {
      final x = left + (total - 40) * (.5 + .5 * math.sin(t * 2 * math.pi));
      out.add(Positioned(
        left: x,
        top: h * .25 + 20 * math.cos(t * 4 * math.pi),
        child: const _Magnifier(),
      ));
    }
    return out;
  }

  /// 모의전: 두 진영이 번갈아 돌진하고 가운데서 불꽃이 튄다.
  List<Widget> _duel(double w, double h) {
    final mine = spotlight.take(3).toList();
    final clash = (math.sin(t * 2 * math.pi * 2) + 1) / 2; // 0..1, 1 = 가운데로 돌진
    final hit = clash > .92;
    final out = <Widget>[];
    for (var i = 0; i < mine.length; i++) {
      final dx = w * .1 + i * 34 + clash * w * .14;
      out.add(Positioned(
        left: dx,
        top: h * .3 + i * 18 - (i.isOdd ? clash * 10 : 0),
        child: Sprite(mine[i]['sprite'] as String, size: 72),
      ));
    }
    // 상대: 알 수 없는 도전자들 (몬스터볼 실루엣)
    for (var i = 0; i < 3; i++) {
      final dx = w * .9 - 64 - i * 34 - clash * w * .14;
      out.add(Positioned(
        left: dx,
        top: h * .3 + i * 18 + math.sin((t + i * .2) * 4 * math.pi) * 5,
        child: Opacity(
          opacity: .85,
          child: LabIcon(LabGlyph.ball, size: 46, color: const Color(0xFFFF9E95).withOpacity(.9)),
        ),
      ));
    }
    if (hit) {
      out.add(Positioned(
        left: w / 2 - 40,
        top: h * .28,
        child: const _Spark(),
      ));
    }
    out.add(Positioned(
      left: w / 2 - 22,
      top: 10,
      child: Text(stage == 'rankers' ? 'VS RANKER' : 'VS',
          style: const TextStyle(
              color: Color(0xFFFFD27A), fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: 1)),
    ));
    return out;
  }

  /// 세트 최적화: 가운데 포켓몬 둘레로 시험 중인 변경이 돈다.
  List<Widget> _workshop(double w, double h) {
    final out = <Widget>[];
    final focus = spotlight.isEmpty ? null : spotlight[tick % spotlight.length];
    final cx = w / 2, cy = h * .5;
    final chips = notes.isEmpty ? ['생명의구슬', '기합의띠', '최속', '역린'] : notes;
    final shown = chips.take(5).toList();
    for (var i = 0; i < shown.length; i++) {
      final a = 2 * math.pi * (t + i / shown.length);
      final rx = math.min(w * .36, 260.0), ry = h * .32;
      final text = shown[i].contains(' · ') ? shown[i].split(' · ').last : shown[i];
      out.add(Positioned(
        left: cx + rx * math.cos(a) - 70,
        top: cy + ry * math.sin(a) - 12,
        width: 140,
        child: Opacity(
          opacity: .55 + .45 * (1 + math.sin(a)) / 2,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFF223A5E),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFF7FE6DA).withOpacity(.6)),
              ),
              child: Text(text,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w600)),
            ),
          ),
        ),
      ));
    }
    if (focus != null) {
      out.add(Positioned(
        left: cx - 48,
        top: cy - 52 + math.sin(t * 4 * math.pi) * 4,
        child: Sprite(focus['sprite'] as String, size: 96),
      ));
    }
    // 렌치가 콩콩
    out.add(Positioned(
      left: cx + 34,
      top: cy - 58,
      child: Transform.rotate(
        angle: -.6 + math.sin(t * 8 * math.pi) * .5,
        child: const LabIcon(LabGlyph.tune, size: 26, color: Color(0xFFFFD27A)),
      ),
    ));
    return out;
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.mon, required this.highlight});
  final Json mon;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1E3352),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
            color: highlight ? const Color(0xFFFFD27A) : Colors.white.withOpacity(.18), width: highlight ? 2 : 1),
        boxShadow: [
          if (highlight) BoxShadow(color: const Color(0xFFFFD27A).withOpacity(.35), blurRadius: 14),
        ],
      ),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        Flexible(child: Sprite(mon['sprite'] as String, size: 56)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text(mon['name'] as String,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w700)),
        ),
      ]),
    );
  }
}

class _Magnifier extends StatelessWidget {
  const _Magnifier();
  @override
  Widget build(BuildContext context) => const LabIcon(LabGlyph.search, size: 44, color: Color(0xFFFFD27A));
}

class _Spark extends StatelessWidget {
  const _Spark();
  @override
  Widget build(BuildContext context) => SizedBox(
        width: 80,
        height: 80,
        child: CustomPaint(painter: _SparkPainter()),
      );
}

class _SparkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final paint = Paint()
      ..color = const Color(0xFFFFE08A)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    for (var i = 0; i < 10; i++) {
      final a = i * math.pi / 5;
      final r1 = size.width * .12, r2 = size.width * (i.isEven ? .48 : .32);
      canvas.drawLine(c + Offset(math.cos(a), math.sin(a)) * r1, c + Offset(math.cos(a), math.sin(a)) * r2, paint);
    }
    canvas.drawCircle(c, size.width * .12, Paint()..color = Colors.white);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// 배경: 은은한 경기장 빛과 흘러가는 몬스터볼 줄무늬
class _Backdrop extends CustomPainter {
  _Backdrop(this.t, this.stage);
  final double t;
  final String stage;

  @override
  void paint(Canvas canvas, Size size) {
    final glow = Paint()
      ..shader = RadialGradient(colors: [
        (stage == 'tune' ? const Color(0xFF7FE6DA) : const Color(0xFF5B8CFF)).withOpacity(.22),
        Colors.transparent,
      ]).createShader(Rect.fromCircle(center: Offset(size.width / 2, size.height * .55), radius: size.width * .5));
    canvas.drawRect(Offset.zero & size, glow);
    final line = Paint()
      ..color = Colors.white.withOpacity(.05)
      ..strokeWidth = 18;
    for (var i = -2; i < 12; i++) {
      final x = (i * 90 + t * 90) % (size.width + 180) - 90;
      canvas.drawLine(Offset(x, size.height), Offset(x + 60, 0), line);
    }
    // 바닥 경기장 선
    final floor = Paint()
      ..color = Colors.white.withOpacity(.12)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    canvas.drawOval(
        Rect.fromCenter(center: Offset(size.width / 2, size.height * .9), width: size.width * .8, height: 40),
        floor);
  }

  @override
  bool shouldRepaint(covariant _Backdrop old) => old.t != t || old.stage != stage;
}
