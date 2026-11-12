/// 추천 파티 연구소: 랭커 코어 분석, 추천 조건(조커·평가 깊이·CPU·랭커 비중), 랭커 파티 상대 전적.
import 'package:dio/dio.dart' show Options;
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../settings.dart' show apiContextProvider;
import '../theme.dart';
import '../widgets.dart';
import 'battle_console.dart';
import 'parties_page.dart';
import 'sim_insights.dart';

class PartyLabOptions {
  final String joker;
  final String depth;
  final String cpu;
  final double rankerWeight;
  const PartyLabOptions(
      {this.joker = 'allow',
      this.depth = 'standard',
      this.cpu = 'ultra',
      this.rankerWeight = .5});

  PartyLabOptions copyWith(
          {String? joker, String? depth, String? cpu, double? rankerWeight}) =>
      PartyLabOptions(
          joker: joker ?? this.joker,
          depth: depth ?? this.depth,
          cpu: cpu ?? this.cpu,
          rankerWeight: rankerWeight ?? this.rankerWeight);

  Map<String, Object> query(String format) => {
        'format': format,
        'joker': joker,
        'depth': depth,
        'cpu': cpu,
        'rankerWeight': rankerWeight.toStringAsFixed(2),
      };

  @override
  bool operator ==(Object other) =>
      other is PartyLabOptions &&
      other.joker == joker &&
      other.depth == depth &&
      other.cpu == cpu &&
      other.rankerWeight == rankerWeight;

  @override
  int get hashCode => Object.hash(joker, depth, cpu, rankerWeight);
}

/// 화면에서 고르는 중인 조건
final partyLabDraftProvider =
    StateProvider<PartyLabOptions>((ref) => const PartyLabOptions());

/// 실제로 실행한 조건 (null 이면 아직 실행 전)
final partyLabRunProvider = StateProvider<PartyLabOptions?>((ref) => null);

final partyResearchProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  final format = ref.watch(formatProvider);
  return (await dio.get('/api/parties/research',
          queryParameters: {'format': format}))
      .data as Json;
});

final partyLabProvider = FutureProvider<Json?>((ref) async {
  ref.watch(apiContextProvider);
  final options = ref.watch(partyLabRunProvider);
  if (options == null) return null;
  final format = ref.watch(formatProvider);
  return (await dio.get('/api/parties/simulated',
          queryParameters: options.query(format),
          options: Options(receiveTimeout: const Duration(minutes: 15))))
      .data as Json;
});

const _depths = {
  'quick': ('빠르게', '약 15초'),
  'standard': ('표준', '약 30초'),
  'deep': ('정밀', '약 2분'),
};
const _jokers = {
  'off': ('제외', '사용률 40위 안의 포켓몬으로만 만듭니다.'),
  'allow': ('허용', '조커를 넣은 팀과 뺀 팀을 함께 검증해 비교합니다.'),
  'force': ('1마리 필수', '팀마다 사용률 40위 밖의 조커를 1마리 넣습니다.'),
};

class PartyLab extends ConsumerWidget {
  const PartyLab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final run = ref.watch(partyLabRunProvider);
    final result = ref.watch(partyLabProvider);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const _Research(),
      const _Options(),
      if (run != null)
        if (result.isLoading)
          BattleLoading(tr('{} 기준으로 후보를 만들고 메타 상대군·랭커 파티와 싸우는 중… ({})')
              .replaceFirst('{}', tr(_depths[run.depth]!.$1))
              .replaceFirst('{}', tr(_depths[run.depth]!.$2)))
        else
          AsyncView<Json?>(result, (d) => d == null ? const SizedBox() : PartyLabResults(d),
              onRetry: () => ref.invalidate(partyLabProvider)),
    ]);
  }
}

class _Research extends ConsumerWidget {
  const _Research();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(partyResearchProvider);
    final theme = Theme.of(context);
    return data.maybeWhen(
      data: (d) {
        final cores = (d['cores'] as List).cast<Json>();
        if (cores.isEmpty) return const SizedBox();
        return Section('랭커 연구',
            subtitle: tr('시즌 최종 상위 랭커 {}팀에서 함께 쓰인 코어')
                .replaceFirst('{}', '${d['rankers']}'),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                  '상위권일수록 무겁게 세었습니다. 배율은 각 포켓몬의 채용 빈도로 기대되는 것보다 얼마나 더 자주 함께 쓰였는지입니다. 이 코어들을 추천의 시작점으로 씁니다.',
                  style: theme.textTheme.bodySmall),
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final core in cores)
                  Container(
                    padding: const EdgeInsets.fromLTRB(6, 4, 10, 4),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHigh,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      for (final s in (core['sprites'] as List).cast<String>())
                        Sprite(s, size: 30),
                      const SizedBox(width: 6),
                      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text((core['names'] as List).join(' + '),
                            style: theme.textTheme.labelMedium),
                        Text(
                            tr('{}팀 · 배율 ×{}')
                                .replaceFirst('{}', '${core['teams']}')
                                .replaceFirst('{}', '${core['lift']}'),
                            style: theme.textTheme.bodySmall),
                      ]),
                    ]),
                  ),
              ]),
            ]));
      },
      orElse: () => const SizedBox(),
    );
  }
}

