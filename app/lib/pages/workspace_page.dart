import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../lab_icons.dart';
import '../main.dart' show PageHeader;
import '../settings.dart' show apiContextProvider;
import '../team_state.dart';
import '../widgets.dart';
import '../workspace_state.dart';
import 'enemy_page.dart' show enemyProvider;
import 'match_journal.dart';
import 'team_page.dart' show SetEditor;
import 'team_switcher.dart' show TeamPickerButton;

/// 팀 워크스페이스: 왼쪽 팀 편집 · 가운데 즉시 분석 · 오른쪽 교체 추천/상대 대응/실험실/실전 기록.
/// 빠른 분석은 정적 계산(승률 아님), 승률은 오른쪽의 모의전 작업에서만 나온다.
class WorkspacePage extends ConsumerStatefulWidget {
  const WorkspacePage({super.key, this.initialTab = 0});
  final int initialTab;
  @override
  ConsumerState<WorkspacePage> createState() => _WorkspacePageState();
}

class _WorkspacePageState extends ConsumerState<WorkspacePage> {
  int slot = 0;
  late int tab = widget.initialTab;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final team = ref.watch(teamProvider);
    if (slot >= team.length && team.isNotEmpty) slot = team.length - 1;
    final left = _TeamColumn(selected: slot, onSelect: (i) => setState(() => slot = i));
    const center = _AnalysisColumn();
    final right = _ToolColumn(slot: slot, tab: tab, onTab: (t) => setState(() => tab = t));
    final header = PageHeader('팀 워크스페이스',
        glyph: LabGlyph.team,
        subtitle: '팀을 고치면 가운데 분석이 바로 바뀝니다. 오른쪽에서 교체 후보·상대 대응·모의전 실험을 같은 팀으로 이어서 할 수 있습니다.');
    if (width >= 1200) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(24, 20, 24, 0),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          header,
          Expanded(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 320, child: SingleChildScrollView(child: left)),
              const SizedBox(width: 16),
              Expanded(child: SingleChildScrollView(child: center)),
              const SizedBox(width: 16),
              SizedBox(width: 440, child: SingleChildScrollView(child: right)),
            ]),
          ),
        ]),
      );
    }
    return ListView(padding: const EdgeInsets.all(16), children: [header, left, right, center]);
  }
}

// ---------------------------------------------------------------- 왼쪽: 팀 편집
class _TeamColumn extends ConsumerWidget {
  final int selected;
  final ValueChanged<int> onSelect;
  const _TeamColumn({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final team = ref.watch(teamProvider);
    final history = ref.watch(historyProvider);
    final notifier = ref.read(teamProvider.notifier);
    final name = notifier.activeName;
    final locks = ref.watch(lockProvider.notifier).of(name, team.length);
    ref.watch(lockProvider);
    final cs = Theme.of(context).colorScheme;

    Future<void> add() async {
      final list = await ref.read(pokemonListProvider.future);
      if (!context.mounted) return;
      final picked = await showPokemonPicker(context, list, ref.read(formatProvider));
      if (picked == null) return;
      ref.read(historyProvider.notifier).record();
      await notifier.add(picked['id'] as String);
    }

    return Section('현재 팀',
        subtitle: '편집은 되돌릴 수 있습니다. 잠근 포켓몬·항목은 추천을 적용해도 바뀌지 않습니다.',
        trailing: const TeamPickerButton(),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            IconButton(
                tooltip: '되돌리기',
                onPressed: history.undo.isEmpty ? null : () => ref.read(historyProvider.notifier).undo(),
                icon: const LabIcon(LabGlyph.back, size: 18)),
            IconButton(
                tooltip: '다시 하기',
                onPressed: history.redo.isEmpty ? null : () => ref.read(historyProvider.notifier).redo(),
                icon: const LabIcon(LabGlyph.forward, size: 18)),
            IconButton(
                tooltip: '팀 복제',
                onPressed: () => notifier.duplicate(ref.read(activeTeamIndexProvider)),
                icon: const LabIcon(LabGlyph.copy, size: 18)),
            const Spacer(),
            Text('버전 ${ref.watch(teamRevisionProvider) % 100000}',
                style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
          ]),
          for (var i = 0; i < team.length; i++)
            _SlotTile(
                index: i,
                slot: team[i],
                locks: locks[i],
                selected: i == selected,
                onSelect: () => onSelect(i),
                teamName: name,
                count: team.length),
          if (team.length < 6)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: OutlinedButton.icon(
                  onPressed: add, icon: const LabIcon(LabGlyph.plus, size: 16), label: const Text('포켓몬 추가')),
            ),
        ]));
  }
}

class _SlotTile extends ConsumerWidget {
  final int index;
  final TeamSlot slot;
  final Map<String, bool> locks;
  final bool selected;
  final VoidCallback onSelect;
  final String teamName;
  final int count;
  const _SlotTile(
      {required this.index,
      required this.slot,
      required this.locks,
      required this.selected,
      required this.onSelect,
      required this.teamName,
      required this.count});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final set = slot.set;
    final lockedMon = locks['pokemon'] ?? false;
    final anyLock = locks.values.any((v) => v);

    void edit() {
      ref.read(historyProvider.notifier).record();
      showDialog(
          context: context,
          builder: (_) => SetEditor(
              slot: slot,
              onChanged: (v) {
                final fixed = applyLocks(set, v, locks);
                if (fixed.toString() != v.toString()) {
                  ScaffoldMessenger.of(context)
                      .showSnackBar(const SnackBar(content: Text('잠긴 항목은 바뀌지 않습니다. 잠금을 풀고 수정하세요.')));
                }
                ref.read(teamProvider.notifier).update(index, fixed);
              }));
    }

