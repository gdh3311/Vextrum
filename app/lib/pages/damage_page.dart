import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'calc_common.dart';
import 'team_page.dart' show SetEditor;

/// 데미지 계산: 공격 측의 기술 4개가 방어 측에게 주는 최소~최대 데미지와 몇 번에 쓰러뜨리는지.
/// 계산은 배틀 엔진(/api/damage)과 같은 식을 쓴다.
class DamagePage extends ConsumerStatefulWidget {
  const DamagePage({super.key});
  @override
  ConsumerState<DamagePage> createState() => _DamagePageState();
}

class _DamagePageState extends ConsumerState<DamagePage> {
  TeamSlot? attacker, defender;
  String weather = 'auto';
  bool? spread; // null = 기술 기준 자동
  bool crit = false, helpingHand = false, screen = false, psychicTerrain = false;
  int atkStage = 0, defStage = 0, hpPct = 100;
  Future<Json>? result;

  void recalc() {
    final a = attacker, d = defender;
    if (a == null || d == null) {
      setState(() => result = null);
      return;
    }
    setState(() => result = dio.post('/api/damage', data: {
          'format': ref.read(formatProvider),
          'attacker': a.set,
          'defender': d.set,
          'weather': weather,
          'spread': spread,
          'crit': crit,
          'helpingHand': helpingHand,
          'screen': screen,
          'psychicTerrain': psychicTerrain,
          'atkStage': atkStage,
          'defStage': defStage,
          'hpPct': hpPct,
        }).then((r) => r.data as Json));
  }

  Future<void> edit(bool isAttacker) async {
    final s = isAttacker ? attacker : defender;
    if (s == null) return;
    await showDialog(
        context: context,
        builder: (_) => SetEditor(
            slot: s,
            onChanged: (v) {
              final next = s.withSet(v);
              if (isAttacker) {
                attacker = next;
              } else {
                defender = next;
              }
            }));
    recalc();
  }

