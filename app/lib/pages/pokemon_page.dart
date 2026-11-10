import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';

class PokemonPage extends ConsumerWidget {
  final String id;
  const PokemonPage({super.key, required this.id});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(pokemonDetailProvider(id));
    final fmt = ref.watch(formatProvider);
    return AsyncView<Json>(detail, (p) {
      final t = Theme.of(context);
      final cs = t.colorScheme;
      final u = p['usage'] as Json?;
      final megas = (p['megas'] as List).cast<Json>();
      final stats = p['stats'] as Json;
      final team = ref.watch(teamProvider);

      Widget dual(String? ko, String name) => Text.rich(
            TextSpan(children: [
              TextSpan(text: ko ?? name, style: const TextStyle(fontWeight: FontWeight.w600)),
              if (ko != null) TextSpan(text: '  $name', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
            ]),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 13),
          );

      Widget statBars(Json s) => Column(children: [
            for (final k in statKeys)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  SizedBox(width: 52, child: Text(statKo[k]!, style: const TextStyle(fontSize: 12))),
                  SizedBox(
                      width: 36,
                      child: Text('${s[k]}',
                          textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.w700))),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                          value: ((s[k] as num) / 260).clamp(0.0, 1.0).toDouble(), minHeight: 8),
                    ),
                  ),
                ]),
              ),
          ]);

      return PageBody(children: [
        Section(
          '${p['ko'] ?? p['name']}',
          subtitle: '${p['name']}${u != null ? ' · ${fmt == 'Doubles' ? '더블' : '싱글'} ${u['rank']}위' : ' · 이 포맷 데이터 없음'}',
          trailing: FilledButton.icon(
            icon: const Icon(Icons.add),
            label: Text(team.length >= 6 ? '팀이 가득 참' : '팀에 추가'),
            onPressed: team.length >= 6
                ? null
                : () async {
                    await ref.read(teamProvider.notifier).add(id);
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text('${p['ko'] ?? p['name']}을(를) 팀에 추가했습니다'),
                          action: SnackBarAction(label: '팀 보기', onPressed: () => context.go('/team'))));
                    }
                  },
          ),
          child: Wrap(spacing: 24, runSpacing: 16, crossAxisAlignment: WrapCrossAlignment.center, children: [
            Sprite(p['sprite'] as String, size: 132),
            SizedBox(
              width: 300,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                TypeRow(p['types'] as List),
                const SizedBox(height: 10),
                Text('특성', style: t.textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant)),
                for (final a in (p['abilities'] as List).cast<Json>()) dual(a['ko'] as String?, a['name'] as String),
                const SizedBox(height: 10),
                Text('능력치 (Lv.50, 포인트 0)', style: t.textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant)),
                statBars(stats),
              ]),
            ),
            for (final m in megas)
              Container(
                width: 250,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                    border: Border.all(color: cs.outlineVariant), borderRadius: BorderRadius.circular(12)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Sprite(m['sprite'] as String, size: 64),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        NameBlock(m['ko'] as String?, m['name'] as String, size: 13),
                        const SizedBox(height: 3),
                        TypeRow(m['types'] as List, dense: true),
                      ]),
                    ),
                  ]),
                  if (m['stone'] != null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(children: [
                        ItemIcon(m['stone'] as String, size: 20),
                        const SizedBox(width: 4),
                        Text(m['stone'] as String, style: const TextStyle(fontSize: 12)),
                      ]),
                    ),
                  for (final a in (m['abilities'] as List).cast<Json>())
                    dual(a['ko'] as String?, a['name'] as String),
                  const SizedBox(height: 4),
                  statBars(m['stats'] as Json),
                ]),
              ),
          ]),
        ),
        if (u != null)
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 960 ? 3 : (c.maxWidth >= 600 ? 2 : 1);
            final w = (c.maxWidth - (cols - 1) * 12) / cols;
            Widget box(Widget child) => SizedBox(width: w, child: child);
            return Wrap(spacing: 12, children: [
              box(Section('기술',
                  subtitle: '채용률',
                  child: Column(children: [
                    for (final r in (u['moves'] as List).cast<Json>())
                      UsageBar(
                        pct: r['pct'] as num,
                        color: typeColor[r['type']],
                        leading: Row(children: [
                          TypeChip(r['type'] as String, dense: true),
                          const SizedBox(width: 6),
                          Flexible(child: dual(r['ko'] as String?, r['name'] as String)),
                          const SizedBox(width: 6),
                          Text(
                              '${categoryKo[r['category']]}${(r['power'] as num) > 0 ? ' ${r['power']}' : ''}',
                              style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
                        ]),
                      ),
                  ]))),
              box(Column(children: [
                Section('도구',
                    child: Column(children: [
                      for (final r in (u['items'] as List).cast<Json>())
                        UsageBar(
                          pct: r['pct'] as num,
                          leading: Row(children: [
                            ItemIcon(r['name'] as String),
                            const SizedBox(width: 6),
                            Flexible(child: dual(r['ko'] as String?, r['name'] as String)),
                          ]),
                        ),
                    ])),
                Section('특성',
                    child: Column(children: [
                      for (final r in (u['abilities'] as List).cast<Json>())
                        UsageBar(pct: r['pct'] as num, leading: dual(r['ko'] as String?, r['name'] as String)),
                    ])),
              ])),
              box(Column(children: [
                Section('성격',
                    child: Column(children: [
                      for (final r in (u['natures'] as List).cast<Json>())
                        UsageBar(
                          pct: r['pct'] as num,
                          leading: Text(natureLabel(r['name'] as String, r['ko'] as String?),
                              style: const TextStyle(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
                        ),
                    ])),
                Section('능력 포인트 분배',
                    subtitle: 'HP / 공격 / 방어 / 특공 / 특방 / 스피드',
                    child: Column(children: [
                      for (final r in (u['spreads'] as List).cast<Json>())
                        UsageBar(
                          pct: r['pct'] as num,
                          leading: Text(statKeys.map((k) => '${r[k]}').join(' / '),
                              style: const TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()])),
                        ),
                    ])),
              ])),
            ]);
          }),
        if (u != null)
          Section('함께 쓰는 포켓몬',
              subtitle: '같은 팀에 자주 들어가는 순서',
              child: Wrap(spacing: 8, runSpacing: 8, children: [
                for (final m in (u['teammates'] as List).cast<Json>())
                  MonPill(m,
                      caption: m['rank'] == null ? null : '#${m['rank']} ${m['name']}',
                      onTap: () => context.push('/pokemon/${m['id']}')),
              ])),
        if (u != null)
          LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 760 ? 2 : 1;
            final w = (c.maxWidth - (cols - 1) * 12) / cols;
            Widget list(String title, String sub, List rows, bool counters) => SizedBox(
                  width: w,
                  child: Section(title,
                      subtitle: sub,
                      child: rows.isEmpty
                          ? const Text('해당 없음')
                          : Wrap(spacing: 8, runSpacing: 8, children: [
                              for (final m in rows.cast<Json>())
                                MonPill(m,
                                    caption: counters
                                        ? '${m['takenMoveKo'] ?? m['takenMove'] ?? '-'} ${fmtPct(m['takenPct'] as num)}'
                                        : '${m['moveKo'] ?? m['move'] ?? '-'} ${fmtPct(m['pct'] as num)}',
                                    onTap: () => context.push('/pokemon/${m['id']}')),
                            ])),
                );
            return Wrap(spacing: 12, children: [
              list('잘 잡는 상대', '메타 상위 40마리 중 · 주력기와 예상 데미지', p['targets'] as List, false),
              list('조심할 상대', '메타 상위 40마리 중 · 상대 주력기와 받는 데미지', p['counters'] as List, true),
            ]);
          }),
        Section('시즌별 순위',
            child: Wrap(spacing: 8, runSpacing: 8, children: [
              for (final h in (p['history'] as List).cast<Json>())
                Chip(
                    label: Text('${h['season']}  ${h['rank'] == null ? '-' : '#${h['rank']}'}'),
                    visualDensity: VisualDensity.compact),
            ])),
      ]);
    }, onRetry: () => ref.invalidate(pokemonDetailProvider(id)));
  }
}
