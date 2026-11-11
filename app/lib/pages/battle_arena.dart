/// 가상 배틀의 게임 화면: 원근감 있는 필드, 이름표, 메시지 창, 턴 재생, 명령 패널.
///
/// 서버의 배틀 로그 이벤트에는 그 시점의 HP(`hp`)와 필드 배치(`active`), 행동한 포켓몬(`ref`)이 들어 있다.
/// 새 이벤트가 오면 한 줄씩 재생하면서 기술 모션, 피격, 데미지 숫자, HP 감소, 기절, 교체를 보여 준다.
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart' hide Text, Tooltip;

import '../i18n.dart';
import '../lab_icons.dart';
import '../widgets.dart';
import '../api.dart';

const _ink = Color(0xFF0A1424);
const _hpGood = Color(0xFF3FD68A);
const _hpMid = Color(0xFFF5C451);
const _hpLow = Color(0xFFF2656B);

String _name(Json? mon) => mon == null ? '???' : (mon['ko'] ?? mon['name']) as String;

/// 받침에 맞는 조사 ('이'/'가', '을'/'를', '은'/'는')
String josa(String word, String withBatchim, String without) {
  // '대쓰여너 (수컷)' 처럼 괄호로 끝나면 괄호 앞 이름을 기준으로 한다.
  word = word.replaceAll(RegExp(r'\s*\([^)]*\)\s*$'), '');
  if (word.isEmpty) return without;
  final c = word.codeUnitAt(word.length - 1);
  if (c < 0xAC00 || c > 0xD7A3) return without;
  return (c - 0xAC00) % 28 == 0 ? without : withBatchim;
}

Color _hpColor(double f) => f <= .2 ? _hpLow : f <= .5 ? _hpMid : _hpGood;

const statusLabels = {'brn': '화상', 'par': '마비', 'slp': '잠듦', 'psn': '독', 'tox': '맹독', 'frz': '얼음'};
const statusColors = {
  'brn': Color(0xFFF08030),
  'par': Color(0xFFE8C02A),
  'slp': Color(0xFF9C98B8),
  'psn': Color(0xFFB45AC8),
  'tox': Color(0xFF9B3FB5),
  'frz': Color(0xFF7CD3E0),
};
const _stageLabels = {'atk': '공격', 'def': '방어', 'spa': '특공', 'spd': '특방', 'spe': '스피드'};

class _Burst {
  final int key;
  final int side;
  final int slot;
  final Color color;
  final bool big;
  _Burst(this.key, this.side, this.slot, this.color, this.big);
}

class _Float {
  final int key;
  final int side;
  final int slot;
  final String text;
  final Color color;
  _Float(this.key, this.side, this.slot, this.text, this.color);
}

class BattleArena extends StatefulWidget {
  const BattleArena({
    super.key,
    required this.teams,
    required this.active,
    required this.field,
    required this.events,
    required this.playKey,
    required this.turn,
    this.prompt,
    this.onPlayback,
    this.weather = '',
    this.terrain = '',
  });

  /// 최종 날씨·필드 (sun rain sand snow / psychic grassy electric misty)
  final String weather;
  final String terrain;

  /// 최종 상태 (각 포켓몬의 hp/maxHp 포함). 상대의 미공개 포켓몬은 null.
  final List<List<Json?>> teams;
  final List<List<int?>> active;
  final List<String> field;

  /// 이번에 재생할 새 이벤트. 비어 있으면 최종 상태를 바로 보여 준다.
  final List<Json> events;
  final Object playKey;
  final int turn;

  /// 재생이 끝난 뒤 메시지 창에 띄울 문구 (예: '포푸니크은(는) 무엇을 할까?')
  final String? prompt;
  final ValueChanged<bool>? onPlayback;

  @override
  State<BattleArena> createState() => _BattleArenaState();
}

class _BattleArenaState extends State<BattleArena> {
  late List<List<int>> hp;
  late List<List<int?>> act;
  String? message;
  String? sub;
  Color? tint;
  final lunge = <(int, int), int>{};
  final hit = <(int, int), int>{};
  final fainting = <(int, int)>{};
  final floats = <_Float>[];
  final bursts = <_Burst>[];
  final status = <(int, int), String>{};
  final stages = <(int, int), Map<String, int>>{};
  final mega = <(int, int), int>{};
  String weatherNow = '';
  String terrainNow = '';
  int shake = 0;
  bool bigShake = false;
  int _run = 0;
  int _floatKey = 0;
  bool playing = false;
  bool fast = false;

  @override
  void initState() {
    super.initState();
    if (widget.events.isEmpty) {
      _finalState();
    } else {
      hp = [
        for (final team in widget.teams) [for (final m in team) (m?['maxHp'] as int?) ?? 1]
      ];
      act = [for (final row in widget.active) List<int?>.filled(row.length, null)];
      WidgetsBinding.instance.addPostFrameCallback((_) => _play());
    }
  }

  @override
  void didUpdateWidget(covariant BattleArena old) {
    super.didUpdateWidget(old);
    if (old.playKey != widget.playKey) {
      if (widget.events.isEmpty) {
        _run++;
        setState(_finalState);
      } else {
        WidgetsBinding.instance.addPostFrameCallback((_) => _play());
      }
    }
  }

  @override
  void dispose() {
    _run++;
    super.dispose();
  }

  void _finalState() {
    hp = [
      for (final team in widget.teams) [for (final m in team) (m?['hp'] as int?) ?? 0]
    ];
    act = [for (final row in widget.active) row.toList()];
    fainting.clear();
    floats.clear();
    message = null;
    sub = null;
    tint = null;
    playing = false;
    bursts.clear();
    status.clear();
    stages.clear();
    for (final (side, team) in widget.teams.indexed) {
      for (final (i, m) in team.indexed) {
        if (m == null) continue;
        if ((m['status'] as String? ?? '').isNotEmpty) status[(side, i)] = m['status'] as String;
        final st = (m['stages'] as Map?)?.cast<String, dynamic>();
        if (st != null && st.isNotEmpty) stages[(side, i)] = st.map((k, v) => MapEntry(k, (v as num).toInt()));
      }
    }
    weatherNow = widget.weather;
    terrainNow = widget.terrain;
  }

  void _float(int? side, int? index, String text, Color color) {
    if (side == null || index == null) return;
    final slot = _slotOf(side, index);
    if (slot != null) floats.add(_Float(_floatKey++, side, slot, text, color));
  }

  void _burst(int? side, int? index, Color color, {bool big = false}) {
    if (side == null || index == null) return;
    final slot = _slotOf(side, index);
    if (slot != null) bursts.add(_Burst(_floatKey++, side, slot, color, big));
    if (bursts.length > 6) bursts.removeRange(0, bursts.length - 6);
  }