    return Card(
      color: selected ? cs.primaryContainer.withOpacity(.35) : null,
      margin: const EdgeInsets.only(top: 6),
      child: InkWell(
        onTap: onSelect,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Row(children: [
            Sprite(slot.sprite, size: 40),
            const SizedBox(width: 8),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${slot.detail['ko'] ?? slot.detail['name']}',
                    style: const TextStyle(fontWeight: FontWeight.w700), overflow: TextOverflow.ellipsis),
                Text('${set['item'] ?? '도구 없음'}',
                    style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant), overflow: TextOverflow.ellipsis),
              ]),
            ),
            IconButton(
                tooltip: lockedMon ? '포켓몬 잠금 해제' : '포켓몬 잠금',
                onPressed: () => ref.read(lockProvider.notifier).toggle(teamName, index, 'pokemon', count),
                icon: LabIcon(lockedMon ? LabGlyph.lock : LabGlyph.unlock,
                    size: 16, color: lockedMon ? cs.primary : null)),
            PopupMenuButton<String>(
              tooltip: '항목 잠금',
              icon: LabIcon(LabGlyph.dots, size: 16, color: anyLock ? cs.primary : null),
              itemBuilder: (_) => [
                for (final f in lockFields.skip(1))
                  CheckedPopupMenuItem(value: f, checked: locks[f] ?? false, child: Text('${lockLabels[f]} 잠금')),
              ],
              onSelected: (f) => ref.read(lockProvider.notifier).toggle(teamName, index, f, count),
            ),
            IconButton(tooltip: '세트 편집', onPressed: edit, icon: const LabIcon(LabGlyph.pencil, size: 16)),
            IconButton(
                tooltip: '빼기',
                onPressed: lockedMon
                    ? null
                    : () {
                        ref.read(historyProvider.notifier).record();
                        ref.read(lockProvider.notifier).removeAt(teamName, index, count);
                        ref.read(teamProvider.notifier).removeAt(index);
                      },
                icon: const LabIcon(LabGlyph.trash, size: 16)),
          ]),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------- 가운데: 빠른 분석
class _AnalysisColumn extends ConsumerStatefulWidget {
  const _AnalysisColumn();
  @override
  ConsumerState<_AnalysisColumn> createState() => _AnalysisColumnState();
}

class _AnalysisColumnState extends ConsumerState<_AnalysisColumn> {
  Map<String, dynamic> _prevHashes = const {};
  Map<String, dynamic> _hashes = const {};

  @override
  Widget build(BuildContext context) {
    ref.listen<AsyncValue<Json?>>(fastAnalysisProvider, (_, next) {
      final h = next.valueOrNull?['hashes'] as Map<String, dynamic>?;
      if (h != null && h.toString() != _hashes.toString()) {
        setState(() {
          _prevHashes = _hashes;
          _hashes = h;
        });
      }
    });
    final async = ref.watch(fastAnalysisProvider);
    final cs = Theme.of(context).colorScheme;
    final data = async.valueOrNull;
    if (ref.watch(teamProvider).isEmpty) {
      return const Section('팀 분석', child: Text('왼쪽에서 포켓몬을 추가하면 분석이 시작됩니다.'));
    }
    if (data == null) {
      return Section('팀 분석',
          child: async.hasError
              ? Text('분석을 불러오지 못했습니다: ${apiError(async.error!)}')
              : const LinearProgressIndicator());
    }
    final s = data['sections'] as Json;
    bool changed(String k) => _prevHashes.isNotEmpty && _prevHashes[k] != _hashes[k];
    Widget badge(String k) => changed(k)
        ? Container(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
            decoration: BoxDecoration(color: cs.tertiaryContainer, borderRadius: BorderRadius.circular(8)),
            child: Text('방금 바뀜', style: TextStyle(fontSize: 11, color: cs.onTertiaryContainer)))
        : const SizedBox.shrink();

    final legality = (s['legality'] as List).cast<Json>();
    final strat = s['strategy'] as Json;
    final speed = s['speed'] as Json;
    final types = s['types'] as Json;
    final meta = s['meta'] as Json;
    final lead = (s['lead'] as Json?)?['lead'] as Json?;
    final worst = [...(meta['matchups'] as List).cast<Json>()]
      ..sort((a, b) => (a['score'] as num).compareTo(b['score'] as num));

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
            '정적 분석 · ${data['elapsedMs']}ms · 승률이 아닌 타입·스피드·기술 계산입니다${async.isLoading ? ' · 갱신 중' : ''}',
            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
      ),
      if (legality.isNotEmpty)
        Section('규칙 점검',
            trailing: badge('legality'),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              for (final i in legality)
                Text('${i['severity'] == 'high' ? '⛔ ' : 'ⓘ '}${i['slot'] != null ? '${(i['slot'] as int) + 1}번 · ' : ''}${i['text']}',
                    style: TextStyle(color: i['severity'] == 'high' ? cs.error : cs.onSurfaceVariant, fontSize: 13)),
            ])),
      Section('전략 연결성',
          subtitle: '태그는 기술·특성으로 판정한 것입니다. 실제로 실행되는지는 실험실에서 확인하세요.',
          trailing: badge('strategy'),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (strat['primary'] != null) Text('주 승리 조건 · ${strat['primary']}'),
            if (strat['secondary'] != null) Text('보조 · ${strat['secondary']}'),
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 4, children: [
              for (final t in (strat['tags'] as List).cast<Json>())
                Chip(label: Text('${t['label']}'), visualDensity: VisualDensity.compact),
            ]),
            for (final i in (strat['issues'] as List).cast<Json>())
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('${i['severity'] == 'mid' ? '⚠ ' : '· '}${i['text']} — ${i['detail']}',
                    style: TextStyle(fontSize: 12.5, color: i['severity'] == 'mid' ? cs.error : null)),
              ),
          ])),
      Section('속도',
          trailing: badge('speed'),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final r in (speed['order'] as List).cast<Json>())
              Text('${r['name']} · ${r['speed']} (순풍 ${r['tailwind']})', style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 6),
            Text('속도 조작 · ${(speed['control'] as List).isEmpty ? '없음' : (speed['control'] as List).map((c) => '${c['name']} ${c['label']}').join(', ')}',
                style: const TextStyle(fontSize: 12.5)),
            Text('선제기 · ${(speed['priority'] as List).isEmpty ? '없음' : (speed['priority'] as List).map((c) => '${c['name']} ${c['label']}').join(', ')}',
                style: const TextStyle(fontSize: 12.5)),
          ])),
      Section('타입 약점 · 화력 균형',
          trailing: badge('types'),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if ((types['warnings'] as List).isEmpty) const Text('겹친 약점이 없습니다.'),
            for (final w in (types['warnings'] as List).cast<Json>()) Text('${w['text']} · ${w['detail']}', style: const TextStyle(fontSize: 13)),
            if (s['balance'] case final Json b) Text('물리 ${b['physical']}% · 특수 ${b['special']}%'),
          ])),
      Section('역할',
          trailing: badge('roles'),
          child: Wrap(spacing: 8, runSpacing: 6, children: [
            for (final r in (s['roles'] as List).cast<Json>())
              Chip(
                  label: Text('${r['label']} ${'★' * (r['stars'] as int)}${'☆' * (5 - (r['stars'] as int))}'),
                  visualDensity: VisualDensity.compact),
          ])),
      Section('대응이 약한 메타 포켓몬',
          subtitle: '랭커 순위 상위 20종의 대표 세트와의 정적 상성. 낮을수록 대응이 약합니다.',
          trailing: badge('meta'),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            for (final m in worst.take(5))
              Row(children: [
                Sprite(m['sprite'] as String, size: 28),
                const SizedBox(width: 6),
                Expanded(child: Text('${m['ko'] ?? m['name']}')),
                Text('${(m['score'] as num).round()}점 · ${m['label']}', style: const TextStyle(fontSize: 12.5)),
              ]),
          ])),
      if (lead != null)
        Section('선봉 추천 (정적)',
            trailing: badge('lead'),
            child: Text(
                '선봉 ${(lead['lead'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')} · 후발 ${(lead['back'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')}')),
      if ((s['mega'] as List).isNotEmpty)
        Section('메가진화 선택지',
            subtitle: '배틀당 1번. 모의전에서는 턴 시작에 필드의 후보 중 하나가 진화합니다.',
            trailing: badge('mega'),
            child: Text((s['mega'] as List).map((m) => '${m['name']} → ${m['mega']}').join(' · '))),
    ]);
  }
}