class _Options extends ConsumerWidget {
  const _Options();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final o = ref.watch(partyLabDraftProvider);
    final run = ref.watch(partyLabRunProvider);
    final busy = ref.watch(partyLabProvider).isLoading && run != null;
    final set = ref.read(partyLabDraftProvider.notifier);
    final theme = Theme.of(context);
    final compact = MediaQuery.sizeOf(context).width < 520;
    Widget label(String text) => Padding(
          padding: const EdgeInsets.only(top: 12, bottom: 6),
          child: Text(text, style: theme.textTheme.titleSmall),
        );
    return Section('추천 조건',
        subtitle: '같은 상대와 같은 난수로 모든 후보를 비교합니다',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          label('조커 포켓몬'),
          SegmentedButton<String>(
            showSelectedIcon: !compact,
            segments: [
              for (final e in _jokers.entries)
                ButtonSegment(value: e.key, label: Text(e.value.$1)),
            ],
            selected: {o.joker},
            onSelectionChanged: (v) => set.state = o.copyWith(joker: v.first),
          ),
          const SizedBox(height: 4),
          Text(_jokers[o.joker]!.$2, style: theme.textTheme.bodySmall),
          label('평가 깊이'),
          SegmentedButton<String>(
            showSelectedIcon: !compact,
            segments: [
              for (final e in _depths.entries)
                ButtonSegment(value: e.key, label: Text(e.value.$1)),
            ],
            selected: {o.depth},
            onSelectionChanged: (v) => set.state = o.copyWith(depth: v.first),
          ),
          const SizedBox(height: 4),
          Text(
              {
                'quick': '후보마다 메타 16판 + 랭커 파티별 1판으로 거르고, 4팀을 메타 48판 + 랭커 파티별 2판으로 검증합니다.',
                'standard': '후보마다 메타 24판 + 랭커 파티별 1판으로 거르고, 6팀을 메타 96판 + 랭커 파티별 4판으로 검증합니다.',
                'deep': '후보마다 메타 40판 + 랭커 파티별 2판으로 거르고, 8팀을 메타 200판 + 랭커 파티별 8판으로 검증합니다.',
              }[o.depth]!,
              style: theme.textTheme.bodySmall),
          label('최종 검증 CPU'),
          SegmentedButton<String>(
            showSelectedIcon: !compact,
            segments: const [
              ButtonSegment(value: 'ultra', label: Text('하이퍼볼')),
              ButtonSegment(value: 'master', label: Text('마스터볼')),
              ButtonSegment(value: 'champion', label: Text('챔피언')),
            ],
            selected: {o.cpu},
            onSelectionChanged: (v) => set.state = o.copyWith(cpu: v.first),
          ),
          if (o.cpu == 'champion')
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text('챔피언 CPU는 한 판이 약 15배 느립니다. 빠르게 깊이를 권장합니다.',
                  style: theme.textTheme.bodySmall?.copyWith(color: even)),
            ),
          label('평가 비중'),
          Row(children: [
            Text('메타 상대군', style: theme.textTheme.bodySmall),
            Expanded(
              child: Slider(
                value: o.rankerWeight,
                divisions: 4,
                label: tr('랭커 파티 {}%')
                    .replaceFirst('{}', '${(o.rankerWeight * 100).round()}'),
                onChanged: (v) => set.state = o.copyWith(rankerWeight: v),
              ),
            ),
            Text('랭커 파티', style: theme.textTheme.bodySmall),
          ]),
          Text(
              tr('종합 점수 = 메타 상대군 승률 {}% + 랭커 파티 상대 승률 {}%')
                  .replaceFirst('{}', '${((1 - o.rankerWeight) * 100).round()}')
                  .replaceFirst('{}', '${(o.rankerWeight * 100).round()}'),
              style: theme.textTheme.bodySmall),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed: busy
                ? null
                : () {
                    if (run == o) ref.invalidate(partyLabProvider);
                    ref.read(partyLabRunProvider.notifier).state = o;
                  },
            icon: const LabIcon(LabGlyph.spark),
            label: Text(busy
                ? '검증 중'
                : run == null
                    ? '추천 파티 만들기'
                    : run == o
                        ? '같은 조건으로 다시 보기'
                        : '이 조건으로 다시 만들기'),
          ),
        ]));
  }
}