  int? _slotOf(int side, int index) {
    final i = act[side].indexOf(index);
    return i < 0 ? null : i;
  }

  Json? _mon(List? ref) =>
      ref == null ? null : widget.teams[ref[0] as int][ref[1] as int];

  Future<void> _play() async {
    final run = ++_run;
    final reduced = MediaQuery.disableAnimationsOf(context);
    if (reduced) {
      setState(_finalState);
      widget.onPlayback?.call(false);
      return;
    }
    setState(() => playing = true);
    widget.onPlayback?.call(true);
    for (final e in widget.events) {
      if (!mounted || run != _run) return;
      final ms = _apply(e);
      await Future.delayed(Duration(milliseconds: fast ? ms ~/ 2.4 : ms));
    }
    if (!mounted || run != _run) return;
    setState(_finalState);
    widget.onPlayback?.call(false);
  }

  void _skip() {
    _run++;
    setState(_finalState);
    widget.onPlayback?.call(false);
  }

  /// 이벤트 하나를 화면에 반영하고, 다음 이벤트까지 기다릴 시간을 돌려준다.
  int _apply(Json e) {
    final kind = e['kind'] as String? ?? 'detail';
    final ref = e['ref'] as List?;
    final side = ref?[0] as int?;
    final index = ref?[1] as int?;
    final mon = _mon(ref);
    final name = _name(mon);
    var wait = 720;
    if (kind == 'crit') return 260; // 데미지 줄에서 이미 '급소' 를 보여 준다
    final before = side != null && index != null ? hp[side][index] : null;
    setState(() {
      sub = null;
      tint = null;
      if (e['hp'] is List) {
        final snap = (e['hp'] as List).map((r) => (r as List).cast<int>()).toList();
        // 기절 애니메이션 중인 포켓몬은 자리를 바로 비우지 않는다.
        hp = snap;
      }
      if (e['active'] is List) {
        final next = (e['active'] as List).map((r) => (r as List).cast<int?>()).toList();
        for (var s = 0; s < next.length; s++) {
          for (var i = 0; i < next[s].length && i < act[s].length; i++) {
            final leaving = act[s][i];
            if (leaving != null && next[s][i] != leaving && fainting.contains((s, leaving))) continue;
            act[s][i] = next[s][i];
          }
        }
      }
      switch (kind) {
        case 'move':
          if (side != null && index != null) lunge[(side, index)] = (lunge[(side, index)] ?? 0) + 1;
          message = e['text'] as String;
          tint = typeColor[e['type']];
          _burst(side, index, (tint ?? Colors.white).withOpacity(.85));
          wait = 640;
        case 'damage':
          if (side != null && index != null) {
            hit[(side, index)] = (hit[(side, index)] ?? 0) + 1;
            final slot = _slotOf(side, index);
            final eff = (e['eff'] as num?)?.toDouble() ?? 1;
            if (slot != null) {
              floats.add(_Float(_floatKey++, side, slot, '-${e['pct']}%',
                  eff >= 2 ? const Color(0xFFFFC857) : eff < 1 ? const Color(0xFFB9C6DA) : Colors.white));
            }
            message = '$name${josa(name, '이', '가')} ${e['pct']}%의 피해를 입었다!';
            final crit = e['crit'] == true;
            final effText = eff >= 2 ? '효과가 굉장했다!' : eff > 0 && eff < 1 ? '효과가 별로인 듯하다…' : null;
            sub = [if (crit) '급소에 맞았다!', if (effText != null) effText].join(' ');
            if (sub!.isEmpty) sub = null;
            _burst(side, index, typeColor[e['type']] ?? Colors.white, big: crit || eff >= 2);
            if (crit || eff >= 2) {
              shake++;
              bigShake = crit && eff >= 2;
            }
            if (e['fainted'] == true) {
              fainting.add((side, index));
              sub = '$name${josa(name, '은', '는')} 쓰러졌다!';
              wait = 1150;
            } else {
              wait = 820;
            }
          }
        case 'entry':
          if (side != null && index != null) {
            fainting.removeWhere((f) => f.$1 == side);
            act = (e['active'] as List?)?.map((r) => (r as List).cast<int?>()).toList() ?? act;
            message = side == 0 ? '가랏, $name!' : '상대가 $name${josa(name, '을', '를')} 내보냈다!';
            wait = 760;
          } else {
            message = e['text'] as String;
          }
        case 'withdraw':
          message = side == 0 ? '$name, 돌아와!' : '상대가 $name${josa(name, '을', '를')} 거둬들였다.';
          if (side != null && index != null) stages.remove((side, index));
          wait = 560;
        case 'residual':
          message = e['text'] as String;
          if (side != null && index != null) {
            hit[(side, index)] = (hit[(side, index)] ?? 0) + 1;
            _float(side, index, '-${e['pct']}%', const Color(0xFFD8A6F0));
            if (e['fainted'] == true) {
              fainting.add((side, index));
              sub = '$name${josa(name, '은', '는')} 쓰러졌다!';
              wait = 1100;
            } else {
              wait = 760;
            }
          }
        case 'heal':
          message = e['text'] as String;
          if (side != null && index != null && before != null) {
            final max = (mon?['maxHp'] as int?) ?? 1;
            final gained = hp[side][index] - before;
            if (gained > 0) _float(side, index, '+${(100 * gained / max).round()}%', _hpGood);
            _burst(side, index, _hpGood.withOpacity(.7));
          }
          wait = 720;
        case 'stat':
          message = e['text'] as String;
          if (side != null && index != null) {
            final changed = (e['stages'] as Map?)?.cast<String, dynamic>() ?? const {};
            final now = Map<String, int>.from(stages[(side, index)] ?? const {});
            var up = false;
            for (final MapEntry(:key, :value) in changed.entries) {
              final delta = (value as num).toInt();
              up |= delta > 0;
              now[key] = ((now[key] ?? 0) + delta).clamp(-6, 6);
              if (now[key] == 0) now.remove(key);
            }
            stages[(side, index)] = now;
            _float(side, index, up ? '▲' : '▼', up ? const Color(0xFFFF8A5B) : const Color(0xFF6FA8FF));
            _burst(side, index, (up ? const Color(0xFFFF8A5B) : const Color(0xFF6FA8FF)).withOpacity(.6));
          }
          wait = 640;
        case 'status':
          message = e['text'] as String;
          if (side != null && index != null && e.containsKey('status')) {
            final st = e['status'] as String? ?? '';
            if (st.isEmpty) {
              status.remove((side, index));
            } else {
              status[(side, index)] = st;
              _float(side, index, statusLabels[st] ?? st, statusColors[st] ?? Colors.white);
              _burst(side, index, (statusColors[st] ?? Colors.white).withOpacity(.75));
            }
          }
          wait = 720;
        case 'mega':
          message = e['text'] as String;
          if (side != null && index != null) mega[(side, index)] = (mega[(side, index)] ?? 0) + 1;
          tint = const Color(0xFFE6A6FF);
          wait = 1150;
        case 'miss' || 'blocked' || 'immune':
          message = e['text'] as String;
          if (side != null && index != null) {
            final slot = _slotOf(side, index);
            if (slot != null) {
              floats.add(_Float(_floatKey++, side, slot, kind == 'miss' ? 'MISS' : kind == 'blocked' ? 'GUARD' : '×0',
                  const Color(0xFFB9C6DA)));
            }
          }
          wait = 700;
        default:
          message = e['text'] as String;
          if (e.containsKey('weather')) weatherNow = e['weather'] as String? ?? '';
          if (e.containsKey('terrain')) terrainNow = e['terrain'] as String? ?? '';
          wait = kind == 'field' ? 760 : 680;
      }
      if (floats.length > 8) floats.removeRange(0, floats.length - 8);
    });
    return wait;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final doubles = widget.active[0].length > 1;
    final idleMessage = widget.prompt;
    return ClipRRect(
      borderRadius: BorderRadius.circular(18),
      child: Column(children: [
        LayoutBuilder(builder: (context, c) {
          final w = c.maxWidth;
          final h = (w * .5).clamp(300.0, 470.0);
          final compact = w < 560;
          final foeSize = h * (doubles ? .29 : .33);
          final mySize = h * (doubles ? .40 : .46);
          Offset spot(int side, int slot) {
            final count = widget.active[side].length;
            if (side == 1) {
              final x = count == 1 ? .72 : .61 + slot * .2;
              return Offset(w * x, h * .47);
            }
            final x = count == 1 ? .28 : .18 + slot * .23;
            return Offset(w * x, h * .97);
          }

          final scene = SizedBox(
            height: h,
            child: Stack(clipBehavior: Clip.none, children: [
              const Positioned.fill(
                child: Image(
                    image: AssetImage('assets/battlefield.jpg'),
                    fit: BoxFit.cover,
                    alignment: Alignment(0, .4),
                    excludeFromSemantics: true),
              ),
              const Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Color(0x66081222), Color(0x10081222), Color(0x55081222)],
                      stops: [0, .55, 1],
                    ),
                  ),
                ),
              ),
              if (terrainNow.isNotEmpty) Positioned.fill(child: IgnorePointer(child: _TerrainLayer(terrainNow))),
              // 발판
              _Platform(center: Offset(w * .72, h * .47), width: w * .42, height: h * .1, tone: const Color(0xFFFF9E95)),
              _Platform(center: Offset(w * .29, h * .96), width: w * .56, height: h * .13, tone: const Color(0xFF7FE6DA)),
              // 포켓몬 (먼 쪽부터 그린다)
              for (final side in const [1, 0])
                for (var slot = 0; slot < act[side].length; slot++)
                  if (act[side][slot] case final index?)
                    if (widget.teams[side][index] case final mon?)
                      Positioned(
                        left: spot(side, slot).dx - (side == 1 ? foeSize : mySize) / 2,
                        top: spot(side, slot).dy - (side == 1 ? foeSize : mySize) * .92,
                        width: side == 1 ? foeSize : mySize,
                        height: side == 1 ? foeSize : mySize,
                        child: _Fighter(
                          key: ValueKey(('f', side, index)),
                          sprite: mon['sprite'] as String,
                          mirrored: side == 0,
                          towards: side == 0 ? const Offset(1, -.6) : const Offset(-1, .6),
                          lunge: lunge[(side, index)] ?? 0,
                          hit: hit[(side, index)] ?? 0,
                          mega: mega[(side, index)] ?? 0,
                          fainting: fainting.contains((side, index)),
                          asleep: status[(side, index)] == 'slp' || status[(side, index)] == 'frz',
                        ),
                      ),
              // 기술 이펙트
              for (final b in bursts)
                if (b.slot < act[b.side].length)
                  Positioned(
                    key: ValueKey(('burst', b.key)),
                    left: spot(b.side, b.slot).dx - (b.side == 1 ? foeSize : mySize) * .7,
                    top: spot(b.side, b.slot).dy - (b.side == 1 ? foeSize : mySize) * 1.15,
                    width: (b.side == 1 ? foeSize : mySize) * 1.4,
                    height: (b.side == 1 ? foeSize : mySize) * 1.4,
                    child: IgnorePointer(child: _BurstView(b.color, big: b.big)),
                  ),
              if (weatherNow.isNotEmpty) Positioned.fill(child: IgnorePointer(child: _WeatherLayer(weatherNow))),
              // 데미지 숫자
              for (final f in floats)
                if (f.slot < act[f.side].length)
                  Positioned(
                    key: ValueKey(('float', f.key)),
                    left: spot(f.side, f.slot).dx - 60,
                    top: spot(f.side, f.slot).dy - (f.side == 1 ? foeSize : mySize) * .95,
                    width: 120,
                    child: _FloatText(f.text, f.color),
                  ),
              // 상대 이름표 (왼쪽 위)
              Positioned(
                left: 12,
                top: 12,
                width: math.min(compact ? w * .5 : 270.0, w * .48),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  for (var slot = 0; slot < act[1].length; slot++)
                    if (act[1][slot] case final index?)
                      if (widget.teams[1][index] case final mon?)
                        _Plate(
                            mon: mon,
                            hp: hp[1][index],
                            mine: false,
                            compact: compact,
                            status: status[(1, index)],
                            stages: stages[(1, index)]),
                ]),
              ),
              // 내 이름표 (오른쪽 아래)
              Positioned(
                right: 12,
                bottom: 12,
                width: math.min(compact ? w * .5 : 290.0, w * .48),
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
                  for (var slot = 0; slot < act[0].length; slot++)
                    if (act[0][slot] case final index?)
                      if (widget.teams[0][index] case final mon?)
                        _Plate(
                            mon: mon,
                            hp: hp[0][index],
                            mine: true,
                            compact: compact,
                            status: status[(0, index)],
                            stages: stages[(0, index)]),
                ]),
              ),
              // 턴과 필드 상태 (오른쪽 위)
              Positioned(
                right: 12,
                top: 12,
                child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  _Badge(text: '${widget.turn}턴', color: const Color(0xFFFFD27A), bold: true),
                  for (final f in widget.field) ...[const SizedBox(height: 5), _Badge(text: f, color: const Color(0xFF9FD8FF))],
                ]),
              ),
            ]),
          );
          // 급소·효과 굉장 시 화면 흔들림
          return TweenAnimationBuilder<double>(
            key: ValueKey(('shake', shake)),
            tween: Tween(begin: shake == 0 ? 1 : 0, end: 1),
            duration: const Duration(milliseconds: 420),
            builder: (_, v, child) => Transform.translate(
              offset: Offset(math.sin(v * math.pi * 9) * (1 - v) * (bigShake ? 11 : 6),
                  math.cos(v * math.pi * 7) * (1 - v) * (bigShake ? 5 : 2.5)),
              child: child,
            ),
            child: scene,
          );
        }),
        // 메시지 창
        Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 70),
          padding: const EdgeInsets.fromLTRB(18, 12, 12, 12),
          decoration: BoxDecoration(
            color: _ink,
            border: Border(top: BorderSide(color: (tint ?? cs.primary).withOpacity(.9), width: 3)),
          ),
          child: Row(children: [
            Expanded(
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 160),
                layoutBuilder: (current, previous) =>
                    Align(alignment: Alignment.centerLeft, child: current ?? const SizedBox.shrink()),
                transitionBuilder: (child, a) => FadeTransition(
                    opacity: a,
                    child: SlideTransition(
                        position: Tween(begin: const Offset(0, .25), end: Offset.zero).animate(a), child: child)),
                child: Column(
                  key: ValueKey('$message|$sub|$idleMessage|$playing'),
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _Typewriter(message ?? idleMessage ?? '',
                        animate: playing && message != null,
                        style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600, height: 1.35)),
                    if (sub != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(sub!,
                            style: const TextStyle(color: Color(0xFFFFD27A), fontSize: 14, fontWeight: FontWeight.w600)),
                      ),
                  ],
                ),
              ),
            ),
            if (playing) ...[
              TextButton(
                onPressed: () => setState(() => fast = !fast),
                style: TextButton.styleFrom(foregroundColor: Colors.white70),
                child: Text(fast ? '2×' : '1×', style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              TextButton.icon(
                onPressed: _skip,
                style: TextButton.styleFrom(foregroundColor: Colors.white70),
                icon: const Icon(Icons.fast_forward_rounded, size: 18),
                label: const Text('건너뛰기'),
              ),
            ] else
              const _Blink(),
          ]),
        ),
      ]),
    );
  }
}

