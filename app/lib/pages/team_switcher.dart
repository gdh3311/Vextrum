import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../lab_icons.dart';
import '../api.dart';
import '../team_state.dart';
import '../widgets.dart';
import '../i18n.dart';

/// 저장된 팀 목록: 눌러서 전환, + 로 새 팀, ⋯ 로 이름·복제·내보내기·삭제
class TeamSwitcher extends ConsumerWidget {
  const TeamSwitcher({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final teams = ref.watch(teamListProvider);
    final active = ref.watch(activeTeamIndexProvider);
    final notifier = ref.read(teamProvider.notifier);

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(children: [
        Expanded(
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              for (var i = 0; i < teams.length; i++)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: _TeamTile(
                      team: teams[i], selected: i == active, onTap: () => notifier.select(i)),
                ),
              Tooltip(
                message: '새 팀 만들기',
                child: Material(
                  color: Colors.transparent,
                  borderRadius: BorderRadius.circular(12),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: notifier.create,
                    child: Container(
                      height: 58,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: cs.outlineVariant, width: 1.5)),
                      child: Row(children: [
                        LabIcon(LabGlyph.plus, size: 18, color: cs.onSurfaceVariant),
                        const SizedBox(width: 6),
                        Text('새 팀', style: TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: cs.onSurfaceVariant)),
                      ]),
                    ),
                  ),
                ),
              ),
            ]),
          ),
        ),
        const SizedBox(width: 8),
        PopupMenuButton<String>(
          tooltip: tr('팀 관리'),
          position: PopupMenuPosition.under,
          color: cs.surfaceContainerHighest,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          icon: LabIcon(LabGlyph.dots, color: cs.onSurfaceVariant),
          onSelected: (v) => _onMenu(context, ref, v, active),
          itemBuilder: (_) => [
            _item('rename', LabGlyph.pencil, '이름 바꾸기'),
            _item('duplicate', LabGlyph.copy, '복제'),
            const PopupMenuDivider(),
            _item('export', LabGlyph.upload, '텍스트로 내보내기'),
            _item('import', LabGlyph.download, '텍스트에서 가져오기'),
            const PopupMenuDivider(),
            _item('clear', LabGlyph.stack, '포켓몬 모두 빼기'),
            _item('delete', LabGlyph.trash, '팀 삭제'),
          ],
        ),
      ]),
    );
  }

  PopupMenuItem<String> _item(String v, LabGlyph icon, String label) => PopupMenuItem(
      value: v,
      height: 40,
      child: Row(children: [LabIcon(icon, size: 18), const SizedBox(width: 10), Text(label, style: const TextStyle(fontSize: 13.5))]));

  Future<void> _onMenu(BuildContext context, WidgetRef ref, String v, int active) async {
    final notifier = ref.read(teamProvider.notifier);
    final name = notifier.activeName;
    switch (v) {
      case 'rename':
        final next = await _textDialog(context, '팀 이름', initial: name, action: '저장');
        if (next != null) notifier.rename(active, next);
      case 'duplicate':
        notifier.duplicate(active);
      case 'clear':
        notifier.clear();
      case 'delete':
        final ok = await showDialog<bool>(
            context: context,
            builder: (c) => AlertDialog(
                  title: const Text('팀 삭제'),
                  content: Text('"$name" 팀을 삭제할까요? 되돌릴 수 없습니다.'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('취소')),
                    FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('삭제')),
                  ],
                ));
        if (ok == true) notifier.delete(active);
      case 'export':
        final text = exportTeamText(ref.read(teamProvider));
        if (!context.mounted) return;
        await showDialog(
            context: context,
            builder: (c) => AlertDialog(
                  title: Text('$name 내보내기'),
                  content: SizedBox(
                    width: 460,
                    child: SingleChildScrollView(
                        child: SelectableText(text.isEmpty ? '팀이 비어 있습니다' : text,
                            style: const TextStyle(fontSize: 13, height: 1.5, fontFamily: 'monospace'))),
                  ),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c), child: const Text('닫기')),
                    FilledButton.icon(
                        onPressed: text.isEmpty
                            ? null
                            : () async {
                                await Clipboard.setData(ClipboardData(text: text));
                                if (c.mounted) Navigator.pop(c);
                                if (context.mounted) {
                                  ScaffoldMessenger.of(context)
                                      .showSnackBar(const SnackBar(content: Text('클립보드에 복사했습니다')));
                                }
                              },
                        icon: const LabIcon(LabGlyph.copy, size: 18),
                        label: const Text('복사')),
                  ],
                ));
      case 'import':
        final text = await _textDialog(context, '텍스트에서 가져오기',
            hint: 'Showdown 형식의 팀 텍스트나 pokepast.es 링크를 붙여 넣으세요.\n현재 팀("$name")의 포켓몬이 이 내용으로 바뀝니다.',
            action: '가져오기',
            lines: 14);
        if (text == null) return;
        var source = text.trim();
        if (RegExp(r'^https?://(www\.)?pokepast\.es/', caseSensitive: false).hasMatch(source)) {
          try {
            source = ((await dio.post('/api/pokepaste', data: {'url': source})).data as Json)['text'] as String;
          } catch (_) {
            if (context.mounted) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('PokePaste 팀을 불러오지 못했습니다')));
            }
            return;
          }
        }
        final all = await ref.read(pokemonListProvider.future);
        final unknown = <String>[];
        final sets = importTeamText(source, all, unknown);
        if (sets.isNotEmpty) await notifier.replaceWith(sets);
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(sets.isEmpty
                  ? '읽을 수 있는 포켓몬이 없습니다'
                  : '${sets.length}마리를 가져왔습니다${unknown.isEmpty ? '' : ' · 찾지 못함: ${unknown.join(', ')}'}')));
        }
    }
  }
}

