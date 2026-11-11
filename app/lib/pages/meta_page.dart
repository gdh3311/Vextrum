import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../arena_ui.dart';
import '../main.dart';
import '../team_state.dart';
import '../theme.dart';
import '../widgets.dart';
import 'team_switcher.dart';
import '../i18n.dart';

class MetaPage extends ConsumerStatefulWidget {
  const MetaPage({super.key});
  @override
  ConsumerState<MetaPage> createState() => _MetaPageState();
}

class _MetaPageState extends ConsumerState<MetaPage> {
  String q = '';
  String? type;
  int shown = 30;

  @override
  Widget build(BuildContext context) {
    final season = ref.watch(metaSeasonProvider);
    final request = seasonMetaProvider(season);
    final meta = ref.watch(request);
    return AsyncView<Json>(meta, (m) {
      final cs = Theme.of(context).colorScheme;
      final fmtKo = m['format'] == 'Doubles' ? '더블배틀' : '싱글배틀';
      final historical = m['historical'] == true;
      final archiveSeason = historical ? m['season'] as String : null;
      final seasons = (m['seasons'] as List?)?.cast<String>() ?? const <String>[];
      final date = (m['generatedAt'] as String?)?.split('T').first;
      final ranking = (m['ranking'] as List).cast<Json>();
      final filtering = q.isNotEmpty || type != null;
      final filtered = !filtering
          ? ranking
          : ranking
              .where((p) =>
                  (type == null || (p['types'] as List).contains(type)) &&
                  (q.isEmpty ||
                      (p['name'] as String).toLowerCase().contains(q) ||
                      ((p['ko'] ?? '') as String).contains(q)))
              .toList();
      final visible = filtered.take(filtering ? 300 : shown).toList();
      final seasonPicker = FilterDropdown(
        value: season,
        allLabel: '최신 수집 시즌',
        labels: {for (final s in seasons.skip(1)) s: '시즌 $s'},
        onChanged: (value) {
          ref.read(metaSeasonProvider.notifier).state = value;
          setState(() => shown = 30);
        },
      );

      final rankingCard = Section(
        '포켓몬 랭킹',
        trailing: seasonPicker,
        subtitle: [
          historical ? '행을 누르면 이 시즌의 채용률과 동료가 펼쳐집니다' : '행을 누르면 채용률·동료·상성 상세가 펼쳐집니다',
          if (m['prevSeason'] != null) '변동은 ${m['prevSeason']} 대비',
        ].join(' · '),
        child: LayoutBuilder(builder: (context, c) {
          final showMoves = c.maxWidth >= 620;
          final head = TextStyle(fontSize: 12, color: cs.onSurfaceVariant, fontWeight: FontWeight.w500);
          return Column(children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Wrap(spacing: 8, runSpacing: 8, children: [
                FilterDropdown(
                    value: type, allLabel: '모든 타입', labels: typeKo, onChanged: (v) => setState(() => type = v)),
                SizedBox(
                  width: 200,
                  child: TextField(
                    style: const TextStyle(fontSize: 14),
                    decoration: InputDecoration(
                        prefixIcon: LabIcon(LabGlyph.search, size: 20), hintText: tr('이름 검색'), isDense: true),
                    onChanged: (v) => setState(() => q = v.trim().toLowerCase()),
                  ),
                ),
              ]),
            ),
            const SizedBox(height: 12),
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
              child: Row(children: [
                SizedBox(width: 36, child: Text('순위', style: head)),
                SizedBox(width: 52, child: Text('변동', style: head, textAlign: TextAlign.center)),
                Expanded(flex: 3, child: Text('포켓몬', style: head)),
                SizedBox(width: 44, child: Text('도구', style: head, textAlign: TextAlign.center)),
                if (showMoves) Expanded(flex: 6, child: Text('주요 기술', style: head)),
              ]),
            ),
            const Divider(),
            for (final p in visible)
              _RankRow(p, showMoves, archiveSeason, key: ValueKey((m['format'], m['season'], p['id']))),
            if (visible.isEmpty)
              Padding(
                  padding: const EdgeInsets.all(28),
                  child: Text('검색 결과가 없습니다', style: TextStyle(color: cs.onSurfaceVariant))),
            if (!filtering && shown < ranking.length)
              Padding(
                padding: const EdgeInsets.only(top: 14),
                child: OutlinedButton(
                    onPressed: () => setState(() => shown += 50), child: Text('더 보기 · $shown / ${ranking.length}')),
              ),
          ]);
        }),
      );