class _Platform extends StatelessWidget {
  const _Platform({required this.center, required this.width, required this.height, required this.tone});
  final Offset center;
  final double width;
  final double height;
  final Color tone;
  @override
  Widget build(BuildContext context) => Positioned(
        left: center.dx - width / 2,
        top: center.dy - height / 2,
        width: width,
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.all(Radius.elliptical(width / 2, height / 2)),
            gradient: RadialGradient(colors: [tone.withOpacity(.28), tone.withOpacity(.06)]),
            border: Border.all(color: tone.withOpacity(.45), width: 1.5),
          ),
        ),
      );
}

class _Fighter extends StatelessWidget {
  const _Fighter({
    super.key,
    required this.sprite,
    required this.mirrored,
    required this.towards,
    required this.lunge,
    required this.hit,
    required this.fainting,
    this.mega = 0,
    this.asleep = false,
  });
  final String sprite;
  final bool mirrored;
  final Offset towards;
  final int lunge;
  final int hit;
  final bool fainting;
  final int mega;
  final bool asleep;

  @override
  Widget build(BuildContext context) {
    Widget art = LayoutBuilder(
        builder: (context, c) => Sprite(sprite, size: c.maxWidth));
    if (mirrored) art = Transform.flip(flipX: true, child: art);
    // 숨쉬기: 가만히 있을 때도 살짝 움직인다 (잠듦·얼음이면 멈춤)
    art = _Idle(seed: sprite.hashCode, still: asleep, child: art);
    // 등장: 몬스터볼에서 나오듯 하얗게 빛나며 커진다
    art = TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 620),
      curve: Curves.easeOut,
      builder: (_, v, child) {
        final grow = Curves.easeOutBack.transform((v / .6).clamp(0.0, 1.0));
        final white = (1 - (v - .35) / .65).clamp(0.0, 1.0);
        return Opacity(
          opacity: (v * 3).clamp(0.0, 1.0),
          child: Transform.scale(
            scale: .2 + .8 * grow,
            alignment: Alignment.bottomCenter,
            child: ColorFiltered(
              colorFilter: ColorFilter.mode(Colors.white.withOpacity(white), BlendMode.srcATop),
              child: child,
            ),
          ),
        );
      },
      child: art,
    );
    // 메가진화: 무지개빛 고리와 함께 빛난다
    if (mega > 0) {
      art = TweenAnimationBuilder<double>(
        key: ValueKey(('mega', mega)),
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 1100),
        builder: (_, v, child) {
          final glow = math.sin(v * math.pi);
          return Stack(clipBehavior: Clip.none, alignment: Alignment.center, children: [
            if (v < 1)
              Transform.scale(
                scale: .6 + v * .9,
                child: Opacity(
                  opacity: glow,
                  child: const DecoratedBox(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: SweepGradient(colors: [
                        Color(0xFFFF6B9A), Color(0xFFFFD36B), Color(0xFF6BFFB5),
                        Color(0xFF6BC8FF), Color(0xFFB66BFF), Color(0xFFFF6B9A),
                      ]),
                    ),
                    child: SizedBox.expand(),
                  ),
                ),
              ),
            ColorFiltered(
              colorFilter: ColorFilter.mode(Colors.white.withOpacity(glow * .85), BlendMode.srcATop),
              child: child,
            ),
          ]);
        },
        child: art,
      );
    }
    // 기술 사용: 상대 쪽으로 돌진
    art = TweenAnimationBuilder<double>(
      key: ValueKey(('lunge', lunge)),
      tween: Tween(begin: lunge == 0 ? 1 : 0, end: 1),
      duration: const Duration(milliseconds: 420),
      builder: (_, v, child) {
        final t = math.sin(v * math.pi);
        return Transform.translate(offset: towards * (t * 22), child: child);
      },
      child: art,
    );
    // 피격: 흔들림 + 깜빡임
    art = TweenAnimationBuilder<double>(
      key: ValueKey(('hit', hit)),
      tween: Tween(begin: hit == 0 ? 1 : 0, end: 1),
      duration: const Duration(milliseconds: 520),
      builder: (_, v, child) {
        final shake = math.sin(v * math.pi * 7) * (1 - v) * 9;
        final blink = v < 1 && (v * 8).floor().isOdd;
        return Transform.translate(
          offset: Offset(shake, 0),
          child: Opacity(opacity: blink ? .35 : 1, child: child),
        );
      },
      child: art,
    );
    // 기절: 아래로 가라앉으며 사라짐
    return AnimatedSlide(
      offset: fainting ? const Offset(0, .45) : Offset.zero,
      duration: const Duration(milliseconds: 650),
      curve: Curves.easeIn,
      child: AnimatedOpacity(
        opacity: fainting ? 0 : 1,
        duration: const Duration(milliseconds: 650),
        child: art,
      ),
    );
  }
}