// ---------------------------------------------------------------- 오른쪽: 도구
class _ToolColumn extends StatelessWidget {
  final int slot;
  final int tab;
  final ValueChanged<int> onTab;
  const _ToolColumn({required this.slot, required this.tab, required this.onTab});
  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SegmentedButton<int>(
        segments: const [
          ButtonSegment(value: 0, label: Text('교체 추천')),
          ButtonSegment(value: 1, label: Text('상대 대응')),
          ButtonSegment(value: 2, label: Text('실험실')),
          ButtonSegment(value: 3, label: Text('실전 기록')),
        ],
        selected: {tab},
        onSelectionChanged: (s) => onTab(s.first),
        showSelectedIcon: false,
      ),
      const SizedBox(height: 12),
      [_ReplacePanel(slot: slot), const _MatchupPanel(), const _LabPanel(), const _FeedbackPanel()][tab],
    ]);
  }
}

/// 결과가 지금 팀 버전의 것이 아니면 표시
Widget staleBanner(BuildContext context, int? resultRev, int currentRev) {
  if (resultRev == null || resultRev == currentRev) return const SizedBox.shrink();
  final cs = Theme.of(context).colorScheme;
  return Container(
    width: double.infinity,
    margin: const EdgeInsets.only(bottom: 8),
    padding: const EdgeInsets.all(8),
    decoration: BoxDecoration(color: cs.errorContainer, borderRadius: BorderRadius.circular(8)),
    child: Text('이 결과는 이전 버전 팀의 것입니다. 지금 팀으로 다시 실행하세요.',
        style: TextStyle(color: cs.onErrorContainer, fontSize: 12.5)),
  );
}

Widget verdictChip(BuildContext context, Json? v) {
  if (v == null) return const SizedBox.shrink();
  final cs = Theme.of(context).colorScheme;
  final color = v['verdict'] == 'better'
      ? cs.primaryContainer
      : v['verdict'] == 'worse'
          ? cs.errorContainer
          : cs.surfaceContainerHigh;
  String pp(num x) => '${x >= 0 ? '+' : ''}${(100 * x).toStringAsFixed(1)}';
  return Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
    child: Text('${v['label']} ${pp(v['diff'] as num)}%p (95% ${pp(v['low'] as num)}~${pp(v['high'] as num)})',
        style: const TextStyle(fontSize: 12)),
  );
}

Widget jobProgress(BuildContext context, JobState job, VoidCallback cancel) {
  if (!job.running) {
    if (job.state == 'error') return Text('실패: ${job.error}', style: TextStyle(color: Theme.of(context).colorScheme.error));
    if (job.state == 'cancelled') return const Text('취소되었습니다.');
    return const SizedBox.shrink();
  }
  final p = job.progress ?? const {};
  return Row(children: [
    Expanded(
        child: LinearProgressIndicator(
            value: (p['total'] ?? 0) == 0 ? null : (p['done'] as num) / (p['total'] as num))),
    const SizedBox(width: 8),
    Text('${p['note'] ?? ''}', style: const TextStyle(fontSize: 12)),
    TextButton(onPressed: cancel, child: const Text('취소')),
  ]);
}