Future<String?> _textDialog(BuildContext context, String title,
    {String initial = '', String? hint, required String action, int lines = 1}) {
  final ctrl = TextEditingController(text: initial);
  return showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
            title: Text(title),
            content: SizedBox(
              width: 460,
              child: TextField(
                controller: ctrl,
                autofocus: true,
                maxLines: lines,
                style: TextStyle(fontSize: 14, fontFamily: lines > 1 ? 'monospace' : null),
                decoration: InputDecoration(hintText: hint, hintMaxLines: 4),
                onSubmitted: lines == 1 ? (v) => Navigator.pop(c, v) : null,
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(c), child: const Text('취소')),
              FilledButton(onPressed: () => Navigator.pop(c, ctrl.text), child: Text(action)),
            ],
          ));
}

class _TeamTile extends StatelessWidget {
  final TeamSummary team;
  final bool selected;
  final VoidCallback onTap;
  const _TeamTile({required this.team, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: selected ? cs.primary.withOpacity(.14) : cs.surfaceContainerLow,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Container(
          height: 58,
          constraints: const BoxConstraints(minWidth: 132),
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: selected ? cs.primary : Colors.transparent, width: 1.5)),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(team.name,
                style: TextStyle(
                    fontSize: 13.5, fontWeight: FontWeight.w600, color: selected ? cs.primary : cs.onSurface)),
            const SizedBox(height: 2),
            team.sprites.isEmpty
                ? Text('비어 있음', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant))
                : Row(mainAxisSize: MainAxisSize.min, children: [for (final s in team.sprites) Sprite(s, size: 24)]),
          ]),
        ),
      ),
    );
  }
}

/// 다른 화면에서 현재 팀을 고르는 드롭다운 (팀이 둘 이상일 때만 의미가 있다)
class TeamPickerButton extends ConsumerWidget {
  const TeamPickerButton({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final teams = ref.watch(teamListProvider);
    final active = ref.watch(activeTeamIndexProvider).clamp(0, teams.length - 1);
    return PopupMenuButton<int>(
      tooltip: tr('사용할 팀 선택'),
      position: PopupMenuPosition.under,
      color: cs.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      onSelected: (i) => ref.read(teamProvider.notifier).select(i),
      itemBuilder: (_) => [
        for (var i = 0; i < teams.length; i++)
          PopupMenuItem(
              value: i,
              height: 46,
              child: Row(children: [
                SizedBox(
                    width: 96,
                    child: Text(teams[i].name,
                        style: TextStyle(
                            fontSize: 13.5,
                            fontWeight: i == active ? FontWeight.w700 : FontWeight.w500,
                            color: i == active ? cs.primary : null),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis)),
                for (final s in teams[i].sprites) Sprite(s, size: 24),
              ])),
      ],
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 7, 8, 7),
        decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(9)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(teams[active].name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
          const SizedBox(width: 2),
          LabIcon(LabGlyph.down, size: 18, color: cs.onSurfaceVariant),
        ]),
      ),
    );
  }
}

/// '전체' + 항목 목록에서 하나를 고르는 필터 드롭다운
class FilterDropdown extends StatelessWidget {
  final String? value;
  final String allLabel;
  final Map<String, String> labels;
  final ValueChanged<String?> onChanged;
  const FilterDropdown(
      {super.key, required this.value, required this.labels, required this.onChanged, this.allLabel = '전체'});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return PopupMenuButton<String>(
      tooltip: '',
      position: PopupMenuPosition.under,
      color: cs.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      constraints: const BoxConstraints(maxHeight: 420),
      onSelected: (v) => onChanged(v.isEmpty ? null : v),
      itemBuilder: (_) => [
        PopupMenuItem(value: '', height: 38, child: Text(allLabel, style: const TextStyle(fontSize: 13.5))),
        for (final e in labels.entries)
          PopupMenuItem(value: e.key, height: 38, child: Text(e.value, style: const TextStyle(fontSize: 13.5))),
      ],
      child: Container(
        height: 40,
        padding: const EdgeInsets.fromLTRB(12, 0, 8, 0),
        decoration: BoxDecoration(
            color: value == null ? cs.surfaceContainer : cs.primary.withOpacity(.16),
            borderRadius: BorderRadius.circular(10)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(value == null ? allLabel : labels[value] ?? value!,
              style: TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w600, color: value == null ? cs.onSurface : cs.primary)),
          const SizedBox(width: 2),
          LabIcon(LabGlyph.down, size: 18, color: cs.onSurfaceVariant),
        ]),
      ),
    );
  }
}
