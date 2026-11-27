import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../lab_icons.dart';

import '../api.dart';
import '../i18n.dart';
import '../team_state.dart';
import '../widgets.dart';

/// 계산 화면(스피드 비교·데미지 계산)에서 쓰는 공통 도구.

/// 포켓몬 하나 고르기 (한 번에): 맨 위에 내 팀, 아래에 전체 목록과 검색. 고른 포켓몬은 인기 세트로 시작한다.
Future<TeamSlot?> pickCalcMon(BuildContext context, WidgetRef ref) async {
  final team = ref.read(teamProvider);
  final all = await ref.read(pokemonListProvider.future);
  if (!context.mounted) return null;
  final picked = await showPokemonPicker(context, all, ref.read(formatProvider), pinned: [
    for (var i = 0; i < team.length; i++)
      {'sprite': team[i].sprite, 'ko': team[i].detail['ko'], 'name': team[i].detail['name'], '__slot': i},
  ]);
  if (picked == null) return null;
  if (picked['__slot'] is int) return team[picked['__slot'] as int];
  return slotFor(ref, picked['id'] as String);
}

/// 포켓몬 id → 인기 세트로 시작하는 계산용 자리
Future<TeamSlot> slotFor(WidgetRef ref, String id) async {
  final detail = await ref.read(pokemonDetailProvider(id).future);
  return TeamSlot(Json.from(detail['defaultSet'] as Json), detail);
}

/// 배틀 계산기의 두 화면(스피드·데미지)을 오가는 탭
class CalcSwitcher extends StatelessWidget {
  const CalcSwitcher(this.current, {super.key});
  final String current; // '/speed' 또는 '/damage'
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 14),
        child: SegmentedButton<String>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: '/speed', icon: LabIcon(LabGlyph.bolt, size: 16), label: Text('스피드')),
            ButtonSegment(value: '/damage', icon: LabIcon(LabGlyph.shield, size: 16), label: Text('데미지')),
          ],
          selected: {current},
          onSelectionChanged: (v) => context.go(v.first),
        ),
      );
}

/// 한 번에 넣기: 내 팀 또는 메타 상위권 스프라이트를 누르면 바로 그 포켓몬으로 바꾼다.
class QuickPicks extends ConsumerWidget {
  const QuickPicks({super.key, required this.onPick, this.meta = false, this.count = 10});
  final ValueChanged<TeamSlot> onPick;
  final bool meta; // false: 내 팀, true: 메타 상위권
  final int count;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final fmt = ref.watch(formatProvider);
    final List<(String, String, Future<TeamSlot> Function())> items;
    if (meta) {
      final all = ref.watch(pokemonListProvider).valueOrNull ?? const <Json>[];
      final ranked = [for (final p in all) if (p['ranks'][fmt] != null) p]
        ..sort((a, b) => (a['ranks'][fmt] as int).compareTo(b['ranks'][fmt] as int));
      items = [
        for (final p in ranked.take(count))
          (p['sprite'] as String, (p['ko'] ?? p['name']) as String, () => slotFor(ref, p['id'] as String)),
      ];
    } else {
      final team = ref.watch(teamProvider);
      items = [
        for (final s in team) (s.sprite, '${s.detail['ko'] ?? s.detail['name']}', () async => s),
      ];
    }
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(children: [
        Text(meta ? tr('메타 상위') : tr('내 팀'), style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
        const SizedBox(width: 6),
        Expanded(
          child: SizedBox(
            height: 38,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final (sprite, name, load) in items)
                Tooltip(
                  message: name,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(8),
                    onTap: () async => onPick(await load()),
                    child: Padding(padding: const EdgeInsets.symmetric(horizontal: 1), child: Sprite(sprite, size: 36)),
                  ),
                ),
            ]),
          ),
        ),
      ]),
    );
  }
}

/// 세트의 실제 폼(메가면 메가 폼)의 종족값
Map baseStatsOf(TeamSlot s) {
  for (final m in (s.detail['megas'] as List).cast<Json>()) {
    if (m['name'] == s.set['mega']) return m['stats'] as Map;
  }
  return s.detail['stats'] as Map;
}

/// 랭크 보정 배율 (−6 ~ +6)
double stageMultiplier(int stage) => stage >= 0 ? (2 + stage) / 2 : 2 / (2 - stage);