      final side = [
        _Movers('상승세', (m['rising'] as List).cast<Json>(), season: archiveSeason),
        _Movers('하락세', (m['falling'] as List).cast<Json>(), season: archiveSeason),
        if (!historical) ...[
        Section('메가진화',
            subtitle: '해당 포켓몬의 메가스톤 채용률',
            child: Column(children: [
              for (final g in (m['topMegas'] as List).cast<Json>().take(6))
                _SideRow(
                    mon: g,
                    caption: '#${g['rank']}',
                    trailing: Text(fmtPct(g['pct'] as num),
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    onTap: () => context.push('/pokemon/${g['id']}')),
            ])),
        _Top('많이 쓰는 기술', (m['topMoves'] as List).cast<Json>()),
        _Top('많이 쓰는 도구', (m['topItems'] as List).cast<Json>(), items: true),
        _Top('많이 쓰는 특성', (m['topAbilities'] as List).cast<Json>()),
        ],
      ];

      return PageBody(children: [
        ArenaHero(title: '$fmtKo 메타',
            subtitle: [
              '랭킹 시즌 ${m['season']}',
              if (date != null) '$date 기준',
              '${m['total']}마리',
            ].join(' · ')),
        if (!historical)
          if (m['officialSeason'] case final Json official)
            _OfficialSeason(official, rankingSeason: m['season'] as String?),
        LayoutBuilder(builder: (context, c) {
          if (c.maxWidth >= 850) {
            return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: rankingCard),
              const SizedBox(width: 16),
              SizedBox(width: 300, child: Column(children: side)),
            ]);
          }
          return Column(children: [rankingCard, ...side]);
        }),
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text('${m['attribution']} · ${m['source']} · 비공식 팬 도구',
              textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
        ),
      ]);
    }, onRetry: () => ref.invalidate(request));
  }
}

class _OfficialSeason extends StatelessWidget {
  final Json data;
  final String? rankingSeason;
  const _OfficialSeason(this.data, {required this.rankingSeason});

  @override
  Widget build(BuildContext context) {
    final season = data['season'] as String;
    final rule = data['regulation'] as String;
    final theme = Theme.of(context);
    return Section(
      '공식 랭크배틀 $season · $rule',
      subtitle: rankingSeason == season
          ? '랭킹과 채용 통계도 $season 기준입니다.'
          : '$season 랭킹이 공개 데이터에 올라오기 전까지 ${rankingSeason ?? '기존'} 통계를 표시합니다.',
      child: LabExpansionTile(
        title: Text('$rule에서 추가된 포켓몬과 메가진화'),
        tilePadding: EdgeInsets.zero,
        expandedAlignment: Alignment.centerLeft,
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('M-C부터 사용 가능한 메가진화', style: theme.textTheme.titleSmall),
          const SizedBox(height: 5),
          Wrap(spacing: 6, runSpacing: 5, children: [
            for (final mon in (data['addedMegas'] as List).cast<Json>())
              MonPill(mon, onTap: () => context.push(pokemonPath(mon['id'] as String))),
          ]),
          const SizedBox(height: 10),
          Text('M-C 영입 라인업에 추가된 포켓몬', style: theme.textTheme.titleSmall),
          const SizedBox(height: 5),
          Wrap(spacing: 6, runSpacing: 5, children: [
            for (final mon in (data['roster'] as List).cast<Json>())
              if (mon['id'] case final String id)
                MonPill(mon, onTap: () => context.push(pokemonPath(id)))
              else
                Chip(label: Text(mon['ko'] as String)),
          ]),
        ],
      ),
    );
  }
}

