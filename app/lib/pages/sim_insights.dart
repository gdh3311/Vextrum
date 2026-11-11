/// 시뮬레이션 상세 통계(포켓몬별 기여, 위협적인 상대, 선봉 조합 승률, 턴 분포)와
/// 자동 구성 후보의 팀 분석·후보 비교표.
import 'package:flutter/material.dart' hide Text, Tooltip;

import '../api.dart';
import '../i18n.dart';
import '../theme.dart';
import '../widgets.dart';

const cpuLabels = {'poke': '몬스터볼', 'great': '슈퍼볼', 'ultra': '하이퍼볼', 'master': '마스터볼', 'champion': '챔피언'};

String _name(Json m) => (m['ko'] ?? m['name']) as String;

String ciText(Json row) {
  final ci = row['ci'] as List?;
  if (ci == null) return '';
  return tr('95% 범위 {}~{}%').replaceFirst('{}', '${ci[0]}').replaceFirst('{}', '${ci[1]}');
}

double winRate(Json row) => 100 * (row['win'] as int) / ((row['runs'] as int?) ?? 1).clamp(1, 1 << 30);

/// 승률 막대 + 신뢰 구간
class WinRateBar extends StatelessWidget {
  const WinRateBar({super.key, required this.rate, this.ci, this.height = 8});
  final double rate;
  final List? ci;
  final double height;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final color = rate >= 60 ? good : rate >= 45 ? even : bad;
    return LayoutBuilder(builder: (context, c) {
      final w = c.maxWidth;
      return SizedBox(
        height: height + 6,
        child: Stack(alignment: Alignment.centerLeft, children: [
          Container(height: height, decoration: BoxDecoration(color: cs.surfaceContainerHighest, borderRadius: BorderRadius.circular(4))),
          if (ci != null)
            Positioned(
              left: w * (ci![0] as num) / 100,
              width: (w * ((ci![1] as num) - (ci![0] as num)) / 100).clamp(2.0, w),
              child: Container(height: height, decoration: BoxDecoration(color: color.withOpacity(.25), borderRadius: BorderRadius.circular(4))),
            ),
          Container(
            width: w * rate / 100,
            height: height,
            decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(4)),
          ),
          Positioned(left: w * .5 - 1, child: Container(width: 2, height: height + 6, color: cs.onSurfaceVariant.withOpacity(.5))),
        ]),
      );
    });
  }
}

