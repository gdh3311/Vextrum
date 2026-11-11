import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'battle_console.dart';
import 'party_simulation.dart';
import 'parties_page.dart';
import '../i18n.dart';

const _focuses = <(String, String, String, LabGlyph)>[
  ('', '알아서 추천', '여러 운영을 비교해 시뮬레이션 성적이 좋은 팀을 찾습니다.', LabGlyph.spark),
  ('speed', '스피드', '스피드가 높은 공격수 3마리를 넣어 먼저 때릴 기회를 늘립니다.', LabGlyph.bolt),
  (
    'physical',
    '물리 공격',
    '공격 능력치를 쓰는 공격수를 3마리 이상 넣고 특수 공격도 보완합니다.',
    LabGlyph.versus
  ),
  (
    'special',
    '특수 공격',
    '특수공격 능력치를 쓰는 공격수를 3마리 이상 넣고 물리 공격도 보완합니다.',
    LabGlyph.crystal
  ),
  ('bulky', '내구', '공격을 받아내는 포켓몬 3마리와 회복 기술을 목표로 구성합니다.', LabGlyph.shield),
  ('balance', '균형', '물리 공격, 특수 공격, 내구 역할을 골고루 섞습니다.', LabGlyph.team),
];
const _weathers = <(String, String, String)>[
  ('', '날씨 조건 없음', ''),
  ('rain', '비', '비를 내릴 포켓몬과 비가 오면 물 기술이 강해지거나 더 빨라지는 포켓몬을 짝짓습니다.'),
  ('sun', '쾌청', '햇살을 만들 포켓몬과 햇살 아래에서 불 기술이 강해지거나 더 빨라지는 포켓몬을 짝짓습니다.'),
  ('sand', '모래바람', '모래바람을 만들고, 모래 속에서 빨라지거나 특수 공격을 더 잘 버티는 포켓몬을 넣습니다.'),
  ('snow', '눈', '눈을 내리고, 눈보라를 쓰거나 눈 속에서 빨라지거나 더 잘 버티는 포켓몬을 넣습니다.'),
];
const _tactics = <(String, String, String, bool)>[
  ('tailwind', '순풍', '일정 턴 동안 아군이 더 빨리 움직이게 합니다.', true),
  ('trickroom', '트릭룸', '느린 포켓몬이 먼저 행동하도록 순서를 바꿉니다.', true),
  ('psychic', '사이코필드', '지상 포켓몬을 선제기에서 보호하고 와이드포스를 강화합니다.', true),
  ('setup', '랭크업', '능력치를 올린 공격수로 후반에 압박합니다.', false),
  ('pivot', '교체 운영', '공격을 받아내거나 교체 기술로 유리한 포켓몬을 내보냅니다.', false),
];

class AutoTeamPage extends ConsumerWidget {
  const AutoTeamPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final format = ref.watch(formatProvider);
    return _AutoTeamForm(format: format, key: ValueKey(format));
  }
}

class _AutoTeamForm extends ConsumerStatefulWidget {
  const _AutoTeamForm({super.key, required this.format});
  final String format;

  @override
  ConsumerState<_AutoTeamForm> createState() => _AutoTeamFormState();
}

class _AutoTeamFormState extends ConsumerState<_AutoTeamForm> {
  final tactics = <String>{};
  String focus = '';
  String weather = '';
  final include = <String, Json>{};
  final exclude = <String, Json>{};
  final locked = <String>{};
  String objective = 'win';
  String depth = 'standard';
  String cpu = 'ultra';
  Json? result;
  String? error;
  bool building = false;
  final resultsKey = GlobalKey();

  void _change(VoidCallback action) {
    setState(() {
      action();
      result = null;
      error = null;
    });
  }

  Future<void> _add(List<Json> mons, Set<String> excluded,
      Map<String, Json> destination) async {
    final selected = await showPokemonPicker(
      context,
      mons.where((p) => !excluded.contains(p['id'])).toList(),
      widget.format,
    );
    if (!mounted || selected == null) return;
    _change(() => destination[selected['id'] as String] = selected);
  }

