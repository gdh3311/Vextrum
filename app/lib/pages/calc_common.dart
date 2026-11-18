import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../team_state.dart';
import '../widgets.dart';

/// 계산 화면(스피드 비교·데미지 계산)에서 쓰는 공통 도구.

/// 내 팀 포켓몬을 먼저 보여 주고, 아니면 전체 목록에서 고른다. 고른 포켓몬은 인기 세트로 시작한다.
Future<TeamSlot?> pickCalcMon(BuildContext context, WidgetRef ref, {String title = '포켓몬 선택'}) async {
  final team = ref.read(teamProvider);
  final choice = await showDialog<Object>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(title),
      content: SizedBox(
        width: 420,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (team.isNotEmpty) ...[
            Text('내 팀', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Theme.of(context).colorScheme.primary)),
            const SizedBox(height: 6),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (final s in team)
                InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: () => Navigator.pop(context, s),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Column(children: [
                      Sprite(s.sprite, size: 48),
                      SizedBox(
                          width: 64,
                          child: Text('${s.detail['ko'] ?? s.detail['name']}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              textAlign: TextAlign.center,
                              style: const TextStyle(fontSize: 11.5))),
                    ]),
                  ),
                ),
            ]),
            const SizedBox(height: 14),
          ],
          FilledButton.tonal(onPressed: () => Navigator.pop(context, 'any'), child: const Text('전체 포켓몬에서 고르기')),
        ]),
      ),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('닫기'))],
    ),
  );
  if (choice is TeamSlot) return choice;
  if (choice != 'any' || !context.mounted) return null;
  final all = await ref.read(pokemonListProvider.future);
  if (!context.mounted) return null;
  final picked = await showPokemonPicker(context, all, ref.read(formatProvider));
  if (picked == null) return null;
  final detail = await ref.read(pokemonDetailProvider(picked['id'] as String).future);
  return TeamSlot(Json.from(detail['defaultSet'] as Json), detail);
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

String hitsLabel(int? hits, num chance) {
  if (hits == null) return tr('6번 안에 못 쓰러뜨림');
  if (chance >= .9995) return tr('확정 {}타').replaceFirst('{}', '$hits');
  return tr('난수 {}타 ({})').replaceFirst('{}', '$hits').replaceFirst('{}', fmtPct(chance * 100));
}