class SimulationInsights extends StatelessWidget {
  const SimulationInsights(this.result, {super.key});
  final Json result;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final members = (result['memberStats'] as List? ?? const []).cast<Json>();
    final threats = (result['threats'] as List? ?? const []).cast<Json>();
    final leads = (result['leadStats'] as List? ?? const []).cast<Json>();
    final hist = (result['turnHistogram'] as List? ?? const []).cast<Json>();
    final runs = result['runs'] as int;
    final rate = winRate(result);
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant);
    final head = TextStyle(fontSize: 12, color: cs.onSurfaceVariant, fontWeight: FontWeight.w600);
    const numStyle = TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()]);
    final byId = {for (final m in members) m['id']: m};

    Widget block(String title, Widget child, {String? sub}) => Padding(
          padding: const EdgeInsets.only(top: 18),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
            if (sub != null) Text(sub, style: muted),
            const SizedBox(height: 8),
            child,
          ]),
        );

    Widget cell(String text, double width, {TextStyle? style, TextAlign align = TextAlign.right}) =>
        SizedBox(width: width, child: Text(text, textAlign: align, style: style ?? numStyle));

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // 요약
      Wrap(spacing: 22, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.end, children: [
        Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Text(fmtPct(rate), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, height: 1.1)),
          Text(ciText(result), style: muted),
        ]),
        _Stat('{}판'.replaceFirst('{}', '$runs'), '${result['win']}승 ${result['loss']}패 ${result['draw']}무'),
        if (result['avgTurns'] != null) _Stat('평균 {}턴'.replaceFirst('{}', '${result['avgTurns']}'), '경기 길이'),
        if (result['difficulty'] != null) _Stat(cpuLabels[result['difficulty']] ?? '${result['difficulty']}', '상대 CPU'),
      ]),
      const SizedBox(height: 8),
      SizedBox(width: 360, child: WinRateBar(rate: rate, ci: result['ci'] as List?)),
      if (members.isNotEmpty)
        block(
          '포켓몬별 활약',
          sub: '선출된 판 기준 · 승률은 그 포켓몬을 낸 판의 승률',
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const SizedBox(width: 178),
                cell('선출', 58, style: head),
                cell('선봉', 52, style: head),
                cell('생존', 58, style: head),
                cell('승률', 58, style: head),
                cell('준 피해', 66, style: head),
                cell('받은 피해', 70, style: head),
                cell('KO/판', 58, style: head),
                cell('남은 HP', 64, style: head),
              ]),
              const SizedBox(height: 4),
              for (final m in members)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(children: [
                    SizedBox(
                      width: 178,
                      child: Row(children: [
                        Sprite(m['sprite'] as String, size: 30),
                        const SizedBox(width: 6),
                        Expanded(
                            child: Text(_name(m),
                                maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600))),
                      ]),
                    ),
                    cell(fmtPct(m['pickRate'] as num), 58),
                    cell('${m['leads']}', 52),
                    cell(fmtPct(m['surviveRate'] as num), 58),
                    cell(fmtPct(m['winRate'] as num), 58,
                        style: numStyle.copyWith(
                            color: (m['winRate'] as num) >= 60 ? good : (m['winRate'] as num) < 45 ? bad : null,
                            fontWeight: FontWeight.w700)),
                    cell('${m['avgDealt']}', 66),
                    cell('${m['avgTaken']}', 70),
                    cell('${m['koPerGame']}', 58),
                    cell('${m['hpLeft']}%', 64),
                  ]),
                ),
            ]),
          ),
        ),
      if (leads.isNotEmpty)
        block(
          '선봉 조합별 승률',
          sub: '자주 나간 선봉 순 · 옅은 막대는 95% 범위',
          Column(children: [
            for (final l in leads)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: LayoutBuilder(builder: (context, c) {
                  final narrow = c.maxWidth < 520;
                  return Row(children: [
                    for (final id in (l['ids'] as List))
                      if (byId[id] case final m?) Tooltip(message: _name(m), child: Sprite(m['sprite'] as String, size: 30)),
                    const SizedBox(width: 8),
                    if (!narrow)
                      SizedBox(
                        width: 170,
                        child: Text([for (final id in (l['ids'] as List)) if (byId[id] case final m?) _name(m)].join(' + '),
                            maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13)),
                      ),
                    Expanded(child: WinRateBar(rate: (l['winRate'] as num).toDouble(), ci: l['ci'] as List?)),
                    const SizedBox(width: 10),
                    Text('${fmtPct(l['winRate'] as num)} · {}판'.replaceFirst('{}', '${l['runs']}'), style: numStyle),
                  ]);
                }),
              ),
          ]),
        ),
      if (threats.isNotEmpty)
        block(
          '가장 위협적이었던 상대',
          sub: '상대로 나왔을 때 판당 쓰러뜨린 내 포켓몬 수와 준 피해',
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final t in threats)
              MonPill(t,
                  caption: tr('KO {}/판 · 피해 {}')
                      .replaceFirst('{}', '${t['koPerGame']}')
                      .replaceFirst('{}', '${t['avgDealt']}')),
          ]),
        ),
      if (hist.isNotEmpty)
        block(
          '경기 길이 분포',
          _Histogram(hist),
        ),
    ]);
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.value, this.label);
  final String value;
  final String label;
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
        Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        Text(label, style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
      ]);
}

class _Histogram extends StatelessWidget {
  const _Histogram(this.rows);
  final List<Json> rows;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final top = rows.map((r) => r['games'] as int).fold(1, (a, b) => a > b ? a : b);
    return SizedBox(
      height: 92,
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
              Text('${r['games']}', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
              Container(
                width: 22,
                height: 56 * (r['games'] as int) / top + 2,
                decoration: BoxDecoration(color: cs.primary.withOpacity(.7), borderRadius: BorderRadius.circular(4)),
              ),
              const SizedBox(height: 3),
              Text((r['turns'] as int) >= 12 ? '12+' : '${r['turns']}', style: const TextStyle(fontSize: 11.5)),
            ]),
          ),
        Padding(
          padding: const EdgeInsets.only(bottom: 2, left: 4),
          child: Text('턴', style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
        ),
      ]),
    );
  }
}

