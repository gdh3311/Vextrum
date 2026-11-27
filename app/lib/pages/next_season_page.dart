import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../main.dart';
import '../settings.dart' show apiContextProvider;
import '../team_state.dart';
import '../widgets.dart';

/// 다음 시즌 미리보기: 발표된 레귤레이션·밸런스 조정·새 포켓몬이 지금 메타와 내 팀에 미칠 영향.
final nextSeasonProvider = FutureProvider<Json>((ref) async {
  ref.watch(apiContextProvider);
  ref.watch(battleDataVersionProvider);
  ref.watch(nextSeasonAtProvider);
  final fmt = ref.watch(formatProvider);
  final team = ref.watch(teamProvider);
  return (await dio.post('/api/next-season', data: {
    'format': fmt,
    'team': [for (final s in team) s.set],
  }))
      .data as Json;
});

String _when(String iso) {
  final d = DateTime.parse(iso).toLocal();
  String two(int n) => '$n'.padLeft(2, '0');
  return '${d.month}월 ${d.day}일 ${two(d.hour)}:${two(d.minute)}';
}

class NextSeasonPage extends ConsumerWidget {
  const NextSeasonPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref.watch(nextSeasonProvider);
    final cs = Theme.of(context).colorScheme;
    final muted = TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant);
    return PageBody(children: [
      AsyncView<Json>(data, (d) {
        final available = d['available'] == true;
        final at = d['at'] as String?;
        final days = at == null ? null : DateTime.parse(at).difference(DateTime.now()).inDays;
        final changes = ((d['changes'] as List?) ?? const []).cast<Json>();
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          PageHeader('다음 시즌 미리보기',
              glyph: LabGlyph.spark,
              subtitle: available
                  ? '${d['regulation'] ?? ''} · ${_when(at!)} 적용${days != null && days >= 0 ? ' (D-$days)' : ''} · '
                      '공식 공지로 발표된 변경을 지금 메타와 내 팀에 미리 적용해 봅니다. 앱의 계산식과 지금까지의 통계로 낸 추정입니다.'
                  : '아직 발표된 다음 시즌 변경이 없습니다. 공식 공지가 나오면 자동으로 이 화면이 채워집니다.'),
          if (available)
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Wrap(spacing: 10, runSpacing: 8, children: [
                FilledButton.icon(
                  onPressed: () {
                    ref.read(previewRulesSwitchProvider.notifier).state = true;
                    context.go('/team/auto');
                  },
                  icon: const LabIcon(LabGlyph.team, size: 18),
                  label: const Text('다음 시즌 규칙으로 팀 자동 구성'),
                ),
                OutlinedButton.icon(
                  onPressed: () {
                    ref.read(previewRulesSwitchProvider.notifier).state = true;
                    context.go('/damage');
                  },
                  icon: const LabIcon(LabGlyph.shield, size: 18),
                  label: const Text('다음 시즌 규칙으로 계산기'),
                ),
              ]),
            ),
          if (changes.isNotEmpty) _Changes(changes),
          if (available) ...[
            if (d['team'] case final Json team) _TeamImpact(team),
            _Newcomers(((d['newcomers'] as List?) ?? const []).cast<Json>()),
            _Balance(d['balance'] as Json),
            Padding(padding: const EdgeInsets.only(top: 4), child: Text('${d['note'] ?? ''}', style: muted)),
          ],
        ]);
      }, onRetry: () => ref.invalidate(nextSeasonProvider)),
    ]);
  }
}

class _Changes extends StatelessWidget {
  const _Changes(this.changes);
  final List<Json> changes;
  static const _kinds = {'regulation': '레귤레이션', 'season': '시즌', 'balance': '밸런스 조정'};

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Section('바뀌는 것',
        child: Column(children: [
          for (final c in changes)
            LabExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: Text('${tr(_kinds[c['kind']] ?? c['kind'] as String)} · ${c['title'] ?? ''}'),
              subtitle: Text('${_when(c['at'] as String)}'
                  '${c['estimated'] == true ? tr(' (점검 공지가 없어 시즌 시작 시각으로 추정)') : ''}'),
              expandedAlignment: Alignment.centerLeft,
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final line in (c['details'] as List? ?? const []))
                  Padding(padding: const EdgeInsets.only(bottom: 4), child: Text('• $line')),
                TextButton.icon(
                  onPressed: () => Clipboard.setData(ClipboardData(text: c['url'] as String)),
                  icon: const LabIcon(LabGlyph.copy, size: 16),
                  label: const Text('공식 공지 링크 복사'),
                ),
              ],
            ),
          if (changes.isEmpty) Text('발표된 변경이 없습니다', style: TextStyle(color: cs.onSurfaceVariant)),
        ]));
  }
}

