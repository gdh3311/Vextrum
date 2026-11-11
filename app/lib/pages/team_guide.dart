import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../theme.dart';
import '../widgets.dart';
import '../i18n.dart';

/// 팀 화면 아래쪽 탭: 전략 가이드 / 약점·상성 분석
final teamTabProvider = StateProvider<String>((ref) => 'guide');

class TeamTabs extends ConsumerWidget {
  final Json? guide;
  final Widget analysis;
  const TeamTabs({super.key, required this.guide, required this.analysis});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tab = ref.watch(teamTabProvider);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SegmentedButton<String>(
        showSelectedIcon: false,
        segments: const [
          ButtonSegment(value: 'guide', icon: LabIcon(LabGlyph.book, size: 18), label: Text('전략 가이드')),
          ButtonSegment(value: 'analysis', icon: LabIcon(LabGlyph.meta, size: 18), label: Text('약점 · 상성 분석')),
        ],
        selected: {tab},
        onSelectionChanged: (s) => ref.read(teamTabProvider.notifier).state = s.first,
      ),
      const SizedBox(height: 16),
      if (tab == 'guide') (guide == null ? const SizedBox() : TeamGuide(guide!)) else analysis,
    ]);
  }
}

class _Mons extends StatelessWidget {
  final List mons;
  final double size;
  const _Mons(this.mons, {this.size = 32});
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        for (final m in mons.cast<Json>())
          Tooltip(message: '${m['ko'] ?? m['name']} · ${m['name']}', child: Sprite(m['sprite'] as String, size: size)),
      ]);
}

class _Badge extends StatelessWidget {
  final String text;
  final Color color;
  const _Badge(this.text, this.color);
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: color.withOpacity(.16), borderRadius: BorderRadius.circular(6)),
        child: Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700)),
      );
}