class _FloatText extends StatelessWidget {
  const _FloatText(this.text, this.color);
  final String text;
  final Color color;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 1100),
        curve: Curves.easeOut,
        builder: (_, v, child) => Opacity(
          opacity: v < .75 ? 1 : (1 - v) * 4,
          child: Transform.translate(offset: Offset(0, -34 * v), child: child),
        ),
        child: Center(
          child: Text(text,
              style: TextStyle(
                color: color,
                fontSize: 22,
                fontWeight: FontWeight.w800,
                shadows: const [Shadow(color: Colors.black, blurRadius: 6), Shadow(color: Colors.black, blurRadius: 2)],
              )),
        ),
      );
}

class _Plate extends StatelessWidget {
  const _Plate(
      {required this.mon, required this.hp, required this.mine, required this.compact, this.status, this.stages});
  final Json mon;
  final int hp;
  final bool mine;
  final bool compact;
  final String? status;
  final Map<String, int>? stages;

  @override
  Widget build(BuildContext context) {
    final max = (mon['maxHp'] as int?) ?? 1;
    final frac = (hp / math.max(max, 1)).clamp(0.0, 1.0);
    final fainted = hp <= 0;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 300),
      opacity: fainted ? .45 : 1,
      child: Container(
        margin: const EdgeInsets.only(bottom: 6),
        padding: EdgeInsets.fromLTRB(12, compact ? 6 : 8, 12, compact ? 7 : 9),
        decoration: BoxDecoration(
          color: _ink.withOpacity(.86),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(mine ? 14 : 4),
            bottomLeft: Radius.circular(mine ? 14 : 4),
            topRight: Radius.circular(mine ? 4 : 14),
            bottomRight: Radius.circular(mine ? 4 : 14),
          ),
          border: Border.all(color: Colors.white.withOpacity(.12)),
          boxShadow: const [BoxShadow(color: Color(0x66000000), blurRadius: 10, offset: Offset(0, 3))],
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            Expanded(
              child: Text(_name(mon),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: Colors.white, fontSize: compact ? 13 : 14.5, fontWeight: FontWeight.w700)),
            ),
            if (mon['mega'] == true)
              const Padding(
                padding: EdgeInsets.only(left: 4),
                child: Icon(Icons.auto_awesome_rounded, size: 14, color: Color(0xFFE6A6FF)),
              ),
            for (final t in (mon['types'] as List? ?? const []))
              Padding(padding: const EdgeInsets.only(left: 4), child: TypeDot(t as String)),
            const SizedBox(width: 6),
            Text('Lv.50', style: TextStyle(color: Colors.white.withOpacity(.6), fontSize: 11.5)),
          ]),
          const SizedBox(height: 5),
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: BoxDecoration(color: const Color(0xFFFFC857), borderRadius: BorderRadius.circular(3)),
              child: const Text('HP', style: TextStyle(color: _ink, fontSize: 9.5, fontWeight: FontWeight.w900, height: 1.1)),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: TweenAnimationBuilder<double>(
                tween: Tween(end: frac.toDouble()),
                duration: const Duration(milliseconds: 650),
                curve: Curves.easeOutCubic,
                builder: (_, v, __) => Container(
                  height: 8,
                  decoration: BoxDecoration(color: const Color(0xFF26354B), borderRadius: BorderRadius.circular(5)),
                  alignment: Alignment.centerLeft,
                  child: FractionallySizedBox(
                    widthFactor: v,
                    child: Container(
                      decoration: BoxDecoration(
                        color: _hpColor(v),
                        borderRadius: BorderRadius.circular(5),
                        boxShadow: [BoxShadow(color: _hpColor(v).withOpacity(.5), blurRadius: 6)],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ]),
          const SizedBox(height: 3),
          Row(children: [
            if (status != null && status!.isNotEmpty)
              Container(
                margin: const EdgeInsets.only(right: 4),
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(color: statusColors[status] ?? Colors.grey, borderRadius: BorderRadius.circular(4)),
                child: Text(statusLabels[status] ?? status!,
                    style: const TextStyle(color: _ink, fontSize: 10, fontWeight: FontWeight.w900, height: 1.2)),
              ),
            for (final MapEntry(:key, :value) in (stages ?? const <String, int>{}).entries)
              if (value != 0 && !compact || value != 0 && (stages!.length <= 2))
                Container(
                  margin: const EdgeInsets.only(right: 3),
                  padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                  decoration: BoxDecoration(
                    color: (value > 0 ? const Color(0xFFFF8A5B) : const Color(0xFF6FA8FF)).withOpacity(.22),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(color: value > 0 ? const Color(0xFFFF8A5B) : const Color(0xFF6FA8FF), width: .8),
                  ),
                  child: Text('${_stageLabels[key] ?? key}${value > 0 ? '+' : ''}$value',
                      style: TextStyle(
                          color: value > 0 ? const Color(0xFFFFB79A) : const Color(0xFFA9C8FF),
                          fontSize: 9.5,
                          fontWeight: FontWeight.w800,
                          height: 1.2)),
                ),
            const Spacer(),
            TweenAnimationBuilder<double>(
              tween: Tween(end: hp.toDouble()),
              duration: const Duration(milliseconds: 650),
              builder: (_, v, __) => Text(
                mine ? '${v.round()} / $max' : '${(100 * v / math.max(max, 1)).round()}%',
                style: TextStyle(
                    color: Colors.white.withOpacity(.85),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    fontFeatures: const [FontFeature.tabularFigures()]),
              ),
            ),
          ]),
        ]),
      ),
    );
  }
}