String _pct(num rate) => fmtPct(100 * rate);

double _metaRate(Json sim) =>
    ((sim['win'] as int) + .5 * (sim['draw'] as int)) / (sim['runs'] as int);

class PartyLabResults extends StatelessWidget {
  final Json data;
  const PartyLabResults(this.data, {super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final candidates = (data['candidates'] as List).cast<Json>();
    final ev = data['evaluation'] as Json;
    final comparison = data['jokerComparison'] as Json?;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Section('추천 순위',
          subtitle: tr('후보 {}팀 · 총 {}판 · 최종 검증 {} CPU')
              .replaceFirst('{}', '${ev['drafts']}')
              .replaceFirst('{}', '${ev['battles']}')
              .replaceFirst('{}', tr(cpuLabels[ev['cpu']] ?? '하이퍼볼')),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _RankingTable(candidates),
            if (comparison != null) ...[
              const SizedBox(height: 12),
              _JokerVerdict(comparison),
            ],
          ])),
      for (final party in candidates)
        PartyCard(party: party, key: ValueKey(('lab', party['id'], ev))),
      Text(
          '승률은 앱의 배틀 엔진과 CPU 기준입니다. 랭커 파티는 공개된 종 구성에 가장 흔한 세트를 입혀 재현했습니다.',
          style: theme.textTheme.bodySmall),
      const SizedBox(height: 12),
    ]);
  }
}

class _JokerVerdict extends StatelessWidget {
  final Json c;
  const _JokerVerdict(this.c);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final w = c['withJoker'] as Json, wo = c['without'] as Json;
    final diff = ((w['score'] as num) - (wo['score'] as num)) * 100;
    final better = diff > 1.5;
    final worse = diff < -1.5;
    final color = better ? good : worse ? bad : even;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(.5)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        LabIcon(LabGlyph.star, size: 20, color: color),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                better
                    ? '조커를 넣는 편이 좋았습니다'
                    : worse
                        ? '조커 없이 가는 편이 좋았습니다'
                        : '조커 유무의 차이가 작습니다',
                style: theme.textTheme.titleSmall),
            const SizedBox(height: 2),
            Text(
                tr('조커 포함 최고 {} ({}) · 조커 없음 최고 {} · 차이 {}점')
                    .replaceFirst('{}', _pct(w['score'] as num))
                    .replaceFirst('{}', (w['jokers'] as List).join(', '))
                    .replaceFirst('{}', _pct(wo['score'] as num))
                    .replaceFirst('{}', '${diff >= 0 ? '+' : ''}${diff.toStringAsFixed(1)}'),
                style: theme.textTheme.bodySmall),
          ]),
        ),
      ]),
    );
  }
}

class _RankingTable extends StatelessWidget {
  final List<Json> candidates;
  const _RankingTable(this.candidates);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final head = TextStyle(
        fontSize: 12, color: cs.onSurfaceVariant, fontWeight: FontWeight.w600);
    const numStyle =
        TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()]);
    Widget cell(Widget child, double w) => SizedBox(width: w, child: child);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          cell(Text('순위', style: head), 40),
          cell(Text('팀', style: head), 196),
          cell(Text('종합', style: head), 64),
          cell(Text('메타 상대군', style: head), 150),
          cell(Text('랭커 파티', style: head), 150),
          cell(Text('유리 · 호각 · 불리', style: head), 150),
        ]),
        const Divider(),
        for (final (i, c) in candidates.indexed)
          Builder(builder: (context) {
            final sim = c['simulation'] as Json;
            final r = c['rankers'] as Json?;
            final meta = 100 * _metaRate(sim);
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(children: [
                cell(
                    Text('${i + 1}',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: i == 0 ? cs.primary : null)),
                    40),
                cell(
                    Row(children: [
                      for (final m in (c['members'] as List).cast<Json>())
                        Stack(clipBehavior: Clip.none, children: [
                          Sprite(m['sprite'] as String, size: 26),
                          if (m['joker'] == true)
                            const Positioned(
                                right: -1,
                                top: -2,
                                child: LabIcon(LabGlyph.starFill, size: 10, color: even)),
                        ]),
                    ]),
                    196),
                cell(
                    Text(_pct(c['score'] as num),
                        style: numStyle.copyWith(fontWeight: FontWeight.w800)),
                    64),
                cell(_Rate(meta, sim['ci'] as List?), 150),
                cell(
                    r == null
                        ? const Text('-')
                        : _Rate(100 * (r['rate'] as num).toDouble(), r['ci'] as List?),
                    150),
                cell(
                    r == null
                        ? const Text('-')
                        : Row(children: [
                            _Count(r['favored'] as int, good),
                            _Count(r['even'] as int, even),
                            _Count(r['unfavored'] as int, bad),
                          ]),
                    150),
              ]),
            );
          }),
      ]),
    );
  }
}