class TeamGuide extends StatelessWidget {
  final Json g;
  const TeamGuide(this.g, {super.key});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final lead = g['lead'] as Json?;
    final body = TextStyle(fontSize: 14, height: 1.55, color: cs.onSurface);
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant);

    Widget group(String title, List mons, {bool strong = false}) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: muted),
            const SizedBox(height: 6),
            if (mons.isEmpty) Text('-', style: muted),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final m in mons.cast<Json>())
                Opacity(
                  opacity: strong ? 1 : .8,
                  child: MonPill(m, onTap: () => context.push('/pokemon/${m['id']}')),
                ),
            ]),
          ],
        );

    return Column(children: [
      if (g['complete'] != true)
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: even.withOpacity(.12), borderRadius: BorderRadius.circular(12)),
          child: Row(children: [
            const LabIcon(LabGlyph.info, size: 18, color: even),
            const SizedBox(width: 10),
            Expanded(child: Text('팀이 아직 다 차지 않았습니다. 6마리를 채우면 선출과 대응법이 더 정확해집니다.', style: body)),
          ]),
        ),
      Section(
        '이 팀의 운영법',
        subtitle: '세트의 기술·특성에서 읽어낸 팀의 축과 굴리는 방법',
        child: Column(children: [
          for (final a in (g['axes'] as List).cast<Json>())
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 118, child: Align(alignment: Alignment.centerLeft, child: _Badge(a['label'] as String, cs.primary))),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if ((a['members'] as List).isNotEmpty)
                      Padding(padding: const EdgeInsets.only(bottom: 4), child: _Mons(a['members'] as List)),
                    Text(a['play'] as String, style: body),
                  ]),
                ),
              ]),
            ),
        ]),
      ),
      if (lead != null)
        Section(
          '기본 선출',
          subtitle: '상대를 모를 때 메타 상위권 기준으로 가장 무난한 조합',
          trailing: OutlinedButton.icon(
              onPressed: () => context.go('/enemy'),
              icon: const LabIcon(LabGlyph.versus, size: 18),
              label: const Text('상대에 맞춘 선출 보기')),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Wrap(spacing: 32, runSpacing: 16, children: [
              group('선봉', lead['lead'] as List, strong: true),
              group('후발', lead['back'] as List, strong: true),
              if ((lead['bench'] as List).isNotEmpty) group('대기', lead['bench'] as List),
            ]),
            const SizedBox(height: 14),
            for (final w in (lead['why'] as List))
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(children: [
                  LabIcon(LabGlyph.check, size: 16, color: cs.primary),
                  const SizedBox(width: 8),
                  Expanded(child: Text('$w', style: body)),
                ]),
              ),
          ]),
        ),
      if ((g['winConditions'] as List).isNotEmpty)
        Section(
          '주력 포켓몬',
          subtitle: '메타 상위권을 가장 넓게 잡는 순서 · 숫자는 잡을 수 있는 메타의 비중',
          child: Column(children: [
            for (final w in (g['winConditions'] as List).cast<Json>())
              Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Sprite(w['mon']['sprite'] as String, size: 48),
                  const SizedBox(width: 10),
                  SizedBox(
                    width: 120,
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${w['mon']['ko'] ?? w['mon']['name']}',
                          style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                      Text('${w['coverage']}%',
                          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: cs.primary)),
                    ]),
                  ),
                  Expanded(
                    child: Wrap(spacing: 8, runSpacing: 8, children: [
                      for (final b in (w['beats'] as List).cast<Json>())
                        MonPill(b,
                            caption: '${b['moveKo'] ?? b['move']} ${fmtPct(b['pct'] as num)}',
                            onTap: () => context.push('/pokemon/${b['id']}')),
                    ]),
                  ),
                ]),
              ),
          ]),
        ),
      if ((g['synergies'] as List).isNotEmpty)
        Section(
          '조합 활용과 주의점',
          child: Column(children: [
            for (final s in (g['synergies'] as List).cast<Json>())
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
                  LabIcon(s['kind'] == 'warn' ? LabGlyph.alert : LabGlyph.link,
                      size: 18, color: s['kind'] == 'warn' ? even : cs.primary),
                  const SizedBox(width: 8),
                  _Mons(s['members'] as List),
                  const SizedBox(width: 10),
                  Expanded(child: Text(s['text'] as String, style: body)),
                ]),
              ),
          ]),
        ),
      Section(
        '메타 전략별 대비',
        subtitle: '자주 만나는 전략에 대해 이 팀이 가진 수단',
        child: Column(children: [
          for (final r in (g['prep'] as List).cast<Json>())
            Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: cs.outlineVariant))),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(
                    width: 96,
                    child: Text(r['label'] as String,
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600))),
                SizedBox(
                  width: 58,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: switch (r['level']) {
                      'good' => const _Badge('충분', good),
                      'ok' => const _Badge('보통', even),
                      _ => const _Badge('부족', bad),
                    },
                  ),
                ),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if ((r['answers'] as List).isNotEmpty)
                      Padding(padding: const EdgeInsets.only(bottom: 4), child: _Mons(r['answers'] as List, size: 30)),
                    Text(r['advice'] as String, style: TextStyle(fontSize: 13.5, height: 1.5, color: cs.onSurface)),
                  ]),
                ),
              ]),
            ),
        ]),
      ),
      Section(
        '위험한 상대와 대응법',
        subtitle: '메타 상위권 중 이 팀이 가장 힘들어하는 순서 · 상대는 가장 흔한 세트 기준, 데미지는 근사치',
        child: Column(children: [
          for (final t in (g['threats'] as List).cast<Json>())
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                InkWell(
                  onTap: () => context.push('/pokemon/${t['mon']['id']}'),
                  borderRadius: BorderRadius.circular(8),
                  child: SizedBox(
                    width: 150,
                    child: Row(children: [
                      Sprite(t['mon']['sprite'] as String, size: 48),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${t['mon']['ko'] ?? t['mon']['name']}',
                              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis),
                          const SizedBox(height: 3),
                          Row(children: [
                            switch (t['label']) {
                              'BAD' => const _Badge('불리', bad),
                              'EVEN' => const _Badge('호각', even),
                              _ => const _Badge('유리', good),
                            },
                            const SizedBox(width: 6),
                            Text('${t['rank']}위', style: muted),
                          ]),
                        ]),
                      ),
                    ]),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    for (final s in (t['steps'] as List))
                      Padding(
                        padding: const EdgeInsets.only(bottom: 4),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Padding(
                            padding: const EdgeInsets.only(top: 9, right: 8),
                            child: Container(
                                width: 4, height: 4, decoration: BoxDecoration(color: cs.onSurfaceVariant, shape: BoxShape.circle)),
                          ),
                          Expanded(child: Text('$s', style: body)),
                        ]),
                      ),
                  ]),
                ),
              ]),
            ),
        ]),
      ),
    ]);
  }
}