  Future<void> _generate(List<Json> sets) async {
    setState(() {
      building = true;
      result = null;
      error = null;
    });
    try {
      final response = await dio.post('/api/team/build', data: {
        'format': widget.format,
        'styles': [
          if (focus.isNotEmpty) focus,
          if (weather.isNotEmpty) weather,
          ...tactics
        ],
        'include': include.keys.toList(),
        'exclude': exclude.keys.toList(),
        'locked': sets,
        'objective': objective,
        'depth': depth,
        'cpu': cpu,
      });
      if (mounted) {
        setState(() => result = response.data as Json);
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (resultsKey.currentContext case final target?) {
            Scrollable.ensureVisible(target,
                alignmentPolicy:
                    ScrollPositionAlignmentPolicy.keepVisibleAtEnd);
          }
        });
      }
    } on DioException catch (failure) {
      final body = failure.response?.data;
      final detail = body is Json ? body['detail'] : null;
      if (mounted) {
        setState(() => error =
            failure.response?.statusCode == 422 && detail is String
                ? detail
                : '팀을 만들지 못했습니다. 연결을 확인하고 다시 시도해 주세요.');
      }
    } finally {
      if (mounted) setState(() => building = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final team = ref.watch(teamProvider);
    final mons = ref.watch(pokemonListProvider).valueOrNull;
    final lockSets = [
      for (final slot in team)
        if (locked.contains(slot.set['id'])) slot.set
    ];
    final fixedCount = include.length + lockSets.length;
    final doubles = widget.format == 'Doubles';
    final cs = Theme.of(context).colorScheme;
    final candidates = (result?['candidates'] as List? ?? []).cast<Json>();
    final unavailable = {
      ...include.keys,
      ...exclude.keys,
      ...lockSets.map((s) => s['id'] as String)
    };
    return PageBody(children: [
      PageHeader(
        '팀 자동 구성',
        glyph: LabGlyph.spark,
        subtitle:
            '${doubles ? '더블배틀' : '싱글배틀'} · 선호 조건으로 6마리 팀을 만들고 같은 상대군에서 성적을 비교합니다.',
        trailing: TextButton(
            onPressed: () => context.go('/team'), child: const Text('팀 빌더')),
      ),
      Section(
        '무엇을 중심으로 짤까요?',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 6, children: [
            for (final (key, label, _, glyph) in _focuses)
              ChoiceChip(
                avatar: LabIcon(glyph, size: 17),
                label: Text(label),
                selected: focus == key,
                onSelected: building ? null : (_) => _change(() => focus = key),
              ),
          ]),
          const SizedBox(height: 7),
          Text(_focuses.firstWhere((option) => option.$1 == focus).$3),
          const SizedBox(height: 14),
          Text('날씨를 활용할까요?', style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 5),
          Wrap(spacing: 8, runSpacing: 6, children: [
            for (final (key, label, _) in _weathers)
              ChoiceChip(
                label: Text(label),
                selected: weather == key,
                onSelected:
                    building ? null : (_) => _change(() => weather = key),
              ),
          ]),
          if (weather.isNotEmpty) ...[
            const SizedBox(height: 7),
            Text(_weathers.firstWhere((option) => option.$1 == weather).$3),
          ],
          LabExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text(
                tactics.isEmpty ? '세부 전술 추가' : '세부 전술 · ${tactics.length}개'),
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final (key, label, help, doublesOnly) in _tactics)
                if (doubles || !doublesOnly)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(children: [
                      FilterChip(
                        label: Text(label),
                        selected: tactics.contains(key),
                        onSelected: building
                            ? null
                            : (value) => _change(() {
                                  if (value) {
                                    tactics.add(key);
                                  } else {
                                    tactics.remove(key);
                                  }
                                }),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                          child: Text(help,
                              style: Theme.of(context).textTheme.bodySmall)),
                    ]),
                  ),
            ],
          ),
        ]),
      ),
      Section(
        '팀을 고르는 기준',
        subtitle: objective == 'win'
            ? '여러 상대를 합친 전체 승률이 높은 팀을 먼저 봅니다.'
            : '전략별 승률 중 가장 낮은 값이 높은 팀을 먼저 봅니다.',
        child: Wrap(spacing: 8, runSpacing: 6, children: [
          for (final (value, label) in [
            ('win', '종합 승률'),
            ('stability', '약점 보완')
          ])
            ChoiceChip(
              label: Text(label),
              selected: objective == value,
              onSelected:
                  building ? null : (_) => _change(() => objective = value),
            ),
        ]),
      ),
      Section(
        '평가 방법',
        subtitle: '판 수가 많을수록 결과가 정확하지만 오래 걸립니다. 최종 후보는 고른 수준의 CPU와 다시 싸웁니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 10, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            SizedBox(width: 92, child: Text('평가 깊이', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant))),
            SegmentedButton<String>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: 'quick', label: Text('빠르게')),
                ButtonSegment(value: 'standard', label: Text('표준')),
                ButtonSegment(value: 'deep', label: Text('정밀')),
              ],
              selected: {depth},
              onSelectionChanged: building ? null : (v) => _change(() => depth = v.first),
            ),
            Text(switch (depth) {
              'quick' => '후보당 12판 → 최종 30판',
              'deep' => '후보당 36판 → 최종 120판',
              _ => '후보당 21판 → 최종 56판',
            }, style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
          ]),
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
            SizedBox(width: 92, child: Text('검증 CPU', style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant))),
            SegmentedButton<String>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment(value: 'ultra', label: Text('하이퍼볼')),
                ButtonSegment(value: 'master', label: Text('마스터볼')),
                ButtonSegment(value: 'champion', label: Text('챔피언')),
              ],
              selected: {cpu},
              onSelectionChanged: building ? null : (v) => _change(() => cpu = v.first),
            ),
            Text(cpu == 'champion' ? '실전 플레이어 수준 · 시간이 더 걸립니다' : cpu == 'master' ? '상대 행동을 예측하는 CPU' : '표준 CPU',
                style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant)),
          ]),
        ]),
      ),
      Section(
        '포켓몬 지정 · $fixedCount/5',
        subtitle: '넣을 포켓몬을 지정하거나 현재 팀의 세트를 고정할 수 있습니다. 남은 자리는 자동으로 채웁니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(
              spacing: 8,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                for (final p in include.values)
                  InputChip(
                    deleteIcon: const LabIcon(LabGlyph.cross, size: 15),
                    label: Text('${p['ko'] ?? p['name']}'),
                    avatar: Sprite(p['sprite'] as String, size: 24),
                    onDeleted: building
                        ? null
                        : () => _change(() => include.remove(p['id'])),
                  ),
                OutlinedButton.icon(
                  onPressed: mons == null || building || fixedCount >= 5
                      ? null
                      : () => _add(mons, unavailable, include),
                  icon: const LabIcon(LabGlyph.plus, size: 18),
                  label: const Text('꼭 넣을 포켓몬'),
                ),
              ]),
          if (team.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('현재 팀에서 세트 그대로 가져오기'),
            const SizedBox(height: 4),
            Wrap(spacing: 8, runSpacing: 6, children: [
              for (final slot in team)
                FilterChip(
                  label: Text('${slot.detail['ko'] ?? slot.detail['name']}'),
                  avatar: Sprite(slot.sprite, size: 24),
                  selected: locked.contains(slot.set['id']),
                  onSelected: building ||
                          include.containsKey(slot.set['id']) ||
                          exclude.containsKey(slot.set['id']) ||
                          (!locked.contains(slot.set['id']) && fixedCount >= 5)
                      ? null
                      : (value) => _change(() {
                            final id = slot.set['id'] as String;
                            if (value) {
                              locked.add(id);
                            } else {
                              locked.remove(id);
                            }
                          }),
                ),
            ]),
          ],
        ]),
      ),
      Section(
        '제외할 포켓몬',
        subtitle: '선호하지 않는 포켓몬을 빼고 팀을 만들 수 있습니다.',
        child: Wrap(spacing: 8, runSpacing: 6, children: [
          for (final p in exclude.values)
            InputChip(
              deleteIcon: const LabIcon(LabGlyph.cross, size: 15),
              label: Text('${p['ko'] ?? p['name']}'),
              avatar: Sprite(p['sprite'] as String, size: 24),
              onDeleted: building
                  ? null
                  : () => _change(() => exclude.remove(p['id'])),
            ),
          OutlinedButton.icon(
            onPressed: mons == null || building || exclude.length >= 12
                ? null
                : () => _add(mons, unavailable, exclude),
            icon: const LabIcon(LabGlyph.plus, size: 18),
            label: const Text('제외할 포켓몬 추가'),
          ),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: Align(
          alignment: Alignment.centerLeft,
          child: building
              ? const BattleLoading('팀 후보를 만들고 가상 배틀에서 비교하는 중…')
              : FilledButton.icon(
                  onPressed: () => _generate(lockSets),
                  icon: const LabIcon(LabGlyph.spark, size: 18),
                  label: const Text('팀 만들고 성적 비교'),
                ),
        ),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 14),
          child: Text(error!, style: TextStyle(color: cs.error)),
        ),
      if (result?['splitWeather'] == true)
        const Padding(
          padding: EdgeInsets.only(bottom: 12),
          child: Text('서로 덮어쓰는 날씨는 각각 후보를 만들었습니다.'),
        ),
      if (result?['evaluation'] case final Json evaluation)
        PartyEvaluationSummary(evaluation,
            key: resultsKey, candidates: candidates),
      for (final candidate in candidates)
        PartyCard(key: ValueKey(candidate['id']), party: candidate),
    ]);
  }
}
