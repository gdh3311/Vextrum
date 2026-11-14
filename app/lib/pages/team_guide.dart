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
  final List<Json> sets;
  final String format;
  const TeamTabs({super.key, required this.guide, required this.analysis,
    this.sets = const [], this.format = 'Doubles'});

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
      if (tab == 'guide')
        (guide == null ? const SizedBox() : TeamGuide(guide!, sets: sets, format: format,
          onPractice: (plan) => context.go('/battle', extra: plan)))
      else analysis,
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
  final ValueChanged<Json>? onPractice;
  final List<Json> sets;
  final String format;
  const TeamGuide(this.g, {super.key, this.onPractice, this.sets = const [], this.format = 'Doubles'});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final lead = g['lead'] as Json?;
    final plans = (g['plans'] as List? ?? const []).cast<Json>();
    final alternatives = (g['alternatives'] as List? ?? const []).cast<Json>();
    final testStyles = (g['testStyles'] as List? ?? const []).cast<Json>();
    final rosterAxes = (g['rosterAxes'] as List? ?? const []).cast<Json>();
    final coverage = g['rulesCoverage'] as Json?;
    final issues = (coverage?['issues'] as List? ?? const []).cast<Json>();
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
      if (issues.isNotEmpty)
        Section(
          '모의전 규칙 범위',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final issue in issues)
              Text("${issue['name']} · ${issue['status'] == 'UNSIMULATABLE' ? tr('시뮬 미구현') : tr('규칙 미검증')}",
                  style: muted),
          ]),
        ),
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
        '현재 선출의 운영법',
        subtitle: '아래 선봉과 후발이 가진 기술·특성 기준',
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
                    if (a['activations'] is int && lead?['runs'] != null)
                      Text("이 선출에서 전개 ${a['activations']}/${lead!['runs']}판", style: muted),
                  ]),
                ),
              ]),
            ),
        ]),
      ),
      if (lead != null)
        Section(
          lead['evidence'] == 'simulation' ? '모의전에서 자주 나온 선출' : '기본 선출 후보',
          subtitle: lead['evidence'] == 'simulation'
              ? "${lead['against']} 상대 · ${lead['runs']}판 ${lead['win']}승"
              : '메타 상위권을 기준으로 계산한 선출',
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
            if (sets.length >= (format == 'Doubles' ? 4 : 3) && lead['evidence'] != 'simulation')
              _VerifySelection(sets: sets, format: format, selection: lead,
                styles: testStyles, onPractice: onPractice),
          ]),
        ),
      if ((g['winConditions'] as List).isNotEmpty)
        Section(
          '이론상 공격 범위',
          subtitle: '예상 피해와 기본 명중을 반영한 범위 점수',
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
        subtitle: '현재 선출에서 쓸 수 있는 기술과 특성',
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
                  width: 78,
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: switch (r['level']) {
                      'good' || 'ok' => const _Badge('수단 있음', good),
                      _ => const _Badge('미확인', even),
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
        '위험한 상대와 예상 피해',
        subtitle: '현재 선출과 상대의 대표 세트로 계산한 이론값',
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
                    for (final hit in (t['damage'] as List? ?? const []).cast<Json>())
                      if (hit['observed'] case final Json observed)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 5),
                          child: Text(
                            "모의전 기록 · ${observed['attempts']}회 시도 · ${observed['hits']}회 명중 · ${observed['kos']}회 KO",
                            style: muted,
                          ),
                        ),
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
      if (alternatives.isNotEmpty)
        Section(
          '다른 선출의 전략',
          subtitle: '세트에서 계산한 이론상 대응',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final a in alternatives)
              LabExpansionTile(
                title: Text(a['label'] as String),
                tilePadding: EdgeInsets.zero,
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(spacing: 20, runSpacing: 8, children: [
                    group('선봉', a['lead'] as List, strong: true),
                    group('후발', a['back'] as List),
                  ]),
                  Padding(padding: const EdgeInsets.only(top: 8), child: Text(a['play'] as String, style: body)),
                  if (sets.length >= (format == 'Doubles' ? 4 : 3))
                    _VerifySelection(sets: sets, format: format, selection: a,
                      styles: testStyles, onPractice: onPractice),
                ],
              ),
          ]),
        ),
      if (rosterAxes.isNotEmpty)
        Section(
          '6마리의 이론상 대응',
          child: LabExpansionTile(
            title: const Text('전체 팀의 전략 요소 보기'),
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final axis in rosterAxes)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text("${axis['label']} · ${(axis['members'] as List).map((m) => m['ko'] ?? m['name']).join(' · ')}",
                    style: body),
                ),
            ],
          ),
        ),
      if (plans.isNotEmpty)
        Section(
          '상대 전략별 모의전 기록',
          subtitle: '관측된 선봉·후발, 첫 턴 행동과 전적',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final plan in plans)
              LabExpansionTile(
                title: Text("${plan['against']} · ${plan['runs']}판 ${plan['win']}승"),
                tilePadding: EdgeInsets.zero,
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(spacing: 20, runSpacing: 8, children: [
                    group('선봉', plan['lead'] as List, strong: true),
                    group('후발', plan['back'] as List),
                  ]),
                  if ((plan['opening'] as List).isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        "관측된 첫 턴 · ${(plan['opening'] as List).join(' / ')}"
                        " · ${plan['openingRuns']}회 ${plan['openingWins']}승",
                        style: body,
                      ),
                    ),
                  if (plan['openingAgreement'] case final num agreement when agreement > 0)
                    Text("같은 선출에서 첫 턴 행동 일치율 ${fmtPct(100 * agreement)}", style: muted),
                  for (final condition in {
                    for (final claim in (plan['openingClaims'] as List? ?? const []).cast<Json>())
                      ...(claim['preconditions'] as List).cast<String>(),
                  }) Text(condition, style: muted),
                  for (final axis in (plan['axes'] as List).cast<Json>())
                    if ((axis['activations'] as int? ?? 0) > 0)
                      Text("${axis['label']} 전개 ${axis['activations']}/${plan['runs']}판", style: muted),
                  if (onPractice != null && plan['sample'] != null)
                    TextButton.icon(
                      onPressed: () => onPractice!(plan),
                      icon: const LabIcon(LabGlyph.versus, size: 18),
                      label: const Text('같은 상대와 이 선출로 연습'),
                    ),
                ],
              ),
          ]),
        ),
    ]);
  }
}