class _Newcomers extends StatelessWidget {
  const _Newcomers(this.rows);
  final List<Json> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    final cs = Theme.of(context).colorScheme;
    return Section('새로 참가하는 포켓몬',
        subtitle: '지금 메타 상위 30마리와 1:1 상성 점수 (50이 호각). 랭킹 원본에 오르기 전에는 공개 도감 기준 임시 세트로 계산합니다',
        child: Column(children: [
          for (final r in rows)
            Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                  color: cs.surfaceContainerHighest.withOpacity(.4), borderRadius: BorderRadius.circular(12)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Sprite(r['sprite'] as String, size: 44),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${r['ko'] ?? r['name']}${r['mega'] != null ? ' · ${tr('메가진화')}' : ''}',
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                      Text(
                          '${(r['types'] as List).join('/')} · ${tr('스피드')} ${r['speed']} · '
                          '${tr('특성')} ${r['ability']}',
                          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                    ]),
                  ),
                  Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Text('${r['average']}',
                        style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            color: (r['average'] as num) >= 55
                                ? const Color(0xFF34C77B)
                                : (r['average'] as num) < 45
                                    ? const Color(0xFFF0616D)
                                    : cs.onSurface)),
                    Text('평균 상성', style: TextStyle(fontSize: 11, color: cs.onSurfaceVariant)),
                  ]),
                ]),
                const SizedBox(height: 6),
                _MonRow('잘 잡는 상대', (r['beats'] as List).cast<Json>()),
                _MonRow('위협', (r['threats'] as List).cast<Json>()),
              ]),
            ),
        ]));
  }
}

class _MonRow extends StatelessWidget {
  const _MonRow(this.label, this.mons, {this.caption});
  final String label;
  final List<Json> mons;
  final String Function(Json)? caption;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 84, child: Text(label, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant))),
        Expanded(
          child: Wrap(spacing: 6, runSpacing: 4, children: [
            for (final m in mons)
              MonPill(m,
                  caption: caption?.call(m) ?? (m['score'] != null ? '${m['score']}' : null),
                  onTap: m['id'] is String && m['provisional'] != true
                      ? () => context.push(pokemonPath(m['id'] as String))
                      : null),
          ]),
        ),
      ]),
    );
  }
}

class _Balance extends StatelessWidget {
  const _Balance(this.b);
  final Json b;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final moves = (b['moves'] as List).cast<Json>();
    final learn = (b['learn'] as List).cast<Json>();
    final abilities = (b['abilities'] as List).cast<Json>();
    if (moves.isEmpty && learn.isEmpty && abilities.isEmpty) return const SizedBox.shrink();
    return Section('밸런스 조정이 닿는 곳',
        subtitle: '지금 메타 상위권에서 바뀐 기술을 쓰는 포켓몬(채용률), 새로 배우는 기술, 바뀐 특성을 가진 포켓몬',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final m in moves) ...[
            Text(
                '${m['ko']}: ${(m['changes'] as List).cast<Json>().map((c) => '${tr(c['label'] as String)} ${c['before']}→${c['after']}').join(', ')}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            if ((m['users'] as List).isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2, bottom: 8),
                child: Text('메타 상위권에서 많이 쓰는 포켓몬 없음', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
              )
            else
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _MonRow('쓰는 포켓몬', (m['users'] as List).cast<Json>(),
                    caption: (u) => '#${u['rank']} · ${fmtPct(u['pct'] as num)}'),
              ),
          ],
          if (learn.isNotEmpty) ...[
            const Text('새로 배우는 기술', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Wrap(spacing: 6, runSpacing: 4, children: [
              for (final l in learn)
                MonPill(l,
                    caption: '${l['rank'] != null ? '#${l['rank']} · ' : ''}'
                        '${(l['moves'] as List).cast<Json>().map((x) => x['ko']).join(', ')}',
                    onTap: () => context.push(pokemonPath(l['id'] as String))),
            ]),
            const SizedBox(height: 10),
          ],
          for (final a in abilities)
            _MonRow(tr(a['text'] as String), (a['holders'] as List).cast<Json>(),
                caption: (h) => '#${h['rank']}'),
        ]));
  }
}

class _TeamImpact extends StatelessWidget {
  const _TeamImpact(this.t);
  final Json t;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final members = (t['members'] as List).cast<Json>();
    final newcomers = (t['newcomers'] as List).cast<Json>();
    return Section('내 팀에 미치는 영향',
        subtitle: '팀 빌더의 지금 팀 기준',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (final m in members)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Sprite(m['sprite'] as String, size: 32),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${m['ko'] ?? m['name']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text((m['notes'] as List).isEmpty ? tr('바뀌는 것 없음') : (m['notes'] as List).join(' · '),
                        style: TextStyle(
                            fontSize: 12.5,
                            color: (m['notes'] as List).isEmpty ? cs.onSurfaceVariant : cs.onSurface)),
                  ]),
                ),
              ]),
            ),
          if (newcomers.isNotEmpty) ...[
            const SizedBox(height: 6),
            const Text('새 포켓몬을 상대로', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            for (final n in newcomers)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Row(children: [
                  Sprite(n['sprite'] as String, size: 30),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                        n['covered'] == true
                            ? tr('{} → {}(으)로 대응 가능 (상성 {})')
                                .replaceFirst('{}', '${n['ko'] ?? n['name']}')
                                .replaceFirst('{}', '${(n['best'] as Json)['ko'] ?? (n['best'] as Json)['name']}')
                                .replaceFirst('{}', '${(n['best'] as Json)['score']}')
                            : tr('{} → 팀에 확실한 대응 포켓몬이 없음 (가장 나은 상성 {})')
                                .replaceFirst('{}', '${n['ko'] ?? n['name']}')
                                .replaceFirst('{}', '${(n['best'] as Json)['score']}'),
                        style: TextStyle(
                            fontSize: 13, color: n['covered'] == true ? null : const Color(0xFFF0616D))),
                  ),
                ]),
              ),
          ],
        ]));
  }
}