class _Rate extends StatelessWidget {
  final double rate;
  final List? ci;
  const _Rate(this.rate, this.ci);
  @override
  Widget build(BuildContext context) => Row(children: [
        SizedBox(width: 80, child: WinRateBar(rate: rate, ci: ci)),
        const SizedBox(width: 8),
        Text(fmtPct(rate),
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                fontFeatures: [FontFeature.tabularFigures()])),
      ]);
}

class _Count extends StatelessWidget {
  final int n;
  final Color color;
  const _Count(this.n, this.color);
  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(right: 6),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
            color: color.withOpacity(.16), borderRadius: BorderRadius.circular(8)),
        child: Text('$n',
            style: TextStyle(
                fontSize: 13, fontWeight: FontWeight.w700, color: color)),
      );
}

const verdictLabels = {'favored': '유리', 'even': '호각', 'unfavored': '불리'};
const verdictColors = {'favored': good, 'even': even, 'unfavored': bad};

/// 랭커 파티별 상대 전적
class RankerMatchups extends StatefulWidget {
  final Json result;
  const RankerMatchups(this.result, {super.key});

  @override
  State<RankerMatchups> createState() => _RankerMatchupsState();
}

class _RankerMatchupsState extends State<RankerMatchups> {
  String? filter;
  bool all = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final r = widget.result;
    final teams = (r['teams'] as List)
        .cast<Json>()
        .where((t) => filter == null || t['verdict'] == filter)
        .toList();
    final shown = all ? teams : teams.take(6).toList();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
            tr('랭커 파티 상대 {}').replaceFirst('{}', _pct(r['rate'] as num)),
            style: theme.textTheme.titleMedium),
        Text(
            tr('{}팀 × {}판 · {}승 {}패 {}무 · {}')
                .replaceFirst('{}', '${(r['teams'] as List).length}')
                .replaceFirst('{}',
                    '${((r['runs'] as int) / (r['teams'] as List).length).round()}')
                .replaceFirst('{}', '${r['win']}')
                .replaceFirst('{}', '${r['loss']}')
                .replaceFirst('{}', '${r['draw']}')
                .replaceFirst('{}', ciText(r)),
            style: theme.textTheme.bodySmall),
        const SizedBox(height: 8),
        Wrap(spacing: 6, runSpacing: 4, children: [
          ChoiceChip(
            label: Text(tr('전체 {}').replaceFirst('{}', '${(r['teams'] as List).length}')),
            selected: filter == null,
            onSelected: (_) => setState(() => filter = null),
          ),
          for (final key in ['unfavored', 'even', 'favored'])
            ChoiceChip(
              avatar: CircleAvatar(backgroundColor: verdictColors[key], radius: 5),
              label: Text('${tr(verdictLabels[key]!)} ${r[key]}'),
              selected: filter == key,
              onSelected: (_) => setState(() => filter = key),
            ),
        ]),
        const SizedBox(height: 6),
        Text('승률이 낮은 상대부터 표시합니다.', style: theme.textTheme.bodySmall),
        const SizedBox(height: 4),
        for (final t in shown) _RankerRow(t),
        if (teams.length > 6)
          TextButton(
            onPressed: () => setState(() => all = !all),
            child: Text(all ? '접기' : tr('{}팀 더 보기').replaceFirst('{}', '${teams.length - 6}')),
          ),
      ]),
    );
  }
}

class _RankerRow extends StatelessWidget {
  final Json t;
  const _RankerRow(this.t);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = verdictColors[t['verdict']]!;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        Container(
          width: 46,
          padding: const EdgeInsets.symmetric(vertical: 3),
          alignment: Alignment.center,
          decoration: BoxDecoration(
              color: color.withOpacity(.16), borderRadius: BorderRadius.circular(8)),
          child: Text(tr(verdictLabels[t['verdict']]!),
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color)),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
                tr('{} {}위 · {}')
                    .replaceFirst('{}', '${t['season']}')
                    .replaceFirst('{}', '${t['rank']}')
                    .replaceFirst('{}', '${t['player']}'),
                style: theme.textTheme.labelMedium,
                maxLines: 1,
                overflow: TextOverflow.ellipsis),
            Wrap(children: [
              for (final m in (t['members'] as List).cast<Json>())
                Sprite(m['sprite'] as String, size: 24),
            ]),
          ]),
        ),
        Text('${t['win']}-${t['loss']}${(t['draw'] as int) > 0 ? '-${t['draw']}' : ''}',
            style: const TextStyle(
                fontWeight: FontWeight.w700,
                fontFeatures: [FontFeature.tabularFigures()])),
      ]),
    );
  }
}