  @override
  Widget build(BuildContext context) {
    final fmt = ref.watch(formatProvider);
    final cs = Theme.of(context).colorScheme;
    final items = ref.watch(itemsProvider).valueOrNull ?? const <Json>[];
    final itemKo = {for (final i in items) i['name']: i['ko']};
    final natures = (ref.watch(infoProvider).valueOrNull?['natures'] ?? const {}) as Map;
    String abilityKo(TeamSlot s, String? name) {
      if (name == null) return '-';
      for (final a in (s.detail['abilities'] as List).cast<Json>()) {
        if (a['name'] == name) return (a['ko'] ?? name) as String;
      }
      return name;
    }

    Widget monCard(TeamSlot? s, bool isAttacker) {
      final set = s?.set ?? const {};
      final pts = (set['points'] ?? const {}) as Map;
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: cs.surfaceContainerHighest.withOpacity(.4), borderRadius: BorderRadius.circular(12)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CalcMonHeader(
            slot: s,
            label: isAttacker ? tr('공격 측') : tr('방어 측'),
            onPick: () async {
              final picked = await pickCalcMon(context, ref);
              if (picked == null) return;
              if (isAttacker) {
                attacker = picked;
              } else {
                defender = picked;
              }
              recalc();
            },
            trailing: s == null ? null : TextButton(onPressed: () => edit(isAttacker), child: const Text('세트 편집')),
          ),
          if (s != null) ...[
            const SizedBox(height: 6),
            Wrap(spacing: 10, runSpacing: 4, children: [
              Text('${tr('도구')}: ${set['item'] == null ? '-' : (itemKo[set['item']] ?? set['item'])}',
                  style: const TextStyle(fontSize: 12.5)),
              Text('${tr('특성')}: ${abilityKo(s, set['ability'] as String?)}', style: const TextStyle(fontSize: 12.5)),
              Text('${tr('성격')}: ${set['nature'] == null ? '-' : natureLabel(set['nature'] as String, (natures[set['nature']] as Map?)?['ko'] as String?)}',
                  style: const TextStyle(fontSize: 12.5)),
            ]),
            Text('${tr('능력 포인트')} ${statKeys.map((k) => '${pts[k] ?? 0}').join('/')}',
                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            const SizedBox(height: 4),
            StageDropdown(
                label: isAttacker ? tr('공격 랭크') : tr('방어 랭크'),
                value: isAttacker ? atkStage : defStage,
                onChanged: (v) {
                  if (isAttacker) {
                    atkStage = v;
                  } else {
                    defStage = v;
                  }
                  recalc();
                }),
            if (!isAttacker)
              Row(children: [
                SizedBox(width: 92, child: Text(tr('남은 HP {}%').replaceFirst('{}', '$hpPct'), style: const TextStyle(fontSize: 13))),
                Expanded(
                  child: Slider(
                      value: hpPct.toDouble(),
                      min: 1,
                      max: 100,
                      divisions: 99,
                      onChanged: (v) => setState(() => hpPct = v.round()),
                      onChangeEnd: (_) => recalc()),
                ),
              ]),
          ],
        ]),
      );
    }

    void toggle(void Function() f) {
      f();
      recalc();
    }

    return PageBody(children: [
      PageHeader('데미지 계산',
          glyph: LabGlyph.shield,
          subtitle:
              '${fmt == 'Doubles' ? '더블배틀' : '싱글배틀'} · 공격 측 기술 4개가 주는 데미지 범위(난수 85~100%)와 몇 번에 쓰러뜨리는지 계산합니다. 앱의 배틀 엔진과 같은 식이라 실제 게임과 조금 다를 수 있습니다'),
      LayoutBuilder(builder: (context, c) {
        final a = monCard(attacker, true), d = monCard(defender, false);
        final swap = IconButton(
            tooltip: tr('공격·방어 바꾸기'),
            onPressed: () {
              final t = attacker;
              attacker = defender;
              defender = t;
              final st = atkStage;
              atkStage = defStage;
              defStage = st;
              recalc();
            },
            icon: const LabIcon(LabGlyph.swap));
        return c.maxWidth >= 720
            ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(child: a),
                Padding(padding: const EdgeInsets.only(top: 18), child: swap),
                Expanded(child: d),
              ])
            : Column(children: [a, swap, d]);
      }),
      const SizedBox(height: 12),
      Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Wrap(spacing: 10, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            DropdownButton<String>(
              value: weather,
              isDense: true,
              items: const [
                DropdownMenuItem(value: 'auto', child: Text('날씨: 특성대로')),
                DropdownMenuItem(value: 'none', child: Text('날씨 없음')),
                DropdownMenuItem(value: 'sun', child: Text('쾌청')),
                DropdownMenuItem(value: 'rain', child: Text('비')),
                DropdownMenuItem(value: 'sand', child: Text('모래바람')),
                DropdownMenuItem(value: 'snow', child: Text('설경')),
              ],
              onChanged: (v) => toggle(() => weather = v ?? 'auto'),
            ),
            if (fmt == 'Doubles')
              DropdownButton<bool?>(
                value: spread,
                isDense: true,
                items: const [
                  DropdownMenuItem(value: null, child: Text('범위 기술: 기술대로')),
                  DropdownMenuItem(value: false, child: Text('한 마리만 맞음')),
                  DropdownMenuItem(value: true, child: Text('두 마리 맞음 (×0.75)')),
                ],
                onChanged: (v) => toggle(() => spread = v),
              ),
            FilterChip(label: const Text('급소'), selected: crit, onSelected: (v) => toggle(() => crit = v)),
            FilterChip(
                label: const Text('도우미'), selected: helpingHand, onSelected: (v) => toggle(() => helpingHand = v)),
            FilterChip(
                label: const Text('리플렉터·빛의장막'), selected: screen, onSelected: (v) => toggle(() => screen = v)),
            FilterChip(
                label: const Text('사이코필드'),
                selected: psychicTerrain,
                onSelected: (v) => toggle(() => psychicTerrain = v)),
          ]),
        ),
      ),
      const SizedBox(height: 12),
      if (result == null)
        Padding(
          padding: const EdgeInsets.all(12),
          child: Text('공격 측과 방어 측 포켓몬을 고르면 계산합니다', style: TextStyle(color: cs.onSurfaceVariant)),
        )
      else
        FutureBuilder<Json>(
          future: result,
          builder: (context, snap) {
            if (snap.hasError) return Text(tr('계산하지 못했습니다'), style: TextStyle(color: cs.error));
            if (!snap.hasData) return const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator());
            return _DamageResults(snap.data!);
          },
        ),
    ]);
  }
}