class _RankRow extends StatefulWidget {
  final Json p;
  final bool showMoves;
  final String? season;
  const _RankRow(this.p, this.showMoves, this.season, {super.key});
  @override
  State<_RankRow> createState() => _RankRowState();
}

class _RankRowState extends State<_RankRow> {
  bool open = false;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final p = widget.p;
    final rank = p['rank'] as int;
    final types = p['types'] as List;
    final reduced = MediaQuery.disableAnimationsOf(context);
    const medal = [Color(0xFFFFCB68), Color(0xFFA9C9E8), Color(0xFFEDAE92)];
    return Container(
      decoration: BoxDecoration(
          color: open ? cs.surfaceContainer.withOpacity(.5) : null,
          border: Border(bottom: BorderSide(color: cs.outlineVariant))),
      child: Column(children: [
        InkWell(
          onTap: () => setState(() => open = !open),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 9, horizontal: 4),
            child: Row(children: [
              SizedBox(width: 36, child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 3),
                    decoration: rank <= 3
                        ? BoxDecoration(color: medal[rank - 1].withOpacity(.18), borderRadius: BorderRadius.circular(6))
                        : null,
                    child: Text('$rank',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          fontFeatures: const [FontFeature.tabularFigures()],
                          color: rank <= 3 && Theme.of(context).brightness == Brightness.dark
                              ? medal[rank - 1] : cs.onSurface)),
                  ))),
              SizedBox(width: 52, child: Center(child: Delta(p['delta'] as int?))),
              Expanded(
                flex: 3,
                child: Row(children: [
                  SpriteBadge((p['megaSprite'] ?? p['sprite']) as String, size: 46, type: types.firstOrNull as String?),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      NameBlock(p['ko'] as String?, p['name'] as String),
                      const SizedBox(height: 4),
                      TypeRow(p['types'] as List, dense: true),
                    ]),
                  ),
                ]),
              ),
              SizedBox(
                width: 44,
                child: p['topItem'] == null
                    ? null
                    : Tooltip(
                        message: '${p['topItemKo'] ?? p['topItem']} · ${p['topItem']}',
                        child: Center(child: ItemIcon(p['topItem'] as String, size: 26))),
              ),
              if (widget.showMoves)
                Expanded(
                  flex: 6,
                  child: Wrap(spacing: 6, runSpacing: 6, children: [
                    for (final mv in (p['topMoves'] as List).cast<Json>())
                      MoveChip(mv['name'] as String, ko: mv['ko'] as String?, type: mv['type'] as String?),
                  ]),
                ),
              LabIcon(open ? LabGlyph.up : LabGlyph.down, size: 22, color: cs.onSurfaceVariant),
            ]),
          ),
        ),
        AnimatedSize(
          alignment: Alignment.topCenter,
          duration: reduced ? Duration.zero : const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          child: open ? _RankDetail(p['id'] as String, widget.season) : const SizedBox.shrink(),
        ),
      ]),
    );
  }
}