/// 가만히 있을 때의 숨쉬기 모션
class _Idle extends StatefulWidget {
  const _Idle({required this.seed, required this.still, required this.child});
  final int seed;
  final bool still;
  final Widget child;
  @override
  State<_Idle> createState() => _IdleState();
}

class _IdleState extends State<_Idle> with SingleTickerProviderStateMixin {
  late final c = AnimationController(
      vsync: this, duration: Duration(milliseconds: 2000 + widget.seed.abs() % 700))
    ..value = (widget.seed.abs() % 100) / 100
    ..repeat(reverse: true);

  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.still || MediaQuery.disableAnimationsOf(context)) return widget.child;
    return AnimatedBuilder(
      animation: c,
      builder: (_, child) {
        final t = Curves.easeInOut.transform(c.value);
        return Transform(
          alignment: Alignment.bottomCenter,
          transform: Matrix4.identity()
            ..translate(0.0, -2.5 * t)
            ..scale(1.0, 1 + .018 * t),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}

/// 기술 적중·상태 변화 이펙트: 퍼지는 빛 + 고리 + 빛줄기
class _BurstView extends StatelessWidget {
  const _BurstView(this.color, {this.big = false});
  final Color color;
  final bool big;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: Duration(milliseconds: big ? 620 : 480),
        curve: Curves.easeOut,
        builder: (_, v, __) => CustomPaint(painter: _BurstPainter(v, color, big)),
      );
}

class _BurstPainter extends CustomPainter {
  _BurstPainter(this.t, this.color, this.big);
  final double t;
  final Color color;
  final bool big;

  @override
  void paint(Canvas canvas, Size size) {
    if (t >= 1) return;
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final fade = 1 - t;
    canvas.drawCircle(
        c,
        r * (.25 + .55 * t),
        Paint()
          ..shader = RadialGradient(colors: [color.withOpacity(.75 * fade), color.withOpacity(0)])
              .createShader(Rect.fromCircle(center: c, radius: r * (.25 + .55 * t))));
    canvas.drawCircle(
        c,
        r * (.15 + .8 * t),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = (big ? 5 : 3) * fade
          ..color = Colors.white.withOpacity(.8 * fade));
    final rays = big ? 12 : 8;
    final ray = Paint()
      ..strokeWidth = (big ? 4 : 2.5) * fade
      ..strokeCap = StrokeCap.round
      ..color = color.withOpacity(fade);
    for (var i = 0; i < rays; i++) {
      final a = i * 2 * math.pi / rays + t * .6;
      final from = r * (.2 + .5 * t), to = r * (.35 + .65 * t);
      canvas.drawLine(c + Offset(math.cos(a), math.sin(a)) * from, c + Offset(math.cos(a), math.sin(a)) * to, ray);
    }
  }

  @override
  bool shouldRepaint(_BurstPainter old) => old.t != t;
}

/// 날씨 오버레이: 비 · 쾌청 · 모래바람 · 눈
class _WeatherLayer extends StatefulWidget {
  const _WeatherLayer(this.weather);
  final String weather;
  @override
  State<_WeatherLayer> createState() => _WeatherLayerState();
}

class _WeatherLayerState extends State<_WeatherLayer> with SingleTickerProviderStateMixin {
  late final c = AnimationController(vsync: this, duration: const Duration(seconds: 6))..repeat();
  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final still = MediaQuery.disableAnimationsOf(context);
    return AnimatedBuilder(
      animation: c,
      builder: (_, __) => CustomPaint(painter: _WeatherPainter(widget.weather, still ? 0 : c.value)),
    );
  }
}

