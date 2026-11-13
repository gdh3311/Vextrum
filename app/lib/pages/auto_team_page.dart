import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../main.dart';
import '../team_state.dart';
import '../widgets.dart';
import 'build_loader.dart';
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

const _originalities = <(String, String, String)>[
  ('meta', '메타 중심', '승률을 가장 우선합니다. 상위 랭커 파티와 비슷한 팀이 나올 수 있습니다.'),
  ('balanced', '균형', '랭커 파티와 최대 3마리까지만 겹치게 하고, 그 안에서 승률이 가장 높은 팀을 찾습니다. 같은 전략도 여러 에이스에서 출발합니다.'),
  ('unique', '독창적', '랭커 파티와 최대 2마리만 겹치는 나만의 팀을 찾습니다. 메타 핵심을 덜 쓰는 만큼 승률은 조금 낮을 수 있습니다.'),
];
const _jokerModes = <(String, String, String)>[
  ('off', '제외', '사용률 40위 안의 포켓몬으로만 구성합니다.'),
  ('allow', '허용', '조커 파인더의 세트도 후보에 넣어 함께 겨룹니다.'),
  ('force', '1마리 필수', '팀마다 사용률 40위 밖의 조커를 1마리 넣습니다.'),
];
const _megaModes = <(String, String, String)>[
  ('auto', '자동', '메가스톤은 많아야 1~2개. 성적이 좋은 쪽을 고릅니다.'),
  ('one', '1마리 필수', '메가진화 포켓몬을 반드시 1마리 넣습니다.'),
  ('none', '쓰지 않음', '메가스톤 없이 도구를 자유롭게 씁니다.'),
];
const _cores = <(String, String, String)>[
  ('', '상관없음', ''),
  ('fwg', '불·물·풀', '서로의 약점을 받아주는 불·물·풀 타입을 함께 넣습니다.'),
  ('dsf', '드래곤·강철·페어리', '드래곤·강철·페어리 타입으로 서로의 약점을 받아줍니다.'),
  ('resist', '약점 최소화', '여러 마리가 같은 약점을 갖는 구성을 더 강하게 피합니다.'),
];
const _tunes = <(String, String, String)>[
  ('off', '사용률 세트', '각 포켓몬의 가장 흔한 세트를 그대로 씁니다.'),
  ('quick', '빠르게', '도구·특성·기술·능력 포인트를 바꿔 보고 확인합니다 (후보당 40판 → 160판).'),
  ('standard', '표준', '도구·특성·기술·능력 포인트를 바꿔 보고 확인합니다 (후보당 60판 → 240판).'),
  ('deep', '정밀', '도구·특성·기술·능력 포인트를 바꿔 보고 확인합니다 (후보당 100판 → 400판).'),
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
  String joker = 'allow';
  String mega = 'auto';
  String core = '';
  String tune = 'standard';
  bool rankers = true;
  String originality = 'balanced';
  Json? result;
  String? error;
  bool building = false;
  Json? progress;
  int _run = 0;
  final resultsKey = GlobalKey();
  final loaderKey = GlobalKey();

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
    final run = ++_run;
    setState(() {
      building = true;
      result = null;
      error = null;
      progress = null;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (loaderKey.currentContext case final target?) {
        Scrollable.ensureVisible(target,
            alignment: .5, duration: const Duration(milliseconds: 450), curve: Curves.easeOutCubic);
      }
    });
    try {
      final body = {
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
        'joker': joker,
        'mega': mega,
        'core': core,
        'tune': tune,
        'rankers': rankers,
        'originality': originality,
      };
      Json data;
      try {
        // 뒤에서 돌리고 진행 상황을 받아 애니메이션에 보여 준다.
        final job = (await dio.post('/api/team/build/start', data: body)).data as Json;
        data = await _follow(job['id'] as String, run);
      } on DioException catch (failure) {
        if (failure.response?.statusCode != 404 && failure.response?.statusCode != 405) rethrow;
        // 진행 상황을 모르는 예전 서버
        data = (await dio.post('/api/team/build', data: body)).data as Json;
      }
      if (!mounted || run != _run) return;
      if (mounted) {
        setState(() => result = data);
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
    } on _Cancelled {
      // 사용자가 그만 보기를 눌렀다.
    } finally {
      if (mounted && run == _run) setState(() => building = false);
    }
  }

  Future<Json> _follow(String job, int run) async {
    while (true) {
      await Future<void>.delayed(const Duration(milliseconds: 650));
      if (!mounted || run != _run) throw _Cancelled();
      final status = (await dio.get('/api/team/build/$job')).data as Json;
      if (!mounted || run != _run) throw _Cancelled();
      if (status['progress'] case final Json p) setState(() => progress = p);
      switch (status['state']) {
        case 'done':
          return status['result'] as Json;
        case 'error':
          throw DioException(
            requestOptions: RequestOptions(path: '/api/team/build/$job'),
            response: Response(
              requestOptions: RequestOptions(path: '/api/team/build/$job'),
              statusCode: 422,
              data: {'detail': status['error']},
            ),
          );
      }
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
        '구성 조건',
        subtitle: '팀 개성, 조커, 메가진화, 타입 조합과 세트 최적화를 고릅니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _OptionRow(
            label: '팀 개성',
            options: _originalities,
            value: originality,
            onChanged: building ? null : (v) => _change(() => originality = v),
          ),
          _OptionRow(
            label: '조커 포켓몬',
            options: _jokerModes,
            value: joker,
            onChanged: building ? null : (v) => _change(() => joker = v),
          ),
          _OptionRow(
            label: '메가진화',
            options: _megaModes,
            value: mega,
            onChanged: building ? null : (v) => _change(() => mega = v),
          ),
          _OptionRow(
            label: '타입 조합',
            options: _cores,
            value: core,
            onChanged: building ? null : (v) => _change(() => core = v),
          ),
          _OptionRow(
            label: '세트 최적화',
            options: _tunes,
            value: tune,
            onChanged: building ? null : (v) => _change(() => tune = v),
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('랭커 파티 상대 전적도 확인'),
            subtitle: const Text('시즌 상위 랭커 파티와도 싸워 유리·호각·불리를 보여 줍니다.'),
            value: rankers,
            onChanged: building
                ? null
                : (v) => _change(() {
                      rankers = v;
                      if (!v && objective == 'ranker') objective = 'win';
                    }),
          ),
        ]),
      ),
      Section(
        '팀을 고르는 기준',
        subtitle: switch (objective) {
          'stability' => '전략별 승률 중 가장 낮은 값이 높은 팀을 먼저 봅니다.',
          'ranker' => '메타 상대군 승률과 랭커 파티 상대 승률을 반씩 합쳐 봅니다.',
          _ => '여러 상대를 합친 전체 승률이 높은 팀을 먼저 봅니다.',
        },
        child: Wrap(spacing: 8, runSpacing: 6, children: [
          for (final (value, label) in [
            ('win', '종합 승률'),
            ('stability', '약점 보완'),
            if (rankers) ('ranker', '랭커 파티 상대'),
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
        subtitle: '평가 깊이를 높이면 멤버를 더 여러 번 바꿔 보고, 검증 경기 수도 늘어납니다.',
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
              'quick' => '후보 36팀 경주 10→20판 · 교체 1라운드 · 최종 40판',
              'deep' => '후보 90팀 경주 14→28→48판 · 교체 3라운드 · 최종 160판',
              _ => '후보 56팀 경주 12→24→32판 · 교체 2라운드 · 최종 80판',
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
              ? TeamBuildLoader(
                  key: loaderKey,
                  progress: progress,
                  onCancel: () => setState(() {
                    _run++;
                    building = false;
                    progress = null;
                  }),
                )
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
      if ((result?['evaluation'] as Json?)?['ignored'] case final List ignored when ignored.isNotEmpty)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(tr('싱글배틀에서는 쓸 수 없는 전술을 빼고 만들었습니다: {}')
              .replaceFirst('{}', ignored.map((e) => tr(e as String)).join(', '))),
        ),
      for (final w in ((result?['evaluation'] as Json?)?['dataWarnings'] as List? ?? const []).cast<Json>())
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
              color: (w['level'] == 'warn' ? cs.tertiaryContainer : cs.surfaceContainerHigh),
              borderRadius: BorderRadius.circular(10)),
          child: Text(tr(w['text'] as String),
              style: TextStyle(color: w['level'] == 'warn' ? cs.onTertiaryContainer : null, fontSize: 13)),
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

/// 라벨 + 선택 칩 + 고른 항목 설명
class _OptionRow extends StatelessWidget {
  const _OptionRow(
      {required this.label,
      required this.options,
      required this.value,
      required this.onChanged});
  final String label;
  final List<(String, String, String)> options;
  final String value;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final help = options.firstWhere((o) => o.$1 == value).$3;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: theme.textTheme.titleSmall),
        const SizedBox(height: 5),
        Wrap(spacing: 8, runSpacing: 6, children: [
          for (final (key, text, _) in options)
            ChoiceChip(
              label: Text(text),
              selected: value == key,
              onSelected: onChanged == null ? null : (_) => onChanged!(key),
            ),
        ]),
        if (help.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text(help, style: theme.textTheme.bodySmall),
        ],
      ]),
    );
  }
}

class _Cancelled implements Exception {}