class _ReplacePanel extends ConsumerStatefulWidget {
  final int slot;
  const _ReplacePanel({required this.slot});
  @override
  ConsumerState<_ReplacePanel> createState() => _ReplacePanelState();
}

class _ReplacePanelState extends ConsumerState<_ReplacePanel> {
  String mode = 'best';
  Json? result;
  String? error;
  bool loading = false;
  final picked = <int>{};
  static const modes = {
    'best': '최고 성능',
    'weakness': '약점 보완',
    'keep': '전략 유지',
    'pivot': '전략 전환',
    'joker': '조커 발굴',
  };

  Future<void> find() async {
    final team = ref.read(teamProvider);
    final notifier = ref.read(teamProvider.notifier);
    setState(() {
      loading = true;
      error = null;
      picked.clear();
    });
    try {
      final rev = ref.read(teamRevisionProvider);
      final res = await dio.post('/api/workbench/replace', data: {
        'format': ref.read(formatProvider),
        'teamRevision': rev,
        'team': [for (final s in team) s.set],
        'slot': widget.slot,
        'mode': mode,
        'locks': ref.read(lockProvider.notifier).of(notifier.activeName, team.length),
      });
      setState(() => result = res.data as Json);
    } catch (e) {
      setState(() => error = apiError(e));
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final team = ref.watch(teamProvider);
    final rev = ref.watch(teamRevisionProvider);
    final job = ref.watch(replaceJobProvider);
    final cs = Theme.of(context).colorScheme;
    if (team.isEmpty) return const Text('팀에 포켓몬을 먼저 넣어 주세요.');
    final slot = widget.slot.clamp(0, team.length - 1);
    final cands = ((result?['candidates'] as List?) ?? const []).cast<Json>();
    final validation = job.result;
    final valRows = {
      for (final r in ((validation?['candidates'] as List?) ?? const []).cast<Json>()) r['pokemon']: r
    };

    return Section('${slot + 1}번 자리 교체 · ${team[slot].detail['ko'] ?? team[slot].detail['name']}',
        subtitle: '왼쪽에서 자리를 고르세요. 후보는 정적 지표로 찾고, 결론은 모의전 검증으로 냅니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final e in modes.entries)
              ChoiceChip(label: Text(e.value), selected: mode == e.key, onSelected: (_) => setState(() => mode = e.key)),
          ]),
          const SizedBox(height: 8),
          FilledButton(onPressed: loading ? null : find, child: Text(loading ? '찾는 중…' : '교체 후보 찾기')),
          if (error != null) Text(error!, style: TextStyle(color: cs.error)),
          if (result != null) ...[
            staleBanner(context, result!['teamRevision'] as int?, rev),
            const SizedBox(height: 6),
            Text('${result!['note']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            for (var i = 0; i < cands.length; i++) _candidateCard(context, cands[i], i, slot, valRows[cands[i]['pokemon']['id']]),
            const SizedBox(height: 8),
            FilledButton.tonal(
              onPressed: picked.isEmpty || job.running || result!['teamRevision'] != rev
                  ? null
                  : () => ref.read(replaceJobProvider.notifier).start('/api/workbench/replace/validate', {
                        'format': ref.read(formatProvider),
                        'team': [for (final s in team) s.set],
                        'slot': slot,
                        'candidates': [for (final i in picked) cands[i]['set']],
                        'games': 40,
                        'holdout': 80,
                      }, rev),
              child: Text('고른 후보 ${picked.length}개 모의전 검증 (선별 40판 + 독립 검증 80판)'),
            ),
            jobProgress(context, job, () => ref.read(replaceJobProvider.notifier).cancel()),
            if (validation != null) ...[
              staleBanner(context, job.revision, rev),
              Text(
                  '원본 · 선별 ${(100 * (validation['original']['screen'] as num)).round()}% · 독립 검증 ${(100 * (validation['original']['holdout'] as num)).round()}% (마스터볼, 스타일 5종)',
                  style: const TextStyle(fontSize: 12.5)),
              if (validation['precise'] == false)
                Text('모의전이 계산하지 않는 효과가 들어 있어 정밀한 실험이 아닙니다.', style: TextStyle(color: cs.error, fontSize: 12)),
              Text('${validation['method']}', style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
            ],
          ],
        ]));
  }

  Widget _candidateCard(BuildContext context, Json c, int i, int slot, Json? val) {
    final cs = Theme.of(context).colorScheme;
    final p = c['pokemon'] as Json;
    final locks = ref.read(lockProvider.notifier).of(ref.read(teamProvider.notifier).activeName, ref.read(teamProvider).length);
    return Card(
      margin: const EdgeInsets.only(top: 8),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Checkbox(
                value: picked.contains(i),
                onChanged: (v) => setState(() => v == true && picked.length < 3 ? picked.add(i) : picked.remove(i))),
            Sprite(p['sprite'] as String, size: 34),
            const SizedBox(width: 6),
            Expanded(
                child: Text('${p['ko'] ?? p['name']} · ${c['set']['item'] ?? ''}',
                    style: const TextStyle(fontWeight: FontWeight.w700))),
            Text('정적 ${(c['staticDelta'] as num) >= 0 ? '+' : ''}${c['staticDelta']}점',
                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          ]),
          for (final r in (c['reasons'] as List)) Text('＋ $r', style: const TextStyle(fontSize: 12.5)),
          for (final r in (c['risks'] as List)) Text('－ $r', style: TextStyle(fontSize: 12.5, color: cs.error)),
          if (c['strategy']?['after'] != null && c['strategy']['after'] != c['strategy']['before'])
            Text('전략 변화 · ${c['strategy']['before']} → ${c['strategy']['after']}', style: const TextStyle(fontSize: 12)),
          if (val != null) ...[
            const SizedBox(height: 4),
            Row(children: [const Text('선별 ', style: TextStyle(fontSize: 12)), verdictChip(context, val['screen'] as Json?)]),
            if (val['holdout'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(children: [
                  const Text('독립 검증 ', style: TextStyle(fontSize: 12)),
                  verdictChip(context, val['holdout'] as Json?)
                ]),
              ),
            if (val['pickShift'] != null)
              Text('선봉이 바뀐 상대 유형 비율 ${(100 * (val['pickShift'] as num)).round()}% (선출 변화 영향)',
                  style: const TextStyle(fontSize: 11.5)),
          ],
          Align(
            alignment: Alignment.centerRight,
            child: TextButton(
              onPressed: (locks[slot]['pokemon'] ?? false)
                  ? null
                  : () async {
                      ref.read(historyProvider.notifier).record();
                      await ref.read(teamProvider.notifier).add(p['id'] as String, set: Json.from(c['set'] as Map), replaceAt: slot);
                    },
              child: const Text('이 후보로 교체'),
            ),
          ),
        ]),
      ),
    );
  }
}