class _WeatherPainter extends CustomPainter {
  _WeatherPainter(this.weather, this.t);
  final String weather;
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final rng = math.Random(7);
    switch (weather) {
      case 'rain':
        canvas.drawRect(rect, Paint()..color = const Color(0x332A4A7A));
        final p = Paint()
          ..color = const Color(0x88CFE6FF)
          ..strokeWidth = 1.4
          ..strokeCap = StrokeCap.round;
        for (var i = 0; i < 90; i++) {
          final x0 = rng.nextDouble() * (size.width + 80);
          final speed = 1 + rng.nextDouble();
          final y = ((rng.nextDouble() + t * 6 * speed) % 1) * (size.height + 40) - 20;
          final x = x0 - y * .25;
          canvas.drawLine(Offset(x, y), Offset(x - 5, y + 18), p);
        }
      case 'sun':
        canvas.drawRect(
            rect,
            Paint()
              ..shader = RadialGradient(
                center: const Alignment(.8, -1.1),
                radius: 1.3,
                colors: [
                  Color.fromRGBO(255, 214, 120, .42 + .08 * math.sin(t * 2 * math.pi * 3)),
                  const Color(0x10FFB347),
                  const Color(0x00FFB347),
                ],
                stops: const [0, .55, 1],
              ).createShader(rect));
      case 'sand':
        canvas.drawRect(rect, Paint()..color = const Color(0x40B08850));
        final p = Paint()..color = const Color(0x99E2C48E);
        for (var i = 0; i < 120; i++) {
          final speed = 1 + rng.nextDouble() * 2;
          final x = ((rng.nextDouble() + t * 4 * speed) % 1) * (size.width + 40) - 20;
          final y = rng.nextDouble() * size.height + math.sin(t * 20 + i) * 6;
          canvas.drawCircle(Offset(x, y), .8 + rng.nextDouble() * 1.6, p);
        }
      case 'snow':
        canvas.drawRect(rect, Paint()..color = const Color(0x26DDEEFF));
        final p = Paint()..color = const Color(0xCCFFFFFF);
        for (var i = 0; i < 70; i++) {
          final speed = .5 + rng.nextDouble();
          final y = ((rng.nextDouble() + t * 2 * speed) % 1) * (size.height + 20) - 10;
          final x = rng.nextDouble() * size.width + math.sin(t * 2 * math.pi * 2 + i) * 10;
          canvas.drawCircle(Offset(x, y), 1.2 + rng.nextDouble() * 2, p);
        }
    }
  }

  @override
  bool shouldRepaint(_WeatherPainter old) => old.t != t || old.weather != weather;
}

/// 필드(테레인): 바닥에 깔리는 빛
class _TerrainLayer extends StatelessWidget {
  const _TerrainLayer(this.terrain);
  final String terrain;
  @override
  Widget build(BuildContext context) {
    final color = switch (terrain) {
      'psychic' => const Color(0xFFE86BD8),
      'grassy' => const Color(0xFF5FD068),
      'electric' => const Color(0xFFF5D547),
      _ => const Color(0xFFF7A8D8),
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.bottomCenter,
          end: Alignment.topCenter,
          colors: [color.withOpacity(.38), color.withOpacity(.12), color.withOpacity(0)],
          stops: const [0, .35, .6],
        ),
      ),
    );
  }
}