/// 랭킹 행을 펼쳤을 때: 채용률 상세, 동료, 상성, 시즌 추이
class _RankDetail extends ConsumerWidget {
  final String id;
  final String? season;
  const _RankDetail(this.id, this.season);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final request = season == null ? pokemonDetailProvider(id) : seasonDetailProvider((id, season!));
    final detail = ref.watch(request);
    final team = season == null ? ref.watch(teamProvider) : const <TeamSlot>[];
    final label = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant, fontWeight: FontWeight.w500);
    return detail.when(
      loading: () => const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator())),
      error: (_, __) => Padding(
        padding: const EdgeInsets.all(20),
        child: TextButton(onPressed: () => ref.invalidate(request), child: const Text('상세 데이터 다시 불러오기')),
      ),
      data: (d) {
        final u = d['usage'] as Json?;
        if (u == null) return const Padding(padding: EdgeInsets.all(20), child: Text('이 포맷의 사용 데이터가 없습니다'));
        final spreads = (u['spreads'] as List).cast<Json>();
        Widget block(String title, List<Widget> children) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [Text(title, style: label), const SizedBox(height: 6), ...children]);
        Widget bars(List rows, {bool items = false, int take = 6}) => Column(children: [
              for (final r in rows.cast<Json>().take(take))
                UsageBar(
                  pct: r['pct'] as num?,
                  leading: Row(children: [
                    if (items) ...[ItemIcon(r['name'] as String, size: 18), const SizedBox(width: 7)],
                    if (r['type'] != null) ...[TypeDot(r['type'] as String), const SizedBox(width: 7)],
                    Flexible(
                        child: Text('${r['ko'] ?? r['name']}',
                            style: const TextStyle(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis)),
                  ]),
                ),
            ]);
        Widget mons(List rows, String Function(Json) caption) => rows.isEmpty
            ? Text('해당 없음', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant))
            : Wrap(spacing: 6, runSpacing: 6, children: [
                for (final m in rows.cast<Json>().take(6))
                  MonPill(m, caption: caption(m), onTap: () => context.push(pokemonPath(m['id'], season))),
              ]);
        return Padding(
          padding: const EdgeInsets.fromLTRB(16, 6, 16, 18),
          child: LayoutBuilder(builder: (context, c) {
            final cols = c.maxWidth >= 760 ? 3 : (c.maxWidth >= 480 ? 2 : 1);
            final w = (c.maxWidth - (cols - 1) * 24) / cols;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (d['snapshotDate'] != null) ...[
                Text('시즌 $season · ${d['snapshotDate']} ${d['previewOnly'] == true ? '요약' : '스냅샷'}', style: label),
                const SizedBox(height: 10),
              ],
              if (d['previewOnly'] == true)
                TextButton(onPressed: () => ref.invalidate(request), child: const Text('전체 채용률 다시 불러오기')),
              Wrap(spacing: 24, runSpacing: 18, children: [
                SizedBox(width: w, child: block('기술 채용률', [bars(u['moves'] as List, take: 8)])),
                SizedBox(
                  width: w,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    block('도구', [bars(u['items'] as List, items: true, take: 5)]),
                    const SizedBox(height: 14),
                    block('특성', [bars(u['abilities'] as List, take: 3)]),
                  ]),
                ),
                SizedBox(
                  width: w,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    block('성격', [
                      for (final r in (u['natures'] as List).cast<Json>().take(3))
                        UsageBar(
                            pct: r['pct'] as num?,
                            leading: Text(natureLabel(r['name'] as String, r['ko'] as String?),
                                style: const TextStyle(fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis)),
                    ]),
                    const SizedBox(height: 14),
                    block('능력 포인트 (HP/공격/방어/특공/특방/스피드)', [
                      for (final r in spreads.take(3))
                        UsageBar(
                            pct: r['pct'] as num,
                            leading: Text(statKeys.map((k) => '${r[k]}').join(' / '),
                                style: const TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()]))),
                    ]),
                  ]),
                ),
              ]),
              const SizedBox(height: 18),
              Wrap(spacing: 24, runSpacing: 18, children: [
                SizedBox(
                    width: w,
                    child: block('함께 쓰는 포켓몬', [mons(u['teammates'] as List, (m) => m['rank'] == null ? '${m['name']}' : '${m['rank']}위')])),
                if (season == null) ...[SizedBox(
                    width: w,
                    child: block('잘 잡는 상대',
                        [mons(d['targets'] as List, (m) => '${m['moveKo'] ?? m['move'] ?? '-'} ${fmtPct(m['pct'] as num)}')])),
                SizedBox(
                    width: w,
                    child: block('조심할 상대', [
                      mons(d['counters'] as List,
                          (m) => '${m['takenMoveKo'] ?? m['takenMove'] ?? '-'} ${fmtPct(m['takenPct'] as num)}')
                    ])),],
              ]),
              const SizedBox(height: 18),
              Row(children: [
                Expanded(
                  child: Wrap(spacing: 14, runSpacing: 6, crossAxisAlignment: WrapCrossAlignment.center, children: [
                    Text('시즌별 순위', style: label),
                    for (final h in (d['history'] as List).cast<Json>())
                      Text('${h['season']} ${h['rank'] == null ? '-' : '${h['rank']}위'}',
                          style: const TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()])),
                  ]),
                ),
                TextButton(onPressed: () => context.push(pokemonPath(id, season)), child: const Text('전체 상세 보기')),
                if (season == null) ...[
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: team.length >= 6
                      ? null
                      : () async {
                          await ref.read(teamProvider.notifier).add(id);
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                                content: Text('${d['ko'] ?? d['name']} — 팀에 추가했습니다'),
                                action: SnackBarAction(label: tr('팀 보기'), onPressed: () => context.go('/team'))));
                          }
                        },
                  icon: const LabIcon(LabGlyph.plus, size: 18),
                  label: Text(team.length >= 6 ? '팀이 가득 참' : '팀에 추가'),
                ),],
              ]),
            ]);
          }),
        );
      },
    );
  }
}