final _matchupTeamProvider = FutureProvider.autoDispose<Json?>((ref) async {
  ref.watch(apiContextProvider);
  final enemy = ref.watch(enemyProvider);
  final team = ref.watch(teamProvider);
  final format = ref.watch(formatProvider);
  final revision = ref.watch(teamRevisionProvider);
  if (enemy.length != 6 || team.length < (format == 'Doubles' ? 4 : 3)) return null;
  final res = await dio.post('/api/workbench/matchup/team', data: {
    'format': format,
    'teamRevision': revision,
    'team': [for (final s in team) s.set],
    'enemy': [for (final mon in enemy) mon['id']],
  });
  return res.data as Json;
});

class _MatchupPanel extends ConsumerStatefulWidget {
  const _MatchupPanel();
  @override
  ConsumerState<_MatchupPanel> createState() => _MatchupPanelState();
}

class _MatchupPanelState extends ConsumerState<_MatchupPanel> {
  Json? foe;
  Json? single;
  String? error;
  List<String> custom = const [];
  int? customRevision;

  Future<void> pickFoe() async {
    final list = await ref.read(pokemonListProvider.future);
    if (!mounted) return;
    final p = await showPokemonPicker(context, list, ref.read(formatProvider));
    if (p == null) return;
    setState(() => foe = p);
    try {
      final team = ref.read(teamProvider);
      final res = await dio.post('/api/workbench/matchup/pokemon', data: {
        'format': ref.read(formatProvider),
        'teamRevision': ref.read(teamRevisionProvider),
        'team': [for (final s in team) s.set],
        'foe': p['id'],
      });
      setState(() => single = res.data as Json);
    } catch (e) {
      setState(() => error = apiError(e));
    }
  }

  Future<void> addEnemy() async {
    final list = await ref.read(pokemonListProvider.future);
    if (!mounted) return;
    final p = await showPokemonPicker(context, list, ref.read(formatProvider));
    if (!mounted || p == null) return;
    final enemy = ref.read(enemyProvider);
    if (enemy.length >= 6 || enemy.any((x) => x['id'] == p['id'])) return;
    ref.read(enemyProvider.notifier).replace([...enemy, p]);
  }

