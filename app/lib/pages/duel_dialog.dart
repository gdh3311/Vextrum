import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../theme.dart';
import '../widgets.dart';
import '../i18n.dart';

const verdictKo = {'WIN': '유리', 'EVEN': '호각', 'LOSE': '불리'};
const verdictColor = {'WIN': good, 'EVEN': even, 'LOSE': bad};

class VerdictBadge extends StatelessWidget {
  final String label;
  final bool large;
  const VerdictBadge(this.label, {super.key, this.large = false});
  @override
  Widget build(BuildContext context) {
    final c = verdictColor[label] ?? even;
    return Container(
      width: large ? 64 : 46,
      padding: EdgeInsets.symmetric(vertical: large ? 6 : 4),
      alignment: Alignment.center,
      decoration: BoxDecoration(color: c.withOpacity(.16), borderRadius: BorderRadius.circular(7)),
      child: Text(verdictKo[label] ?? label,
          style: TextStyle(color: c, fontSize: large ? 15 : 12.5, fontWeight: FontWeight.w700)),
    );
  }
}

/// 데미지 범위 막대: 최소까지 진하게, 최대까지 연하게. 100%를 넘으면 가득 찬다.
class DamageBar extends StatelessWidget {
  final num min;
  final num max;
  final Color color;
  const DamageBar({super.key, required this.min, required this.max, required this.color});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: SizedBox(
        height: 8,
        child: Stack(children: [
          Container(color: cs.surfaceContainerHighest),
          FractionallySizedBox(
              widthFactor: (max / 100).clamp(0.0, 1.0).toDouble(), child: Container(color: color.withOpacity(.45))),
          FractionallySizedBox(widthFactor: (min / 100).clamp(0.0, 1.0).toDouble(), child: Container(color: color)),
        ]),
      ),
    );
  }
}

class _MoveRow extends StatelessWidget {
  final Json r;
  final Color color;
  const _MoveRow(this.r, this.color);
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final none = (r['max'] as num) <= 0;
    final tags = [
      if (r['usage'] != null) '채용 ${fmtPct(r['usage'] as num)}',
      if ((r['eff'] as num) >= 2) '약점 ${(r['eff'] as num).toStringAsFixed(0)}배',
      if ((r['eff'] as num) > 0 && (r['eff'] as num) < 1) '반감',
      if (r['spread'] == true) '전체기',
      if ((r['priority'] as num) > 0) '선공기',
      if ((r['acc'] as num) < 100) '명중 ${r['acc']}%',
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          TypeDot(r['type'] as String?),
          const SizedBox(width: 8),
          Expanded(
            child: Text.rich(
              TextSpan(children: [
                TextSpan(text: '${r['ko'] ?? r['move']}', style: const TextStyle(fontWeight: FontWeight.w600)),
                TextSpan(text: '  ${tags.join(' · ')}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
              ]),
              style: const TextStyle(fontSize: 14),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Text(none ? '효과 없음' : '${(r['min'] as num).round()}~${(r['max'] as num).round()}%',
              style: const TextStyle(
                  fontSize: 14, fontWeight: FontWeight.w700, fontFeatures: [FontFeature.tabularFigures()])),
          const SizedBox(width: 10),
          SizedBox(
              width: 62,
              child: Text(none ? '' : r['koText'] as String,
                  textAlign: TextAlign.right,
                  style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: (r['koText'] as String).endsWith('1타') ? color : cs.onSurfaceVariant))),
        ]),
        const SizedBox(height: 6),
        DamageBar(min: r['min'] as num, max: r['max'] as num, color: color),
      ]),
    );
  }
}

class _Side extends StatelessWidget {
  final Json mon;
  final String title;
  final Widget? extra;
  const _Side(this.mon, this.title, {this.extra});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final st = mon['stats'] as Json;
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Sprite(mon['sprite'] as String, size: 64),
      const SizedBox(width: 10),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          NameBlock(mon['ko'] as String?, mon['name'] as String, size: 15.5),
          const SizedBox(height: 4),
          TypeRow(mon['types'] as List, dense: true),
          const SizedBox(height: 6),
          extra ??
              Row(children: [
                ItemIcon(mon['item'] as String?, size: 18),
                const SizedBox(width: 5),
                Flexible(
                    child: Text('${mon['itemKo'] ?? mon['item'] ?? '도구 없음'}',
                        style: const TextStyle(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis)),
              ]),
          const SizedBox(height: 4),
          Text('${mon['abilityKo'] ?? mon['ability']} · ${mon['natureKo'] ?? mon['nature']}',
              style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
          Text('HP ${st['hp']} · 공 ${st['atk']} · 방 ${st['def']} · 특공 ${st['spa']} · 특방 ${st['spd']} · 스피드 ${(mon['speed'] as num).round()}',
              style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant, fontFeatures: const [FontFeature.tabularFigures()])),
        ]),
      ),
    ]);
  }
}

/// 내 세트 vs 상대 한 마리의 1:1 상세
class DuelDialog extends ConsumerStatefulWidget {
  final Json mySet;
  final String foeId;
  const DuelDialog({super.key, required this.mySet, required this.foeId});
  @override
  ConsumerState<DuelDialog> createState() => _DuelDialogState();
}

class _DuelDialogState extends ConsumerState<DuelDialog> {
  String? foeItem; // null = 가장 흔한 세트
  late Future<Json> future = _load();