/// 순위 변동 표시
class Delta extends StatelessWidget {
  final int? delta;
  const Delta(this.delta, {super.key});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (delta == null) {
      return Text('NEW', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: cs.primary));
    }
    if (delta == 0) return Text('–', style: TextStyle(color: cs.onSurfaceVariant));
    final up = delta! > 0;
    return Text('${up ? '▲' : '▼'} ${delta!.abs()}',
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: up ? good : bad));
  }
}

class _SideRow extends StatelessWidget {
  final Json mon;
  final String caption;
  final Widget trailing;
  final VoidCallback onTap;
  const _SideRow({required this.mon, required this.caption, required this.trailing, required this.onTap});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 2),
        child: Row(children: [
          Sprite(mon['sprite'] as String, size: 36),
          const SizedBox(width: 10),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${mon['ko'] ?? mon['name']}',
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
              Text(caption, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            ]),
          ),
          trailing,
        ]),
      ),
    );
  }
}

class _Movers extends StatelessWidget {
  final String title;
  final List<Json> rows;
  final String? season;
  const _Movers(this.title, this.rows, {this.season});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Section(title,
        child: rows.isEmpty
            ? Text('큰 변동이 없습니다', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant))
            : Column(children: [
                for (final r in rows.take(5))
                  _SideRow(
                      mon: r,
                      caption: '${r['prevRank']}위 → ${r['rank']}위',
                      trailing: Delta(r['delta'] as int?),
                      onTap: () => context.push(pokemonPath(r['id'], season))),
              ]));
  }
}

class _Top extends StatelessWidget {
  final String title;
  final List<Json> rows;
  final bool items;
  const _Top(this.title, this.rows, {this.items = false});
  @override
  Widget build(BuildContext context) => Section(title,
      subtitle: '상위 50마리 평균 채용률',
      child: Column(children: [
        for (final r in rows.take(8))
          UsageBar(
            pct: r['share'] as num,
            leading: Row(children: [
              if (items) ...[ItemIcon(r['name'] as String, size: 20), const SizedBox(width: 8)],
              if (r['type'] != null) ...[TypeDot(r['type'] as String), const SizedBox(width: 8)],
              Flexible(
                  child: Text('${r['ko'] ?? r['name']}',
                      style: const TextStyle(fontSize: 13.5), maxLines: 1, overflow: TextOverflow.ellipsis)),
            ]),
          ),
      ]));
}