class _DamageResults extends StatelessWidget {
  const _DamageResults(this.r);
  final Json r;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final moves = (r['moves'] as List).cast<Json>();
    final hp = r['defenderHp'] as num, current = r['currentHp'] as num;
    final defender = r['defender'] as Json;
    return Section(
      '결과',
      subtitle: tr('{} · HP {} / {}')
          .replaceFirst('{}', '${defender['ko'] ?? defender['name']}')
          .replaceFirst('{}', '$current')
          .replaceFirst('{}', '$hp'),
      child: Column(children: [
        for (final m in moves)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
              if (m['type'] != null) TypeChip(m['type'] as String, dense: true) else const SizedBox(width: 52),
              const SizedBox(width: 8),
              SizedBox(
                width: 150,
                child: NameBlock(m['ko'] as String?, m['move'] as String, size: 13),
              ),
              Expanded(
                child: m['status'] == true
                    ? Text('변화 기술', style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant))
                    : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        _RangeBar(
                            min: (m['minHp'] as num) / hp, max: (m['maxHp'] as num) / hp, current: current / hp),
                        const SizedBox(height: 3),
                        Wrap(spacing: 10, children: [
                          Text('${m['minPct']}% ~ ${m['maxPct']}%',
                              style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w800)),
                          Text('(${m['minHp']}~${m['maxHp']} HP)',
                              style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                          Text(hitsLabel(m['hits'] as int?, (m['chance'] ?? 0) as num),
                              style: TextStyle(
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w700,
                                  color: m['hits'] == 1 ? const Color(0xFFF0616D) : cs.primary)),
                          if ((m['eff'] as num) != 1)
                            Text(tr('상성 ×{}').replaceFirst('{}', '${m['eff']}'),
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                        ]),
                      ]),
              ),
            ]),
          ),
      ]),
    );
  }
}

/// 남은 HP 막대 위에 최소~최대 데미지 구간을 겹쳐 보여 준다.
class _RangeBar extends StatelessWidget {
  const _RangeBar({required this.min, required this.max, required this.current});
  final double min, max, current;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return LayoutBuilder(builder: (context, c) {
      final w = c.maxWidth;
      double x(double v) => (v.clamp(0, 1)) * w;
      final hpEnd = x(current);
      final lo = (current - max).clamp(0, 1).toDouble(), hi = (current - min).clamp(0, 1).toDouble();
      return SizedBox(
        height: 10,
        child: Stack(children: [
          Container(decoration: BoxDecoration(color: cs.surfaceContainerHighest, borderRadius: BorderRadius.circular(5))),
          // 확실히 남는 HP
          Container(
              width: x(lo),
              decoration: BoxDecoration(color: const Color(0xFF34C77B), borderRadius: BorderRadius.circular(5))),
          // 난수에 따라 남거나 깎이는 구간
          Positioned(
              left: x(lo),
              width: (x(hi) - x(lo)).clamp(0, w),
              top: 0,
              bottom: 0,
              child: Container(color: const Color(0xFFE0A93B))),
          // 확실히 깎이는 구간
          Positioned(
              left: x(hi),
              width: (hpEnd - x(hi)).clamp(0, w),
              top: 0,
              bottom: 0,
              child: Container(color: const Color(0xFFF0616D).withOpacity(.55))),
        ]),
      );
    });
  }
}