  @override
  Widget build(BuildContext context) {
    final rev = ref.watch(teamRevisionProvider);
    final team = ref.watch(teamProvider);
    final job = ref.watch(matchupJobProvider);
    final enemy = ref.watch(enemyProvider);
    final analysis = ref.watch(_matchupTeamProvider);
    final teamResult = analysis.isLoading ? null : analysis.valueOrNull;
    final cs = Theme.of(context).colorScheme;
    final rec = teamResult?['recommendation'] as Json?;
    final alternatives = ((rec?['alternatives'] as List?) ?? const []).cast<Json>();
    List<String> ids(Json r) => [
          for (final m in [...(r['lead'] as List? ?? const []), ...(r['back'] as List? ?? const [])]) m['id'] as String
        ];
    final count = ref.watch(formatProvider) == 'Doubles' ? 4 : 3;
    final enemyIds = [for (final mon in enemy) mon['id'] as String]..sort();
    final names = {for (final m in [...team.map((s) => s.detail), ...enemy]) m['id']: (m['ko'] ?? m['name'])};
    String name(Object? id) => '${names[id] ?? id}';
    final resultEnemy = (job.result?['enemy'] as List?)?.join('|');
    bool samePick(List<String> a, List<String> b) {
      final lead = count - 2;
      return a.take(lead).toSet().containsAll(b.take(lead)) &&
          a.skip(lead).toSet().containsAll(b.skip(lead));
    }
    final suggested = [if (rec != null) ids(rec), for (final a in alternatives.take(2)) ids(a)]
        .where((p) => p.length == count).toList();
    final customPick = customRevision == rev && custom.length == count ? custom : const <String>[];
    final picks = [
      if (suggested.isNotEmpty) suggested.first,
      if (customPick.isNotEmpty && suggested.isNotEmpty && !samePick(customPick, suggested.first)) customPick,
      for (final a in suggested.skip(1))
        if (customPick.isEmpty || !samePick(a, customPick)) a,
    ].take(3).toList();
    final hyp = (teamResult?['hypotheses'] as Json?)?['scenario'] as Map?;
    final plans = job.result?['opponentPlans'] as Map? ?? const {};
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Section('상대 포켓몬 하나',
          subtitle: '상대 세트는 채용률 가설(도구·특성)의 확률 가중으로 계산합니다. 확정 정보가 아닙니다.',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            OutlinedButton(onPressed: pickFoe, child: Text(foe == null ? '상대 포켓몬 고르기' : '${foe!['ko'] ?? foe!['name']} · 바꾸기')),
            if (error != null) Text(error!, style: TextStyle(color: cs.error)),
            if (single != null) ...[
              staleBanner(context, single!['teamRevision'] as int?, rev),
              Text('가설: ${(single!['hypotheses'] as List).map((h) => '${h['item'] ?? '-'} / ${h['ability']} ${(100 * (h['prob'] as num)).round()}%').join(' · ')}',
                  style: const TextStyle(fontSize: 12)),
              for (final r in (single!['rows'] as List).cast<Json>())
                Text(
                    '${(single!['safest'] as List).contains(r['id']) ? '★ ' : ''}${r['name']} · 주는 피해 ${r['dealt']}% · 받는 피해 ${r['taken']}% (최대 ${r['worstTaken']}%) · 선공 확률 ${(100 * (r['outspeedProb'] as num)).round()}%${r['ohko'] == true ? ' · 한 방' : ''}',
                    style: const TextStyle(fontSize: 12.5)),
              for (final t in (single!['threats'] as List).cast<Json>())
                Text('위협 · ${t['label']} → ${t['target']} ${t['pct']}%', style: TextStyle(fontSize: 12, color: cs.error)),
              for (final a in (single!['advice'] as List)) Text('제안 · $a', style: const TextStyle(fontSize: 12.5)),
            ],
          ])),
      Section('상대 6마리',
          subtitle: '실전 상대 분석과 같은 명단을 사용합니다. 6마리를 채우면 선출을 추천하고 모의전으로 비교할 수 있습니다.',
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (analysis.isLoading && enemy.length == 6) const LinearProgressIndicator(),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final (i, e) in enemy.indexed)
                InputChip(
                    avatar: Sprite(e['sprite'] as String, size: 22),
                    label: Text('${e['ko'] ?? e['name']}'),
                    onDeleted: () => ref.read(enemyProvider.notifier).removeAt(i)),
              if (enemy.length < 6) ActionChip(label: const Text('+ 상대 추가'), onPressed: addEnemy),
            ]),
            if (analysis.hasError) Text(apiError(analysis.error!), style: TextStyle(color: cs.error)),
            if (teamResult != null) ...[
              if (hyp != null)
                Text('상대 전략 가설 · ${hyp.entries.map((e) => '${_tactics[e.key] ?? e.key} ${fmtPct(100 * (e.value as num))}').join(' · ')}',
                    style: const TextStyle(fontSize: 12.5)),
              if (rec != null)
                Text('추천 선출 · 선봉 ${(rec['lead'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')} · 후발 ${(rec['back'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')}',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              if ((teamResult['leads'] as List? ?? const []).isNotEmpty)
                Text('상대 선봉 후보 · ${(teamResult['leads'] as List).take(3).map((r) =>
                   (r['members'] as List).map((m) => m['ko'] ?? m['name']).join(' + ')).join(' / ')}'),
              Wrap(spacing: 8, children: [
                OutlinedButton(
                  onPressed: picks.isEmpty || job.running ? null : () async {
                    final pick = await showDialog<List<String>>(context: context,
                        builder: (_) => _SelectionDialog(
                          team: [for (final s in team) s.detail],
                          leadSize: count - 2,
                          initial: customPick.isEmpty ? picks.first : customPick,
                        ));
                    if (mounted && pick != null) {
                      setState(() {
                        custom = pick;
                        customRevision = rev;
                      });
                    }
                  },
                  child: Text(customPick.isEmpty ? '내 선출 추가' : '내 선출 수정'),
                ),
                FilledButton.tonal(
                  onPressed: picks.isEmpty || job.running || teamResult['teamRevision'] != rev
                      ? null
                      : () => ref.read(matchupJobProvider.notifier).start('/api/workbench/matchup/validate', {
                            'format': ref.read(formatProvider),
                            'team': [for (final s in team) s.set],
                            'enemy': [for (final e in enemy) e['id']],
                            'picks': picks,
                            'games': 30,
                          }, rev),
                  child: Text('선출 ${picks.length}가지 모의전 비교 (30판씩)')),
              ]),
              if (customPick.isNotEmpty)
                Text('내 선출 · 선봉 ${customPick.take(count - 2).map(name).join(' + ')} · 후발 ${customPick.skip(count - 2).map(name).join(' + ')}'),
              jobProgress(context, job, () => ref.read(matchupJobProvider.notifier).cancel()),
              if (job.result != null && resultEnemy == enemyIds.join('|')) ...[
                staleBanner(context, job.revision, rev),
                for (final (i, r) in (job.result!['rows'] as List).cast<Json>().indexed)
                  LabExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text([
                      if (i == 0) '추천 선출'
                      else if ((r['pick'] as List).join('|') == customPick.join('|')) '내 선출'
                      else '대안 $i',
                      if (r['unavailable'] != null) '모의전 미지원'
                      else '${fmtPct(100 * (r['rate'] as num))} (${r['games']}판)',
                    ].join(' · ')),
                    subtitle: Text('선봉 ${(r['lead'] as List).map(name).join(' + ')} · 후발 ${(r['back'] as List).map(name).join(' + ')}'),
                    children: [
                      if (r['unavailable'] case final String reason)
                        Text(reason)
                      else ...[
                        verdictChip(context, r['vsFirst'] as Json?),
                        Text('모의전 승점률의 95% 구간 ${(r['ci'] as List).join('~')}%'),
                      ],
                      for (final row in (r['openingExamples'] as List? ?? const []).cast<Json>())
                        Text('CPU 첫 턴 선택 ${row['games']}판 · ${(row['actions'] as List).cast<Json>().map((a) =>
                          "${name(a['actor'])} ${a['move'] == 'switch' ? '교체' : a['moveKo']}${a['target'] == '' ? '' : ' → ${name(a['target'])}'}").join(' / ')}'),
                      if ((r['used'] as Map? ?? const {}).isNotEmpty)
                        Text('전술 활용 · ${(r['used'] as Map).entries.map((e) => '${_tactics[e.key] ?? e.key} ${e.value}판').join(' · ')}'),
                    ],
                  ),
                Text('상대 세트·선출 가설 ${job.result!['opponentHypotheses']}가지 · ${job.result!['note']}',
                    style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
                if (plans.isNotEmpty)
                  Text('상대 핵심 조합을 시험한 판 · ${plans.entries.map((e) => '${_tactics[e.key] ?? e.key} ${e.value}판').join(' · ')}'),
              ],
            ],
          ])),
    ]);
  }
}

