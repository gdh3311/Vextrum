import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../main.dart';
import '../widgets.dart';

class MetaPage extends ConsumerStatefulWidget {
  const MetaPage({super.key});
  @override
  ConsumerState<MetaPage> createState() => _MetaPageState();
}

class _MetaPageState extends ConsumerState<MetaPage> {
  String q = '';
  int shown = 50;

  @override
  Widget build(BuildContext context) {
    final meta = ref.watch(metaProvider);
    return AsyncView<Json>(meta, (m) {
      final fmtKo = m['format'] == 'Doubles' ? '더블배틀' : '싱글배틀';
      final ranking = (m['ranking'] as List).cast<Json>();
      final filtered = q.isEmpty
          ? ranking
          : ranking
              .where((p) =>
                  (p['name'] as String).toLowerCase().contains(q) || ((p['ko'] ?? '') as String).contains(q))
              .toList();
      final visible = filtered.take(q.isEmpty ? shown : 300).toList();
      final t = Theme.of(context);
      return PageBody(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
          child: Wrap(crossAxisAlignment: WrapCrossAlignment.end, spacing: 12, children: [
            Text('시즌 ${m['season']} · $fmtKo',
                style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
            Text('데이터 기준 ${(m['generatedAt'] as String).substring(0, 10)} · 총 ${m['total']}마리',
                style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
          ]),
        ),
        LayoutBuilder(builder: (context, c) {
          final cols = c.maxWidth >= 820 ? 2 : 1;
          final w = (c.maxWidth - (cols - 1) * 12) / cols;
          return Wrap(spacing: 12, children: [
            SizedBox(
              width: w,
              child: Section('🔥 상승세', subtitle: '지난 시즌(${m['prevSeason']}) 대비 순위 상승', child: _movers(m['rising'])),
            ),
            SizedBox(
              width: w,
              child:
                  Section('📉 하락세', subtitle: '지난 시즌(${m['prevSeason']}) 대비 순위 하락', child: _movers(m['falling'])),
            ),
          ]);
        }),
        Section('메가진화 채용 순위',
            subtitle: '순위 가중 채용률 기준',
            child: Wrap(spacing: 8, runSpacing: 8, children: [
              for (final g in (m['topMegas'] as List).cast<Json>())
                MonPill(g,
                    caption: '#${g['rank']} · ${fmtPct(g['pct'] as num)} 채용',
                    onTap: () => context.push('/pokemon/${g['id']}')),
            ])),
        LayoutBuilder(builder: (context, c) {
          final cols = c.maxWidth >= 900 ? 3 : (c.maxWidth >= 560 ? 2 : 1);
          final w = (c.maxWidth - (cols - 1) * 12) / cols;
          Widget list(String title, List rows, {bool items = false}) => SizedBox(
                width: w,
                child: Section(title,
                    subtitle: '상위 50마리의 평균 채용률',
                    child: Column(children: [
                      for (final r in rows.cast<Json>())
                        UsageBar(
                          pct: r['share'] as num,
                          color: typeColor[r['type']],
                          leading: Row(children: [
                            if (items) ...[ItemIcon(r['name'] as String), const SizedBox(width: 6)],
                            if (r['type'] != null) ...[TypeChip(r['type'] as String, dense: true), const SizedBox(width: 6)],
                            Flexible(child: _dual(context, r['ko'] as String?, r['name'] as String)),
                          ]),
                        ),
                    ])),
              );
          return Wrap(spacing: 12, children: [
            list('많이 쓰는 기술', m['topMoves'] as List),
            list('많이 쓰는 도구', m['topItems'] as List, items: true),
            list('많이 쓰는 특성', m['topAbilities'] as List),
          ]);
        }),
        Section(
          '포켓몬 랭킹',
          subtitle: '게임 내 사용 순위 (원본 데이터에 사용률 %는 없고 순위만 제공됩니다)',
          trailing: SizedBox(
            width: 220,
            child: TextField(
              decoration:
                  const InputDecoration(prefixIcon: Icon(Icons.search), hintText: '검색 (한글/영문)', isDense: true),
              onChanged: (v) => setState(() => q = v.trim().toLowerCase()),
            ),
          ),
          child: Column(children: [
            for (final p in visible) _RankRow(p),
            if (q.isEmpty && shown < ranking.length)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: OutlinedButton(
                    onPressed: () => setState(() => shown += 50), child: Text('더 보기 ($shown / ${ranking.length})')),
              ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text('${m['attribution']} (${m['source']}) · 비공식 팬 도구',
              textAlign: TextAlign.center,
              style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        ),
      ]);
    }, onRetry: () => ref.invalidate(metaProvider));
  }

  Widget _movers(dynamic rows) {
    final list = (rows as List).cast<Json>();
    if (list.isEmpty) return const Text('큰 변동이 없습니다');
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final r in list)
        MonPill(r,
            caption: '#${r['prevRank']} → #${r['rank']}', onTap: () => context.push('/pokemon/${r['id']}')),
    ]);
  }
}

Widget _dual(BuildContext context, String? ko, String name) => Text.rich(
      TextSpan(children: [
        TextSpan(text: ko ?? name, style: const TextStyle(fontWeight: FontWeight.w600)),
        if (ko != null)
          TextSpan(
              text: '  $name',
              style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ]),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: const TextStyle(fontSize: 13),
    );

class _RankRow extends StatelessWidget {
  final Json p;
  const _RankRow(this.p);
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final delta = p['delta'] as int?;
    final wide = MediaQuery.sizeOf(context).width >= 760;
    Widget trend;
    if (delta == null) {
      trend = Text('NEW', style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: cs.tertiary));
    } else if (delta == 0) {
      trend = Text('–', style: TextStyle(color: cs.onSurfaceVariant));
    } else {
      final up = delta > 0;
      trend = Text('${up ? '▲' : '▼'}${delta.abs()}',
          style: TextStyle(
              fontSize: 12, fontWeight: FontWeight.w700, color: up ? const Color(0xFF1E9E55) : const Color(0xFFD64545)));
    }
    return InkWell(
      onTap: () => context.push('/pokemon/${p['id']}'),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
        child: Row(children: [
          SizedBox(
              width: 38,
              child: Text('${p['rank']}',
                  textAlign: TextAlign.right, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800))),
          SizedBox(width: 44, child: Center(child: trend)),
          Sprite(p['sprite'] as String, size: 44),
          if (p['megaSprite'] != null)
            Tooltip(
                message: '주로 메가진화: ${p['megaKo'] ?? p['megaName']}',
                child: Sprite(p['megaSprite'] as String, size: 34)),
          const SizedBox(width: 8),
          Expanded(
            flex: 3,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              NameBlock(p['ko'] as String?, p['name'] as String),
              const SizedBox(height: 2),
              TypeRow(p['types'] as List, dense: true),
            ]),
          ),
          if (p['topItem'] != null)
            Tooltip(
              message: '${p['topItemKo'] ?? p['topItem']} (${p['topItem']})',
              child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8), child: ItemIcon(p['topItem'] as String, size: 26)),
            ),
          if (wide)
            Expanded(
              flex: 5,
              child: Wrap(spacing: 4, runSpacing: 4, children: [
                for (final mv in (p['topMoves'] as List).cast<Json>())
                  MoveChip(mv['name'] as String, ko: mv['ko'] as String?, type: mv['type'] as String?),
              ]),
            ),
        ]),
      ),
    );
  }
}