  Future<Json> _load() => fetchDuel(
      ref.read(formatProvider), widget.mySet, {'id': widget.foeId, if (foeItem != null) 'item': foeItem});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Dialog(
      insetPadding: const EdgeInsets.all(20),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 900, maxHeight: 860),
        child: FutureBuilder<Json>(
          future: future,
          builder: (context, snap) {
            if (snap.hasError) {
              return const Padding(padding: EdgeInsets.all(40), child: Text('대결 정보를 불러오지 못했습니다'));
            }
            if (!snap.hasData) {
              return const SizedBox(height: 240, child: Center(child: CircularProgressIndicator()));
            }
            final d = snap.data!;
            final v = d['verdict'] as Json;
            final me = d['me'] as Json, foe = d['foe'] as Json;
            final items = (d['foeItems'] as List).cast<Json>();
            final speedText = switch (v['speed']) {
              'fast' => '내가 선공',
              'slow' => '상대가 선공',
              _ => '동속',
            };
            return Column(mainAxisSize: MainAxisSize.min, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 18, 12, 0),
                child: Row(children: [
                  VerdictBadge(v['label'] as String, large: true),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(v['text'] as String, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                      Text(
                          '$speedText'
                          '${v['myTurns'] != null ? ' · 내가 ${v['myTurns']}타' : ''}'
                          '${v['theirTurns'] != null ? ' · 상대가 ${v['theirTurns']}타' : ''}',
                          style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                    ]),
                  ),
                  IconButton(onPressed: () => Navigator.pop(context), icon: const LabIcon(LabGlyph.cross)),
                ]),
              ),
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(24, 18, 24, 24),
                  child: LayoutBuilder(builder: (context, c) {
                    final two = c.maxWidth >= 640;
                    final w = two ? (c.maxWidth - 32) / 2 : c.maxWidth;
                    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Wrap(spacing: 32, runSpacing: 20, children: [
                        SizedBox(width: w, child: _Side(me, '내 포켓몬')),
                        SizedBox(
                          width: w,
                          child: _Side(foe, '상대',
                              extra: PopupMenuButton<String>(
                                tooltip: tr('상대 도구 바꿔 보기'),
                                position: PopupMenuPosition.under,
                                color: cs.surfaceContainerHighest,
                                onSelected: (it) => setState(() {
                                  foeItem = it;
                                  future = _load();
                                }),
                                itemBuilder: (_) => [
                                  for (final it in items)
                                    PopupMenuItem(
                                        value: it['name'] as String,
                                        height: 40,
                                        child: Row(children: [
                                          ItemIcon(it['name'] as String, size: 20),
                                          const SizedBox(width: 8),
                                          Expanded(
                                              child: Text('${it['ko'] ?? it['name']}',
                                                  style: const TextStyle(fontSize: 13.5))),
                                          Text(fmtPct(it['pct'] as num),
                                              style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
                                        ])),
                                ],
                                child: Container(
                                  padding: const EdgeInsets.fromLTRB(8, 5, 4, 5),
                                  decoration: BoxDecoration(
                                      color: cs.surfaceContainer, borderRadius: BorderRadius.circular(8)),
                                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                                    ItemIcon(foe['item'] as String?, size: 18),
                                    const SizedBox(width: 5),
                                    Text('${foe['itemKo'] ?? foe['item'] ?? '도구 없음'}',
                                        style: const TextStyle(fontSize: 13)),
                                    LabIcon(LabGlyph.down, size: 18, color: cs.onSurfaceVariant),
                                  ]),
                                ),
                              )),
                        ),
                      ]),
                      const SizedBox(height: 18),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(14),
                        decoration:
                            BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(12)),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          for (final nt in (d['notes'] as List))
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Text('$nt',
                                  style: TextStyle(
                                      fontSize: 13.5,
                                      height: 1.5,
                                      color: '$nt'.startsWith('주의') ? even : cs.onSurface)),
                            ),
                        ]),
                      ),
                      const SizedBox(height: 20),
                      Wrap(spacing: 32, runSpacing: 20, children: [
                        SizedBox(
                          width: w,
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            const Text('내가 주는 데미지', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                            const SizedBox(height: 12),
                            for (final r in (d['mine'] as List).cast<Json>()) _MoveRow(r, good),
                            if ((d['mine'] as List).isEmpty)
                              Text('공격 기술이 없습니다', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant)),
                            if ((d['status'] as List).isNotEmpty)
                              Wrap(spacing: 6, runSpacing: 6, children: [
                                for (final m in (d['status'] as List).cast<Json>())
                                  MoveChip(m['move'] as String, ko: m['ko'] as String?, type: m['type'] as String?),
                              ]),
                          ]),
                        ),
                        SizedBox(
                          width: w,
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            const Text('내가 받는 데미지', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                            Text('상대가 자주 쓰는 기술 전부 (채용률 8% 이상)',
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                            const SizedBox(height: 10),
                            for (final r in (d['theirs'] as List).cast<Json>()) _MoveRow(r, bad),
                          ]),
                        ),
                      ]),
                      const SizedBox(height: 4),
                      Text('데미지는 난수 85~100% 범위이며 급소·랭크 변화·날씨 지속은 반영하지 않습니다.',
                          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                    ]);
                  }),
                ),
              ),
            ]);
          },
        ),
      ),
    );
  }
}