const _tactics = {
  'rain': '비', 'sun': '쾌청', 'sand': '모래바람', 'snow': '눈', 'psychic': '사이코필드',
  'tailwind': '순풍', 'trickroom': '트릭룸', 'setup': '능력치 강화', 'balance': '균형형',
};

class _SelectionDialog extends StatefulWidget {
  const _SelectionDialog({required this.team, required this.leadSize, required this.initial});
  final List<Json> team;
  final int leadSize;
  final List<String> initial;

  @override
  State<_SelectionDialog> createState() => _SelectionDialogState();
}

class _SelectionDialogState extends State<_SelectionDialog> {
  late final lead = widget.initial.take(widget.leadSize).toSet();
  late final back = widget.initial.skip(widget.leadSize).toSet();

  @override
  Widget build(BuildContext context) {
    Widget choices(Set<String> selected, Set<String> other, int limit) => Wrap(
      spacing: 6,
      children: [
        for (final mon in widget.team)
          FilterChip(
            label: Text('${mon['ko'] ?? mon['name']}'),
            selected: selected.contains(mon['id']),
            onSelected: !selected.contains(mon['id']) && selected.length == limit ? null : (checked) {
              final id = mon['id'] as String;
              setState(() {
                if (checked) {
                  other.remove(id);
                  selected.add(id);
                } else {
                  selected.remove(id);
                }
              });
            },
          ),
      ],
    );
    return AlertDialog(
      title: const Text('비교할 내 선출'),
      content: SizedBox(width: 400, child: SingleChildScrollView(child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('선봉 ${lead.length}/${widget.leadSize}'),
          choices(lead, back, widget.leadSize),
          const SizedBox(height: 8),
          Text('후발 ${back.length}/2'),
          choices(back, lead, 2),
        ],
      ))),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('취소')),
        FilledButton(
          onPressed: lead.length == widget.leadSize && back.length == 2
              ? () => Navigator.pop(context, [...lead, ...back]) : null,
          child: const Text('비교에 추가'),
        ),
      ],
    );
  }
}

class _LabPanel extends ConsumerStatefulWidget {
  const _LabPanel();
  @override
  ConsumerState<_LabPanel> createState() => _LabPanelState();
}

class _LabPanelState extends ConsumerState<_LabPanel> {
  int other = -1;
  String difficulty = 'master';
  int games = 60;

  @override
  Widget build(BuildContext context) {
    final teams = ref.watch(teamListProvider);
    final active = ref.watch(activeTeamIndexProvider);
    final team = ref.watch(teamProvider);
    final rev = ref.watch(teamRevisionProvider);
    final job = ref.watch(experimentJobProvider);
    final cs = Theme.of(context).colorScheme;
    final r = job.result;
    final options = [for (var i = 0; i < teams.length; i++) if (i != active && teams[i].sets.isNotEmpty) i];
    if (!options.contains(other)) other = options.isEmpty ? -1 : options.first;
    String pct(num x) => '${(100 * x).toStringAsFixed(1)}%';
    return Section('모의전 실험',
        subtitle: '지금 팀(A)과 저장된 다른 팀(B)을 같은 상대·같은 난수로 비교합니다. 팀 복제 후 한 곳만 고쳐 비교하면 수정 전후 실험이 됩니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (options.isEmpty) const Text('비교할 팀이 없습니다. 왼쪽 위 복제 버튼으로 팀을 복제해 고친 뒤 비교하세요.'),
          if (options.isNotEmpty)
            DropdownButton<int>(
              value: other,
              isExpanded: true,
              items: [for (final i in options) DropdownMenuItem(value: i, child: Text('B: ${teams[i].name}'))],
              onChanged: (v) => setState(() => other = v ?? other),
            ),
          Row(children: [
            const Text('CPU '),
            DropdownButton<String>(
              value: difficulty,
              items: const [
                DropdownMenuItem(value: 'ultra', child: Text('하이퍼볼')),
                DropdownMenuItem(value: 'master', child: Text('마스터볼')),
                DropdownMenuItem(value: 'champion', child: Text('챔피언')),
              ],
              onChanged: (v) => setState(() => difficulty = v ?? difficulty),
            ),
            const SizedBox(width: 12),
            const Text('판 수 '),
            DropdownButton<int>(
              value: games,
              items: const [
                DropdownMenuItem(value: 30, child: Text('30')),
                DropdownMenuItem(value: 60, child: Text('60')),
                DropdownMenuItem(value: 120, child: Text('120')),
              ],
              onChanged: (v) => setState(() => games = v ?? games),
            ),
          ]),
          FilledButton(
            onPressed: other < 0 || job.running || team.isEmpty
                ? null
                : () => ref.read(experimentJobProvider.notifier).start('/api/workbench/experiment', {
                      'format': ref.read(formatProvider),
                      'a': [for (final s in team) s.set],
                      'b': teams[other].sets,
                      'games': games,
                      'difficulty': difficulty,
                    }, rev),
            child: const Text('실험 실행'),
          ),
          jobProgress(context, job, () => ref.read(experimentJobProvider.notifier).cancel()),
          if (r != null) ...[
            staleBanner(context, job.revision, rev),
            Text('A ${pct(r['a']['rate'] as num)} (95% ${(r['a']['ci'] as List).join('~')}%) · B ${pct(r['b']['rate'] as num)} · ${r['games']}판 · ${r['difficulty']}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            Row(children: [const Text('B − A '), verdictChip(context, r['diff'] as Json?)]),
            if (r['precise'] == false)
              Text('모의전이 계산하지 않는 효과가 들어 있어 정밀한 실험이 아닙니다.', style: TextStyle(color: cs.error, fontSize: 12)),
            const SizedBox(height: 6),
            const Text('상대 유형별 (A)', style: TextStyle(fontWeight: FontWeight.w600)),
            for (final a in (r['a']['byArchetype'] as List).cast<Json>())
              Text('${a['label']} ${a['win']}/${a['runs']}', style: const TextStyle(fontSize: 12.5)),
            const SizedBox(height: 4),
            const Text('A의 패배 원인', style: TextStyle(fontWeight: FontWeight.w600)),
            for (final t in (r['a']['lossTags'] as List).cast<Json>())
              Text('${t['label']} · 진 판의 ${(100 * (t['share'] as num)).round()}%', style: const TextStyle(fontSize: 12.5)),
            const SizedBox(height: 4),
            Text('실제로 전개한 전술 (A): ${(r['a']['executed'] as Map).entries.map((e) => '${e.key} ${e.value}회').join(', ')}',
                style: const TextStyle(fontSize: 12.5)),
          ],
        ]));
  }
}