/// 자동 구성 후보의 팀 분석 요약
class CandidateAnalysis extends StatelessWidget {
  const CandidateAnalysis(this.party, {super.key});
  final Json party;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final a = party['analysis'] as Json;
    final members = (party['members'] as List).cast<Json>();
    final split = a['damageSplit'] as Json;
    final m = a['matchups'] as Json;
    final lead = a['lead'] as Json?;
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant);
    Widget label(String t) => Padding(
        padding: const EdgeInsets.only(top: 14, bottom: 6),
        child: Text(t, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      label('구성원과 역할'),
      for (final mon in members)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(children: [
            Sprite(mon['sprite'] as String, size: 32),
            const SizedBox(width: 8),
            SizedBox(
              width: 150,
              child: Text(_name(mon), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
            ),
            SizedBox(width: 74, child: Text(tr('스피드 {}').replaceFirst('{}', '${mon['speed'] ?? '-'}'), style: muted)),
            if (mon['fixed'] == true)
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: Text('고정', style: TextStyle(fontSize: 12, color: cs.primary, fontWeight: FontWeight.w700)),
              ),
            Expanded(
              child: Text(((mon['features'] as List?) ?? const []).map((f) => tr('$f')).join(' · '),
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: muted),
            ),
          ]),
        ),
      label('메타 상성 · 약점'),
      Wrap(spacing: 16, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Text('유리 {} · 호각 {} · 불리 {}'
            .replaceFirst('{}', '${m['GOOD']}')
            .replaceFirst('{}', '${m['EVEN']}')
            .replaceFirst('{}', '${m['BAD']}')),
        Text('물리 {}% · 특수 {}%'.replaceFirst('{}', '${split['physical']}').replaceFirst('{}', '${split['special']}'), style: muted),
        for (final w in (a['weakTypes'] as List).cast<Json>())
          Row(mainAxisSize: MainAxisSize.min, children: [
            TypeChip(w['type'] as String, dense: true),
            const SizedBox(width: 4),
            Text('약점 {} · 반감 {}'.replaceFirst('{}', '${w['weak']}').replaceFirst('{}', '${w['resist']}'), style: muted),
          ]),
      ]),
      label('역할 구성'),
      Wrap(spacing: 14, runSpacing: 6, children: [
        for (final r in (a['roles'] as List).cast<Json>())
          Row(mainAxisSize: MainAxisSize.min, children: [
            Text(r['label'] as String, style: const TextStyle(fontSize: 13)),
            const SizedBox(width: 4),
            Stars(r['stars'] as int),
          ]),
      ]),
      if ((a['axes'] as List).isNotEmpty) ...[
        label('운영법'),
        for (final ax in (a['axes'] as List).cast<Json>())
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text.rich(TextSpan(children: [
              TextSpan(text: '${ax['label']}  ', style: TextStyle(fontWeight: FontWeight.w700, color: cs.primary)),
              TextSpan(text: ax['play'] as String),
            ]), style: const TextStyle(fontSize: 13.5, height: 1.5)),
          ),
      ],
      if (lead != null) ...[
        label('기본 선출'),
        Wrap(spacing: 18, runSpacing: 8, children: [
          for (final (title, key) in const [('선봉', 'lead'), ('후발', 'back')])
            Row(mainAxisSize: MainAxisSize.min, children: [
              Text(title, style: muted),
              const SizedBox(width: 6),
              for (final mon in (lead[key] as List).cast<Json>()) Tooltip(message: _name(mon), child: Sprite(mon['sprite'] as String, size: 34)),
            ]),
        ]),
      ],
    ]);
  }
}

/// 자동 구성 후보 비교표
class CandidateComparison extends StatelessWidget {
  const CandidateComparison(this.candidates, {super.key});
  final List<Json> candidates;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final head = TextStyle(fontSize: 12, color: cs.onSurfaceVariant, fontWeight: FontWeight.w600);
    const numStyle = TextStyle(fontSize: 13, fontFeatures: [FontFeature.tabularFigures()]);
    Widget cell(Widget child, double w) => SizedBox(width: w, child: child);
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          cell(Text('순위', style: head), 40),
          cell(Text('팀', style: head), 200),
          cell(Text('검증 승률', style: head), 190),
          cell(Text('가장 어려운 전략', style: head), 170),
          cell(Text('메타 대응 점수', style: head), 100),
          cell(Text('평균 턴', style: head), 64),
          cell(Text('약점 타입', style: head), 120),
        ]),
        const Divider(),
        for (final (i, c) in candidates.indexed)
          Builder(builder: (context) {
            final sim = c['simulation'] as Json;
            final worst = (sim['strategies'] as List).cast<Json>().first;
            final rate = winRate(sim);
            final weak = ((c['analysis'] as Json?)?['weakTypes'] as List? ?? const []).cast<Json>();
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(children: [
                cell(Text('${i + 1}', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: i == 0 ? cs.primary : null)), 40),
                cell(
                  Row(children: [
                    for (final m in (c['members'] as List).cast<Json>().take(6)) Sprite(m['sprite'] as String, size: 26),
                  ]),
                  200,
                ),
                cell(
                  Row(children: [
                    SizedBox(width: 90, child: WinRateBar(rate: rate, ci: sim['ci'] as List?)),
                    const SizedBox(width: 8),
                    Text(fmtPct(rate), style: numStyle.copyWith(fontWeight: FontWeight.w700)),
                  ]),
                  190,
                ),
                cell(Text('${worst['label']} ${fmtPct(winRate(worst))}', maxLines: 1, overflow: TextOverflow.ellipsis, style: numStyle), 170),
                cell(Text('${c['metaScore'] ?? '-'}', style: numStyle), 100),
                cell(Text('${sim['avgTurns'] ?? '-'}', style: numStyle), 64),
                cell(Wrap(spacing: 3, children: [for (final w in weak.take(3)) TypeDot(w['type'] as String)]), 120),
              ]),
            );
          }),
      ]),
    );
  }
}
