import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'parties_page.dart' show partySets;
import 'party_lab.dart' show RankerMatchups;
import 'party_simulation.dart';
import 'sim_insights.dart';
import 'team_guide.dart';

/// 팀 자동 구성 결과 한 팀: 핵심 수치 → 6마리 → 왜 이 팀인가 → 포켓몬별 이유·세트 → 상세(접힘) → 저장
class AutoTeamCard extends ConsumerStatefulWidget {
  const AutoTeamCard({super.key, required this.party, required this.index});
  final Json party;
  final int index;

  @override
  ConsumerState<AutoTeamCard> createState() => _AutoTeamCardState();
}

class _AutoTeamCardState extends ConsumerState<AutoTeamCard> {
  bool saving = false;

  Future<void> _save({bool play = false, bool edit = false, Json? practice}) async {
    setState(() => saving = true);
    final p = widget.party;
    try {
      await ref.read(teamProvider.notifier).saveParty(p['name'] as String, partySets(p), p['format'] as String);
      if (!mounted) return;
      if (play) return context.go('/battle', extra: practice);
      if (edit) return context.go('/workspace');
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: const Text('새 팀으로 저장했습니다'),
        action: SnackBarAction(label: tr('팀 빌더'), onPressed: () => context.go('/team')),
      ));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('파티를 저장하지 못했습니다')));
      }
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.party;
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final members = (p['members'] as List).cast<Json>();
    final simulation = p['simulation'] as Json?;
    final holdout = p['holdout'] as Json?;
    final metrics = p['metrics'] as Json?;
    final guide = p['guide'] as Json?;
    final plans = (guide?['plans'] as List? ?? const []).cast<Json>();
    final practice = plans.where((plan) => plan['lossSample'] != null).firstOrNull;
    final fixedIds = (p['fixedIds'] as List? ?? const []).toSet();
    final unconfirmed = ((p['operation'] as Json?)?['unconfirmed'] as List? ?? const []).cast<String>();
    final axes = ((p['analysis'] as Json?)?['axes'] as List? ?? const []).cast<Json>();
    final warnings = [
      for (final w in (p['warnings'] as List? ?? const []))
        if (w is String) w else if (w is Json && w['text'] is String) w['text'] as String,
    ];
    final weak = ((p['analysis'] as Json?)?['weakTypes'] as List? ?? const []).cast<Json>();
    final lead = (guide?['lead'] as Json?);

    return Container(
      margin: const EdgeInsets.only(bottom: 18),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: widget.index == 0 ? cs.primary.withOpacity(.55) : cs.outlineVariant.withOpacity(.6)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // ── 제목
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
            decoration: BoxDecoration(
                color: widget.index == 0 ? cs.primary : cs.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(20)),
            child: Text(tr('{}안').replaceFirst('{}', '${widget.index + 1}'),
                style: TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 12.5,
                    color: widget.index == 0 ? cs.onPrimary : cs.onSurface)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(p['name'] as String,
                style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.3)),
          ),
        ]),
        const SizedBox(height: 12),
        // ── 핵심 수치
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (holdout != null)
            _Stat('검증 승점률', fmtPct(100 * (holdout['rate'] as num)),
                note: tr('처음 보는 상대 {}판').replaceFirst('{}', '${holdout['runs']}'), strong: true),
          if (simulation != null)
            _Stat('선정 모의전 승률', _rate(simulation), note: tr('{}판').replaceFirst('{}', '${simulation['runs']}')),
          if (metrics?['leagues'] case final Map leagues)
            if (leagues['챔피언'] case final Map champ)
              _Stat('챔피언 CPU 상대', fmtPct(100 * (champ['rate'] as num)),
                  note: tr('{}판').replaceFirst('{}', '${champ['games']}')),
          if (p['metaScore'] != null) _Stat('메타 상성', '${p['metaScore']}', note: '100점 만점'),
        ]),
        const SizedBox(height: 14),
        // ── 6마리 한눈에
        LayoutBuilder(builder: (context, box) {
          final per = box.maxWidth >= 560 ? 6 : 3;
          final width = (box.maxWidth - 8 * (per - 1)) / per;
          return Wrap(spacing: 8, runSpacing: 8, children: [
            for (final m in members)
              SizedBox(width: width, child: _MonTile(m, fixed: fixedIds.contains(m['id']))),
          ]);
        }),
        const SizedBox(height: 14),
        // ── 왜 이 팀인가
        _Box(
          title: '이 팀을 고른 이유',
          glyph: LabGlyph.spark,
          children: [
            for (final axis in axes.take(3))
              _Bullet(
                  title: tr(axis['label'] as String),
                  text: _firstSentences(axis['play'] as String? ?? '', 2)),
            if (lead != null && (lead['lead'] as List? ?? const []).isNotEmpty)
              _Bullet(
                  title: tr('주로 쓰는 선봉'),
                  text: '${_names(lead['lead'])}${(lead['back'] as List? ?? const []).isEmpty ? '' : ' · ${tr('후발')} ${_names(lead['back'])}'}'),
            if (weak.isNotEmpty)
              _Bullet(
                  title: tr('조심할 타입'),
                  text: weak.map((w) => '${typeKo[w['type']] ?? w['type']} (${tr('약점 {}').replaceFirst('{}', '${w['weak']}')})').join(', ')),
            for (final w in [...unconfirmed.map((u) => '$u · ${tr('반복 실행 미확인')}'), ...warnings].take(4))
              _Bullet(text: tr(w), warn: true),
          ],
        ),
        const SizedBox(height: 14),
        // ── 포켓몬별 이유와 세트
        Text('포켓몬별 선택 이유와 세트', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 6),
        for (final m in members) _MemberReason(m, fixed: fixedIds.contains(m['id'])),
        const SizedBox(height: 6),
        // ── 상세 (접힘)
        if (guide != null)
          LabExpansionTile(
            title: const Text('선출과 운영 가이드'),
            tilePadding: EdgeInsets.zero,
            expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TeamGuide(guide, sets: partySets(p), format: p['format'] as String, onPractice: (plan) {
                if (!saving) _save(play: true, practice: plan);
              })
            ],
          ),
        LabExpansionTile(
          title: const Text('모의전 상세'),
          subtitle: const Text('선정·검증 전적, 포켓몬별 성적, 교체·최적화 기록'),
          tilePadding: EdgeInsets.zero,
          expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (simulation != null) PartySimulationResult(simulation, members: members),
            if (holdout != null) ...[
              const SizedBox(height: 10),
              _HoldoutDetail(holdout),
            ],
            if (p['rankers'] case final Json rankers) RankerMatchups(rankers),
            if ((p['rosterSearch'] as List? ?? const []).isNotEmpty)
              PartyRosterChanges((p['rosterSearch'] as List).cast<Json>()),
            if (p['tuning'] case final Json tuning) _Tuning(tuning),
            if (p['analysis'] != null) ...[
              const SizedBox(height: 8),
              CandidateAnalysis(p),
            ],
          ],
        ),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: saving ? null : () => _save(edit: true),
            icon: const LabIcon(LabGlyph.stack),
            label: const Text('저장하고 팀 수정'),
          ),
          FilledButton.tonalIcon(
            onPressed: saving ? null : _save,
            icon: const LabIcon(LabGlyph.addList),
            label: Text(saving ? '저장 중' : '새 팀으로 저장'),
          ),
          OutlinedButton.icon(
            onPressed: saving ? null : () => _save(play: true),
            icon: const LabIcon(LabGlyph.controller),
            label: const Text('저장하고 배틀'),
          ),
          if (practice != null)
            TextButton.icon(
              onPressed: saving ? null : () => _save(play: true, practice: {...practice, 'sample': practice['lossSample']}),
              icon: const LabIcon(LabGlyph.controller),
              label: Text(tr('{} 상대 패배 매치 연습').replaceFirst('{}', tr('${practice['against']}'))),
            ),
        ]),
      ]),
    );
  }

  static String _names(Object? value) =>
      (value as List? ?? const []).cast<Json>().map((mon) => mon['ko'] ?? mon['name']).join(' + ');

  static String _rate(Json r) {
    final runs = (r['runs'] as num?) ?? 0;
    if (runs == 0) return '-';
    return fmtPct(100 * (((r['win'] as num?) ?? 0) + .5 * ((r['draw'] as num?) ?? 0)) / runs);
  }

  static String _firstSentences(String text, int count) {
    final parts = text.split(RegExp(r'(?<=[.다])\s+'));
    return parts.take(count).join(' ');
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value, {this.note, this.strong = false});
  final String label;
  final String value;
  final String? note;
  final bool strong;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      constraints: const BoxConstraints(minWidth: 108),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: strong ? cs.primary.withOpacity(.13) : cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
        Text(value,
            style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800, color: strong ? cs.primary : null, height: 1.25)),
        if (note != null) Text(note!, style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
      ]),
    );
  }
}