class _FeedbackPanel extends ConsumerStatefulWidget {
  const _FeedbackPanel();
  @override
  ConsumerState<_FeedbackPanel> createState() => _FeedbackPanelState();
}

class _FeedbackPanelState extends ConsumerState<_FeedbackPanel> {
  Json? result;
  String? error;
  String? resultScope;
  bool running = false;

  Future<void> run(String format, String scope, List<Json> records) async {
    setState(() {
      resultScope = scope;
      result = null;
      error = null;
      running = true;
    });
    try {
      final res = await dio.post('/api/workbench/feedback', data: {
        'format': format,
        'records': records.take(500).toList(),
      });
      if (mounted) setState(() => result = res.data as Json);
    } catch (e) {
      if (mounted) setState(() => error = apiError(e));
    } finally {
      if (mounted) setState(() => running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final journal = ref.watch(matchJournalProvider).valueOrNull ?? const <Json>[];
    final name = ref.read(teamProvider.notifier).activeName;
    ref.watch(activeTeamIndexProvider);
    final format = ref.watch(formatProvider);
    final mine = journal.where((r) => r['teamName'] == name && r['format'] == format).toList();
    final scope = '$format|$name|${mine.firstOrNull?['at']}';
    final result = resultScope == scope ? this.result : null;
    final error = resultScope == scope ? this.error : null;
    final cs = Theme.of(context).colorScheme;
    return Section('실전 기록',
        subtitle: '상대 분석에서 경기 전 예측을 저장한 뒤 실제 선출과 결과를 기록하면 두 내용을 비교할 수 있습니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('이 팀($name)의 기록 ${mine.length}판 · 전체 ${journal.length}판'),
          const SizedBox(height: 6),
          FilledButton(onPressed: mine.isEmpty || running ? null : () => run(format, scope, mine),
              child: Text(running && resultScope == scope ? '분석 중' : '기록 분석')),
          if (error != null) Text(error, style: TextStyle(color: cs.error)),
          if (result != null) ...[
            Text('${result['note']}', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            if (result['rate'] != null)
              Text('실전 승점률 ${(100 * (result['rate'] as num)).round()}% (95% ${(result['ci'] as List).join('~')}%)'),
            for (final t in (result['trouble'] as List).cast<Json>())
              Text('자주 지는 상대 · ${t['name']} ${t['losses']}패/${t['games']}판', style: const TextStyle(fontSize: 12.5)),
            if (result['pickCheck'] case final Json picks)
              Text('경기 전 예측을 남긴 ${picks['saved'] ?? 0}판 · 내 선봉과 후발 모두 일치 ${picks['followed']}판 · 다름 ${picks['deviated']}판',
                  style: const TextStyle(fontSize: 12.5)),
            if (result['enemyLeadCheck'] case final Json foe when (foe['games'] as int) > 0)
              Text('상대 선봉 예측 · 첫 후보 ${foe['topOne']}/${foe['games']} · 상위 후보 ${foe['topThree']}/${foe['games']}'),
            if (result['calibration'] case final Json sample)
              Text('같은 선출로 비교한 ${sample['games']}판 · 경기 전 모의전 ${fmtPct(100 * (sample['simulated'] as num))} · 실전 ${fmtPct(100 * (sample['observed'] as num))}'),
            if (result['openingCheck'] case final Json opening when (opening['games'] as int) > 0)
              Text('내 첫 턴 기술·교체가 저장한 CPU 선택 예시와 일치 ${opening['matches']}/${opening['games']}판'),
            for (final row in (result['lossReasons'] as List? ?? const []).cast<Json>())
              Text('직접 기록한 패배 요인 · ${row['text']} ${row['count']}회'),
            for (final row in (result['turnObservations'] as List? ?? const []).cast<Json>())
              Text("관측 · ${row['turn'] == null ? '' : '${row['turn']}턴 · '}${row['text']}"),
            for (final h in (result['hypotheses'] as List).cast<Json>())
              Text('다음 실험 · ${h['text']}', style: const TextStyle(fontSize: 12.5)),
          ],
        ]));
  }
}