/// 배틀 엔진과 같은 계산: (종족값 + 포인트) × 성격 → 랭크 → 구애스카프 → 순풍 → 마비
int speedOf({
  required num base,
  required int points,
  required int nature, // +1 상승, 0 보정 없음, −1 하락
  int stage = 0,
  bool scarf = false,
  bool tailwind = false,
  bool paralysis = false,
}) {
  var v = ((base + points) * (nature > 0 ? 1.1 : (nature < 0 ? 0.9 : 1.0))).floor();
  v = (v * stageMultiplier(stage)).floor();
  if (scarf) v = (v * 1.5).floor();
  if (tailwind) v *= 2;
  if (paralysis) v = (v * .5).floor();
  return v;
}

/// −6 ~ +6 랭크 고르기
class StageDropdown extends StatelessWidget {
  const StageDropdown({super.key, required this.label, required this.value, required this.onChanged});
  final String label;
  final int value;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Text(label, style: const TextStyle(fontSize: 13)),
        const SizedBox(width: 6),
        DropdownButton<int>(
          value: value,
          isDense: true,
          items: [
            for (var s = 6; s >= -6; s--) DropdownMenuItem(value: s, child: Text(s > 0 ? '+$s' : '$s')),
          ],
          onChanged: (v) => onChanged(v ?? 0),
        ),
      ]);
}

/// 포켓몬 한 마리 머리글 (스프라이트·이름·바꾸기 버튼)
class CalcMonHeader extends StatelessWidget {
  const CalcMonHeader({super.key, required this.slot, required this.onPick, this.trailing, this.label});
  final TeamSlot? slot;
  final VoidCallback onPick;
  final Widget? trailing;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final s = slot;
    return Row(children: [
      if (s != null) Sprite(s.sprite, size: 48) else const SizedBox(width: 48, height: 48),
      const SizedBox(width: 8),
      Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (label != null) Text(label!, style: TextStyle(fontSize: 11.5, color: cs.onSurfaceVariant)),
          if (s == null)
            Text('포켓몬을 고르세요', style: TextStyle(color: cs.onSurfaceVariant))
          else
            NameBlock(s.detail['ko'] as String?, s.detail['name'] as String, size: 15),
        ]),
      ),
      if (trailing != null) trailing!,
      TextButton(onPressed: onPick, child: Text(s == null ? '고르기' : '바꾸기')),
    ]);
  }
}

/// 몇 번에 쓰러뜨리나: 확정이면 '확정 n타', 아니면 확률과 함께 확정 횟수도 보여 준다
/// (예: 4번에 0.2%뿐이면 '확정 5타 · 난수 4타 0.2%').
String hitsLabel(int? hits, num chance, [int? sure]) {
  if (hits == null) return tr('8번 안에 못 쓰러뜨림');
  if (chance >= .9995) return tr('확정 {}타').replaceFirst('{}', '$hits');
  final odds = tr('난수 {}타 ({})').replaceFirst('{}', '$hits').replaceFirst('{}', fmtPct(chance * 100));
  if (sure == null || sure == hits) return odds;
  return '${tr('확정 {}타').replaceFirst('{}', '$sure')} · $odds';
}


/// '다음 시즌 규칙으로 계산' 토글. 발표된 다음 시즌 변경이 없으면 보이지 않는다.
class PreviewRulesChip extends ConsumerWidget {
  const PreviewRulesChip({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final at = ref.watch(nextSeasonAtProvider);
    if (at == null) return const SizedBox.shrink();
    final on = ref.watch(previewRulesProvider);
    return Tooltip(
      message: '공식 공지로 발표된 다음 시즌의 레귤레이션·밸런스 조정·새 포켓몬을 적용해 계산합니다',
      child: FilterChip(
        avatar: LabIcon(LabGlyph.spark, size: 16, color: on ? Theme.of(context).colorScheme.primary : null),
        label: Text(tr('다음 시즌 규칙 ({} 부터)').replaceFirst('{}', '${at.month}/${at.day}')),
        selected: on,
        showCheckmark: false,
        onSelected: (v) => ref.read(previewRulesSwitchProvider.notifier).state = v,
      ),
    );
  }
}