class _MonTile extends StatelessWidget {
  const _MonTile(this.m, {required this.fixed});
  final Json m;
  final bool fixed;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
      decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(12)),
      child: Column(children: [
        Sprite(m['sprite'] as String, size: 48),
        const SizedBox(height: 4),
        Text('${m['ko'] ?? m['name']}',
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
        Text('${m['itemKo'] ?? (m['set'] as Json)['item'] ?? '-'}',
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
        if (fixed || m['joker'] == true)
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Text(fixed ? tr('지정') : tr('숨은 카드'),
                style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: fixed ? cs.primary : cs.tertiary)),
          ),
      ]),
    );
  }
}

class _Box extends StatelessWidget {
  const _Box({required this.title, required this.glyph, required this.children});
  final String title;
  final LabGlyph glyph;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
      decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(14)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          LabIcon(glyph, size: 17, color: cs.primary),
          const SizedBox(width: 7),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
        ]),
        const SizedBox(height: 8),
        ...children,
      ]),
    );
  }
}

class _Bullet extends StatelessWidget {
  const _Bullet({this.title, required this.text, this.warn = false});
  final String? title;
  final String text;
  final bool warn;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = warn ? cs.tertiary : cs.onSurface;
    return Padding(
      padding: const EdgeInsets.only(bottom: 7),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.only(top: 6, right: 9),
          child: Container(
              width: 6, height: 6, decoration: BoxDecoration(color: warn ? cs.tertiary : cs.primary, shape: BoxShape.circle)),
        ),
        Expanded(
          child: Text.rich(TextSpan(children: [
            if (title != null) TextSpan(text: '$title  ', style: TextStyle(fontWeight: FontWeight.w700, color: color)),
            TextSpan(text: text, style: TextStyle(color: warn ? color : cs.onSurfaceVariant)),
          ]), style: const TextStyle(fontSize: 13, height: 1.45)),
        ),
      ]),
    );
  }
}