/// 메시지를 한 글자씩 보여 준다 (게임 대사창처럼)
class _Typewriter extends StatelessWidget {
  const _Typewriter(this.text, {required this.style, this.animate = true});
  final String text;
  final TextStyle style;
  final bool animate;
  @override
  Widget build(BuildContext context) {
    final shown = tr(text);
    if (!animate || MediaQuery.disableAnimationsOf(context)) return Text(text, style: style);
    return TweenAnimationBuilder<double>(
      key: ValueKey(shown),
      tween: Tween(begin: 0, end: 1),
      duration: Duration(milliseconds: (shown.length * 13).clamp(120, 420)),
      builder: (_, v, __) => Stack(children: [
        // 줄바꿈이 흔들리지 않도록 전체 문장 자리를 먼저 잡는다
        Opacity(opacity: 0, child: Text(shown, style: style)),
        Text(shown.substring(0, (shown.length * v).round()), style: style),
      ]),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, required this.color, this.bold = false});
  final String text;
  final Color color;
  final bool bold;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: _ink.withOpacity(.8),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withOpacity(.55)),
        ),
        child: Text(text,
            style: TextStyle(color: color, fontSize: 12, fontWeight: bold ? FontWeight.w800 : FontWeight.w600)),
      );
}

/// 입력 대기 중임을 알리는 깜빡이는 삼각형
class _Blink extends StatefulWidget {
  const _Blink();
  @override
  State<_Blink> createState() => _BlinkState();
}

class _BlinkState extends State<_Blink> with SingleTickerProviderStateMixin {
  late final c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
  @override
  void dispose() {
    c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: .25, end: 1.0).animate(c),
        child: const Padding(
          padding: EdgeInsets.only(right: 6),
          child: Icon(Icons.arrow_drop_down_rounded, color: Color(0xFFFFD27A), size: 30),
        ),
      );
}

// ===================================================================== 명령 패널

/// 한 포켓몬의 명령 선택: 2×2 기술 버튼(타입 색), 대상 선택(상성 표시), 교체 목록.
class GameCommandPanel extends StatefulWidget {
  const GameCommandPanel({
    super.key,
    required this.mon,
    required this.options,
    required this.selected,
    required this.foes,
    required this.team,
    required this.reserved,
    required this.onSelected,
  });

  final Json mon;
  final List<Json> options;
  final Json? selected;

  /// 상대 자리 번호 → 포켓몬
  final Map<int, Json> foes;

  /// 내 팀 전체 (교체 대상 표시용)
  final List<Json?> team;
  final Set<int> reserved;
  final ValueChanged<Json?>? onSelected;

  @override
  State<GameCommandPanel> createState() => _GameCommandPanelState();
}

class _GameCommandPanelState extends State<GameCommandPanel> {
  String? move;
  bool switching = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final moves = <String, List<Json>>{};
    final swaps = <Json>[];
    Json? wait;
    for (final o in widget.options) {
      if (o['kind'] == 'switch') {
        swaps.add(o);
      } else if (o['kind'] == 'wait') {
        wait = o;
      } else {
        moves.putIfAbsent(o['move'] as String, () => []).add(o);
      }
    }
    final selected = widget.selected;
    final enabled = widget.onSelected != null;
    final candidates = moves[move] ?? const <Json>[];
    final hp = widget.mon['hp'] as int? ?? 0;
    final maxHp = widget.mon['maxHp'] as int? ?? 1;
    final name = _name(widget.mon);

    void pickMove(String key) {
      final list = moves[key]!;
      setState(() {
        move = key;
        switching = false;
      });
      if (list.length == 1) {
        widget.onSelected!(list.single);
      } else if (selected?['move'] != key) {
        widget.onSelected!(null);
      }
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: selected != null ? cs.primary.withOpacity(.7) : cs.outlineVariant, width: 1.4),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Sprite(widget.mon['sprite'] as String, size: 40),
          const SizedBox(width: 8),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('$name${josa(name, '은', '는')} 무엇을 할까?',
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              SizedBox(
                width: 160,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                      value: (hp / math.max(maxHp, 1)).clamp(0.0, 1.0),
                      minHeight: 5,
                      color: _hpColor(hp / math.max(maxHp, 1))),
                ),
              ),
            ]),
          ),
          if (selected != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              decoration: BoxDecoration(color: cs.primary.withOpacity(.16), borderRadius: BorderRadius.circular(20)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.check_rounded, size: 16, color: cs.primary),
                const SizedBox(width: 4),
                Text(_summary(selected), style: TextStyle(fontSize: 13, color: cs.primary, fontWeight: FontWeight.w600)),
              ]),
            ),
        ]),
        const SizedBox(height: 12),
        if (wait != null)
          _MoveButton(
              label: wait['label'] as String,
              type: null,
              detail: '',
              selected: identical(selected, wait),
              onTap: enabled ? () => widget.onSelected!(wait) : null)
        else
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 520 ? 2 : 1;
            final w = (c.maxWidth - (cols - 1) * 8) / cols;
            return Wrap(spacing: 8, runSpacing: 8, children: [
              for (final entry in moves.entries)
                SizedBox(
                  width: w,
                  child: _MoveButton(
                    label: entry.value.first['label'] as String,
                    type: entry.value.first['type'] as String?,
                    detail: _detail(entry.value.first),
                    selected: !switching && (selected?['move'] == entry.key || (selected == null && move == entry.key)),
                    onTap: enabled ? () => pickMove(entry.key) : null,
                  ),
                ),
            ]);
          }),
        if (!switching && candidates.length > 1) ...[
          const SizedBox(height: 12),
          Text('대상 선택', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant, fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final o in candidates)
              _TargetButton(
                mon: widget.foes[o['target']],
                eff: (o['eff'] as num?)?.toDouble(),
                selected: identical(selected, o),
                onTap: enabled ? () => widget.onSelected!(o) : null,
              ),
          ]),
        ],
        if (swaps.isNotEmpty) ...[
          const SizedBox(height: 10),
          Row(children: [
            TextButton.icon(
              onPressed: !enabled
                  ? null
                  : () {
                      setState(() => switching = !switching);
                      if (!switching && selected?['kind'] == 'switch') widget.onSelected!(null);
                    },
              icon: LabIcon(LabGlyph.swap, size: 16, color: switching ? cs.primary : null),
              label: Text(switching ? '취소' : '포켓몬 교체'),
            ),
          ]),
          if (switching)
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final o in swaps)
                if (widget.team[o['target'] as int] case final m?)
                  _BenchButton(
                    mon: m,
                    selected: identical(selected, o),
                    onTap: !enabled || widget.reserved.contains(o['target']) ? null : () => widget.onSelected!(o),
                  ),
            ]),
        ],
      ]),
    );
  }

  String _detail(Json o) {
    final cat = o['category'] as String?;
    return [
      if (cat != null) tr(categoryKo[cat] ?? cat),
      if ((o['power'] as num? ?? 0) > 0) tr('위력 {}').replaceFirst('{}', '${o['power']}'),
      if ((o['priority'] as int? ?? 0) > 0) tr('우선도 +{}').replaceFirst('{}', '${o['priority']}'),
      if (o['scope'] == 'all') tr('아군도 맞음'),
      if (o['scope'] == 'foes') tr('상대 전체'),
      if (o['pivot'] == true) tr('기술 후 교체'),
    ].join(' · ');
  }

  String _summary(Json o) {
    if (o['kind'] == 'switch') {
      return '→ ${_name(widget.team[o['target'] as int])}';
    }
    final target = widget.foes[o['target']];
    return target == null ? '${o['label']}' : '${o['label']} → ${_name(target)}';
  }
}

