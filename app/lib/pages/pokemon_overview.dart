import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../widgets.dart';
import '../i18n.dart';

/// 채용 통계 탭: 능력치, 메가 폼, 기술·도구·특성·성격·분배 채용률, 동료, 시즌별 순위
class PokemonOverview extends ConsumerWidget {
  final String id;
  final String? season;
  const PokemonOverview({super.key, required this.id, this.season});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final request = season == null ? pokemonDetailProvider(id) : seasonDetailProvider((id, season!));
    final detail = ref.watch(request);
    final fmt = ref.watch(formatProvider);
    return AsyncView<Json>(detail, (p) {
      final t = Theme.of(context);
      final cs = t.colorScheme;
      final u = p['usage'] as Json?;
      final megas = (p['megas'] as List).cast<Json>();
      final stats = p['stats'] as Json;

      Widget dual(String? ko, String name) => Text.rich(
            TextSpan(children: [
              TextSpan(text: ko ?? name, style: const TextStyle(fontWeight: FontWeight.w600)),
              if (ko != null) TextSpan(text: '  $name', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
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

      return Column(children: [
        if (season != null)
          Section('시즌 $season · ${p['ko'] ?? p['name']}',
            subtitle: p['previewOnly'] == true ? '시즌 요약 · 확인된 채용률만 표시' : p['snapshotDate'] as String?,
            child: Wrap(spacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
              Text(u == null ? '이 배틀 형식의 상세 스냅샷이 없습니다.' : '사용 순위 ${p['rank']}위'),
              if (p['previewOnly'] == true)
                TextButton(onPressed: () => ref.invalidate(request), child: const Text('전체 채용률 다시 불러오기')),
            ]),
          ),
        Section(
          '기본 능력치',
          subtitle: '${p['name']}${u != null ? ' · ${fmt == 'Doubles' ? '더블' : '싱글'} ${u['rank']}위' : ' · 이 포맷 데이터 없음'}',
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
                        pct: r['pct'] as num?,
                        color: typeColor[r['type']],
                        leading: Row(children: [
                          if (r['type'] case final String type) ...[
                            TypeChip(type, dense: true),
                            const SizedBox(width: 6),
                          ],
                          Flexible(child: dual(r['ko'] as String?, r['name'] as String)),
                          const SizedBox(width: 6),
                          if (r['category'] != null) Text(
                              '${categoryKo[r['category']]}${(r['power'] as num? ?? 0) > 0 ? ' ${r['power']}' : ''}',
                              style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                        ]),
                      ),
                  ]))),
              box(Column(children: [
                Section('도구',
                    child: Column(children: [
                      for (final r in (u['items'] as List).cast<Json>())
                        UsageBar(
                          pct: r['pct'] as num?,
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
                        UsageBar(pct: r['pct'] as num?, leading: dual(r['ko'] as String?, r['name'] as String)),
                    ])),
              ])),
              box(Column(children: [
                Section('성격',
                    child: Column(children: [
                      for (final r in (u['natures'] as List).cast<Json>())
                        UsageBar(
                          pct: r['pct'] as num?,
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
                      onTap: () => context.push(pokemonPath(m['id'], season))),
              ])),
        Section('시즌별 순위',
            child: Wrap(spacing: 8, runSpacing: 8, children: [
              for (final h in (p['history'] as List).cast<Json>())
                Chip(
                    label: Text('${h['season']}  ${h['rank'] == null ? '-' : '#${h['rank']}'}'),
                    visualDensity: VisualDensity.compact),
            ])),
      ]);
    }, onRetry: () => ref.invalidate(request));
  }
}