class _VerifySelection extends StatefulWidget {
  const _VerifySelection({required this.sets, required this.format, required this.selection,
    required this.styles, this.onPractice});

  final List<Json> sets;
  final String format;
  final Json selection;
  final List<Json> styles;
  final ValueChanged<Json>? onPractice;

  @override
  State<_VerifySelection> createState() => _VerifySelectionState();
}

class _VerifySelectionState extends State<_VerifySelection> {
  bool busy = false;
  bool failed = false;
  Json? result;
  String style = '';

  @override
  void didUpdateWidget(covariant _VerifySelection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selection != widget.selection) {
      busy = false;
      failed = false;
      result = null;
      style = '';
    }
  }

  Future<void> _verify() async {
    final selection = widget.selection;
    setState(() { busy = true; failed = false; });
    try {
      final response = await dio.post('/api/team/guide/verify', data: {
        'format': widget.format,
        'team': widget.sets,
        'selection': [for (final key in ['lead', 'back'])
          for (final mon in (selection[key] as List).cast<Json>()) mon['id']],
        if (style.isNotEmpty) 'style': style,
      });
      if (mounted && widget.selection == selection) setState(() => result = response.data as Json);
    } catch (_) {
      if (mounted && widget.selection == selection) setState(() => failed = true);
    } finally {
      if (mounted && widget.selection == selection) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final verified = result;
    final baseline = verified?['baseline'] as num?;
    final plans = (verified?['plans'] as List? ?? const []).cast<Json>();
    final tested = plans.isEmpty ? null : plans.reduce(
      (a, b) => (a['runs'] as int) >= (b['runs'] as int) ? a : b,
    );
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        if (widget.styles.isNotEmpty)
          DropdownButton<String>(
            value: style,
            items: [
              const DropdownMenuItem(value: '', child: Text('여러 상대 전략')),
              for (final option in widget.styles)
                DropdownMenuItem(value: option['id'] as String, child: Text(option['label'] as String)),
            ],
            onChanged: busy ? null : (value) => setState(() {
              style = value ?? '';
              result = null;
              failed = false;
            }),
          ),
        TextButton.icon(
          onPressed: busy ? null : _verify,
          icon: const LabIcon(LabGlyph.versus, size: 18),
          label: Text(busy ? '모의전 검증 중…' : '이 선출로 모의전 검증'),
        ),
      ]),
      if (failed) const Text('모의전 검증에 실패했습니다. 다시 시도해 주세요.'),
      if (verified != null) ...[
        Text("마스터볼 CPU · ${verified['runs']}판 · 승점률 ${fmtPct(100 * (verified['rate'] as num))}"
            "${baseline != null ? ' · 상대별 자동 선출 ${fmtPct(100 * baseline)}' : ''}"),
        if (baseline == null) const Text('자동 선출의 미구현 요소로 비교 전적이 보류됐습니다.'),
        if (tested != null && (tested['opening'] as List).isNotEmpty)
          Text("${tested['against']} 상대 첫 턴 · ${(tested['opening'] as List).join(' / ')}"
              " · ${tested['openingRuns']}/${tested['runs']}판 관측"),
        if (tested?['sample'] != null && widget.onPractice != null)
          TextButton(
            onPressed: () => widget.onPractice!(tested!),
            child: const Text('같은 상대와 이 선출로 연습'),
          ),
      ],
    ]);
  }
}