class _MoveButton extends StatelessWidget {
  const _MoveButton({required this.label, required this.type, required this.detail, required this.selected, this.onTap});
  final String label;
  final String? type;
  final String detail;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final color = typeColor[type] ?? const Color(0xFF8D95A6);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            gradient: LinearGradient(colors: [
              color.withOpacity(selected ? .55 : .30),
              color.withOpacity(selected ? .30 : .10),
            ]),
            border: Border.all(color: selected ? Colors.white.withOpacity(.85) : color.withOpacity(.6), width: selected ? 2 : 1.2),
          ),
          child: Row(children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                if (detail.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(detail, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                  ),
              ]),
            ),
            if (type != null) TypeChip(type!, dense: true),
          ]),
        ),
      ),
    );
  }
}

class _TargetButton extends StatelessWidget {
  const _TargetButton({required this.mon, required this.eff, required this.selected, this.onTap});
  final Json? mon;
  final double? eff;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final (label, color) = switch (eff) {
      null => (null, cs.onSurfaceVariant),
      0 => ('효과 없음', const Color(0xFF8D95A6)),
      >= 2 => ('효과 굉장', const Color(0xFFFFC857)),
      < 1 => ('별로', const Color(0xFF9DB4D6)),
      _ => ('보통', cs.onSurfaceVariant),
    };
    return Material(
      color: selected ? cs.primary.withOpacity(.18) : cs.surfaceContainer,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.fromLTRB(6, 6, 14, 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: selected ? cs.primary : Colors.transparent, width: 1.5),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            if (mon != null) Sprite(mon!['sprite'] as String, size: 36),
            const SizedBox(width: 6),
            Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              Text(_name(mon), style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
              if (label != null)
                Text(eff != null && eff! != 1 && eff! != 0 ? '$label ×${eff!.toStringAsFixed(eff! < 1 ? 2 : 0)}' : label,
                    style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
            ]),
          ]),
        ),
      ),
    );
  }
}

class _BenchButton extends StatelessWidget {
  const _BenchButton({required this.mon, required this.selected, this.onTap});
  final Json mon;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hp = mon['hp'] as int? ?? 0;
    final max = mon['maxHp'] as int? ?? 1;
    final f = hp / math.max(max, 1);
    return Opacity(
      opacity: onTap == null && !selected ? .45 : 1,
      child: Material(
        color: selected ? cs.primary.withOpacity(.18) : cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            width: 168,
            padding: const EdgeInsets.fromLTRB(6, 6, 12, 8),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: selected ? cs.primary : Colors.transparent, width: 1.5),
            ),
            child: Row(children: [
              Sprite(mon['sprite'] as String, size: 38),
              const SizedBox(width: 6),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(_name(mon),
                      maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(value: f.clamp(0.0, 1.0), minHeight: 5, color: _hpColor(f)),
                  ),
                  const SizedBox(height: 2),
                  Text('$hp / $max', style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// 교체 포켓몬 고르기 (기절·유턴 뒤)
class ReplacementPicker extends StatelessWidget {
  const ReplacementPicker({
    super.key,
    required this.slot,
    required this.bench,
    required this.team,
    required this.chosen,
    required this.taken,
    required this.onPick,
  });
  final int slot;
  final List<int> bench;
  final List<Json?> team;
  final int? chosen;
  final Set<int> taken;
  final ValueChanged<int?>? onPick;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('{}번 자리'.replaceFirst('{}', '${slot + 1}'),
              style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final i in bench)
              if (team[i] case final m?)
                _BenchButton(
                  mon: m,
                  selected: chosen == i,
                  onTap: onPick == null || (taken.contains(i) && chosen != i) ? null : () => onPick!(chosen == i ? null : i),
                ),
          ]),
        ]),
      );
}

/// 배틀 결과 배너
class BattleResultBanner extends StatelessWidget {
  const BattleResultBanner({super.key, required this.winner, required this.turns, required this.members});
  final String winner; // win | loss | draw
  final int turns;
  final List<Json> members;

  @override
  Widget build(BuildContext context) {
    final (title, color, glyph) = switch (winner) {
      'win' || 'player' || 'me' => ('승리!', const Color(0xFFFFC857), LabGlyph.crystal),
      'draw' => ('무승부', const Color(0xFF9FD8FF), LabGlyph.versus),
      _ => ('패배…', const Color(0xFFF2656B), LabGlyph.versus),
    };
    final mvp = members.isEmpty ? null : (members.toList()..sort((a, b) => (b['dealt'] as int).compareTo(a['dealt'] as int))).first;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 520),
      curve: Curves.easeOutBack,
      builder: (_, v, child) => Transform.scale(scale: .85 + .15 * v, child: Opacity(opacity: v.clamp(0, 1), child: child)),
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(colors: [color.withOpacity(.28), color.withOpacity(.06)]),
          border: Border.all(color: color.withOpacity(.6), width: 1.5),
        ),
        child: Row(children: [
          LabIcon(glyph, size: 36, color: color),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: color, letterSpacing: -.5)),
              Text('{}턴 만에 끝났습니다'.replaceFirst('{}', '$turns'),
                  style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
            ]),
          ),
          if (mvp != null && (mvp['dealt'] as int) > 0) ...[
            Sprite(mvp['sprite'] as String, size: 56),
            const SizedBox(width: 6),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('MVP', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFFFFC857))),
              Text(_name(mvp), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
              Text('KO {}'.replaceFirst('{}', '${mvp['kos']}'),
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
            ]),
          ],
        ]),
      ),
    );
  }
}