/// 포켓몬 한 마리: 접힌 상태에서도 한 줄 요약, 펼치면 뽑은 이유와 세트별 이유
class _MemberReason extends StatefulWidget {
  const _MemberReason(this.m, {required this.fixed});
  final Json m;
  final bool fixed;

  @override
  State<_MemberReason> createState() => _MemberReasonState();
}

class _MemberReasonState extends State<_MemberReason> {
  bool open = false;

  @override
  Widget build(BuildContext context) {
    final m = widget.m;
    final cs = Theme.of(context).colorScheme;
    final why = m['why'] as Json?;
    final s = m['set'] as Json;
    final reasons = (why?['reasons'] as List? ?? const []).cast<Json>();
    final parts = (why?['set'] as List? ?? const []).cast<Json>();
    final summary = why?['summary'] as String? ??
        (m['features'] as List? ?? const []).cast<String>().map(tr).join(' · ');
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      decoration: BoxDecoration(
        color: open ? cs.surfaceContainer : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.outlineVariant.withOpacity(.5)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => setState(() => open = !open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 10, 8),
            child: Row(children: [
              Sprite(m['sprite'] as String, size: 40),
              const SizedBox(width: 10),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text.rich(
                    TextSpan(children: [
                      TextSpan(text: '${m['ko'] ?? m['name']}', style: const TextStyle(fontWeight: FontWeight.w800)),
                      TextSpan(
                          text: '   ${m['itemKo'] ?? s['item'] ?? tr('도구 없음')} · ${m['abilityKo'] ?? s['ability'] ?? ''}',
                          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                    ]),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(summary,
                      maxLines: open ? 3 : 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant, height: 1.35)),
                ]),
              ),
              const SizedBox(width: 6),
              AnimatedRotation(
                turns: open ? .5 : 0,
                duration: const Duration(milliseconds: 160),
                child: LabIcon(LabGlyph.down, size: 18, color: cs.onSurfaceVariant),
              ),
            ]),
          ),
        ),
        if (open)
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const Divider(height: 14),
              const _Label('뽑은 이유'),
              for (final r in reasons) _Bullet(text: tr(r['text'] as String)),
              const SizedBox(height: 6),
              const _Label('세트와 이유'),
              if (parts.isEmpty)
                Wrap(spacing: 6, runSpacing: 6, children: [
                  for (final mv in (m['moveInfo'] as List).cast<Json>())
                    MoveChip(mv['name'] as String, ko: mv['ko'] as String?, type: mv['type'] as String?),
                ])
              else
                for (final part in parts) _SetRow(part),
              if (why?['source'] case final String source)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(tr(source), style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
                ),
            ]),
          ),
      ]),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(text,
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.w800, color: Theme.of(context).colorScheme.primary)),
      );
}

class _SetRow extends StatelessWidget {
  const _SetRow(this.part);
  final Json part;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final narrow = MediaQuery.sizeOf(context).width < 520;
    final head = Row(mainAxisSize: MainAxisSize.min, children: [
      if (part['type'] != null) ...[TypeDot(part['type'] as String?), const SizedBox(width: 6)],
      Flexible(
        child: Text('${part['label']}',
            maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
      ),
    ]);
    final kind = Text(tr('${part['part']}'), style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant));
    final reason = Text(tr('${part['text']}'), style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant, height: 1.4));
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: narrow
          ? Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [kind, const SizedBox(width: 8), Flexible(child: head)]),
              const SizedBox(height: 2),
              reason,
            ])
          : Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 74, child: Padding(padding: const EdgeInsets.only(top: 1), child: kind)),
              SizedBox(width: 132, child: head),
              const SizedBox(width: 10),
              Expanded(child: reason),
            ]),
    );
  }
}

class _HoldoutDetail extends StatelessWidget {
  const _HoldoutDetail(this.sample);
  final Json sample;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerHigh, borderRadius: BorderRadius.circular(12)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(tr('처음 보는 상대로 검증 · {} ({}판)')
                .replaceFirst('{}', fmtPct(100 * (sample['rate'] as num)))
                .replaceFirst('{}', '${sample['runs']}'),
            style: theme.textTheme.titleSmall),
        Text(tr('탐색에 쓰지 않은 합성 코어 {}종 · 마스터볼 CPU').replaceFirst('{}', '${sample['coreCount']}'),
            style: theme.textTheme.bodySmall),
        if (sample['ci'] case final List interval)
          Text(
              tr('95% 추정 범위 {}–{}')
                  .replaceFirst('{}', fmtPct(100 * (interval[0] as num)))
                  .replaceFirst('{}', fmtPct(100 * (interval[1] as num))),
              style: theme.textTheme.bodySmall),
        const SizedBox(height: 6),
        for (final match in (sample['strategies'] as List? ?? const []).cast<Json>())
          Text(
              tr('{} · {}승 {}무 {}패')
                  .replaceFirst('{}', tr('${match['label']}'))
                  .replaceFirst('{}', '${match['win']}')
                  .replaceFirst('{}', '${match['draw']}')
                  .replaceFirst('{}', '${match['loss']}'),
              style: theme.textTheme.bodySmall),
      ]),
    );
  }
}

class _Tuning extends StatelessWidget {
  const _Tuning(this.tuning);
  final Json tuning;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final changes = (tuning['changes'] as List? ?? const []).cast<Json>();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('세트 최적화', style: theme.textTheme.titleSmall),
        if (changes.isEmpty)
          Text('사용률 세트보다 확실히 나은 변경이 없어 그대로 두었습니다.', style: theme.textTheme.bodySmall)
        else
          for (final c in changes)
            Text(
                tr('{} · {} · {} (승률 +{}%p)')
                    .replaceFirst('{}', '${c['name']}')
                    .replaceFirst('{}', tr(c['kind'] as String))
                    .replaceFirst('{}', '${c['change']}')
                    .replaceFirst('{}', '${c['gain']}'),
                style: theme.textTheme.bodySmall),
      ]),
    );
  }
}
