import 'package:flutter/material.dart' hide Text, Tooltip;

import '../lab_icons.dart';
import '../api.dart';
import '../widgets.dart';
import '../i18n.dart';

String monName(Json mon) => (mon['ko'] ?? mon['name']) as String;

const _examples = {
  '비': [
    'pelipper',
    'archaludon',
    'swampert',
    'basculegion',
    'incineroar',
    'rillaboom'
  ],
  '쾌청': [
    'charizard',
    'venusaur',
    'sneasler',
    'garchomp',
    'incineroar',
    'whimsicott'
  ],
  '사이코필드 · 트릭룸': [
    'indeedeef',
    'armarouge',
    'hatterene',
    'farigiraf',
    'torkoal',
    'kingambit'
  ],
  '순풍': [
    'whimsicott',
    'garchomp',
    'gholdengo',
    'sneasler',
    'charizard',
    'incineroar'
  ],
};

Future<List<Json>?> pickOpponents(BuildContext context, List<Json> mons,
        List<Json> current, String format) =>
    showDialog<List<Json>>(
      context: context,
      builder: (_) =>
          _OpponentPicker(mons: mons, current: current, format: format),
    );

class _OpponentPicker extends StatefulWidget {
  const _OpponentPicker(
      {required this.mons, required this.current, required this.format});
  final List<Json> mons;
  final List<Json> current;
  final String format;

  @override
  State<_OpponentPicker> createState() => _OpponentPickerState();
}

class _OpponentPickerState extends State<_OpponentPicker> {
  final search = TextEditingController();
  final focus = FocusNode();
  late List<Json> selected = [...widget.current];
  String? message;

  String _normalize(String s) =>
      s.toLowerCase().replaceAll(RegExp(r"[\s_'’().-]"), '');
  Iterable<String> _keys(Json p) =>
      [p['id'], p['name'], p['ko']].whereType<String>().map(_normalize);

  List<Json> _matches() {
    final q = _normalize(search.text);
    final selectedIds = selected.map((p) => p['id']).toSet();
    final found = widget.mons
        .where((p) =>
            !selectedIds.contains(p['id']) &&
            (q.isEmpty || _keys(p).any((k) => k.contains(q))))
        .toList();
    int rank(Json p) => (p['ranks']?[widget.format] as int?) ?? 999;
    found.sort((a, b) {
      if (q.isNotEmpty && _keys(a).contains(q) != _keys(b).contains(q)) {
        return _keys(a).contains(q) ? -1 : 1;
      }
      return rank(a).compareTo(rank(b));
    });
    return found.take(24).toList();
  }

  void _pick(Json mon) {
    if (selected.length >= 6 || selected.any((p) => p['id'] == mon['id'])) return;
    setState(() {
      selected = [...selected, mon];
      search.clear();
      message = null;
    });
    focus.requestFocus();
  }

  Future<void> _paste() async {
    final entered = await showDialog<String>(
      context: context,
      builder: (_) => const _NamesDialog(),
    );
    if (entered == null || !mounted) return;
    final names = entered
        .split(RegExp(r'[,;\n\r]+'))
        .map((s) => s.split('@').first.trim())
        .where((s) => s.isNotEmpty);
    final added = <Json>[];
    final missing = <String>[];
    for (final n in names) {
      final matches =
          widget.mons.where((p) => _keys(p).contains(_normalize(n))).toList();
      if (matches.length == 1) {
        if (!added.any((p) => p['id'] == matches.first['id'])) {
          added.add(matches.first);
        }
      } else {
        missing.add(n);
      }
    }
    setState(() {
      if (added.isNotEmpty) selected = added.take(6).toList();
      message = [
        if (added.length > 6) '앞의 6마리만 넣었습니다.',
        if (missing.isNotEmpty) '이름을 확인해 주세요 · ${missing.take(4).join(', ')}',
        if (added.isEmpty && missing.isEmpty) '입력된 이름이 없습니다.',
      ].join(' ');
    });
  }

  @override
  void dispose() {
    search.dispose();
    focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final results = _matches();
    final available = {for (final p in widget.mons) p['id']: p};
    return AlertDialog(
      title: Text('상대 포켓몬 빠른 입력 · ${selected.length}/6'),
      content: SizedBox(
        width: 520,
        height: 480,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          TextField(
            autofocus: true,
            controller: search,
            focusNode: focus,
            decoration: InputDecoration(
                prefixIcon: LabIcon(LabGlyph.search),
                hintText: tr('한글·영문 이름 · Enter로 첫 결과 추가')),
            onChanged: (_) => setState(() => message = null),
            onSubmitted: (_) {
              if (search.text.trim().isNotEmpty && results.isNotEmpty) {
                _pick(results.first);
              }
              focus.requestFocus();
            },
          ),
          const SizedBox(height: 6),
          if (selected.isNotEmpty)
            Wrap(spacing: 5, runSpacing: 2, children: [
              for (final p in selected)
                InputChip(
                  deleteIcon: const LabIcon(LabGlyph.cross, size: 15),
                  label: Text(monName(p)),
                  visualDensity: VisualDensity.compact,
                  onDeleted: () => setState(() => selected =
                      selected.where((m) => m['id'] != p['id']).toList()),
                ),
            ]),
          if (widget.format == 'Doubles')
            Wrap(spacing: 6, runSpacing: 2, children: [
              for (final entry in _examples.entries)
                if (entry.value.every(available.containsKey))
                  ActionChip(
                    label: Text('${entry.key} 연습'),
                    visualDensity: VisualDensity.compact,
                    onPressed: () => setState(() {
                      selected = [for (final id in entry.value) available[id]!];
                      message = '연습용 상대 조합을 넣었습니다.';
                    }),
                  ),
            ]),
          if (message?.isNotEmpty == true) Text(message!),
          Expanded(
            child: results.isEmpty
                ? const Center(child: Text('검색 결과가 없습니다.'))
                : ListView.builder(
                    itemCount: results.length,
                    itemBuilder: (context, index) {
                      final p = results[index];
                      return ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: Sprite(p['sprite'] as String, size: 32),
                        title: Text(monName(p)),
                        subtitle: Text(p['name'] as String),
                        onTap: selected.length < 6 ? () => _pick(p) : null,
                      );
                    },
                  ),
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: _paste, child: const Text('이름 붙여넣기')),
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('취소')),
        FilledButton(
            onPressed: () => Navigator.pop(context, selected),
            child: const Text('입력 완료')),
      ],
    );
  }
}

class _NamesDialog extends StatefulWidget {
  const _NamesDialog();
  @override
  State<_NamesDialog> createState() => _NamesDialogState();
}

class _NamesDialogState extends State<_NamesDialog> {
  final text = TextEditingController();
  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('포켓몬 이름 붙여넣기'),
        content: TextField(
          autofocus: true,
          controller: text,
          minLines: 4,
          maxLines: 6,
          decoration: InputDecoration(hintText: tr('이름을 줄바꿈 또는 쉼표로 구분하세요')),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context), child: const Text('취소')),
          FilledButton(
              onPressed: () => Navigator.pop(context, text.text),
              child: const Text('입력')),
        ],
      );
}

class DoublesBriefing extends StatefulWidget {
  const DoublesBriefing(
      {super.key, required this.recommendation, required this.onLock});
  final Json recommendation;
  final ValueChanged<List<String>> onLock;

  @override
  State<DoublesBriefing> createState() => _DoublesBriefingState();
}

class _DoublesBriefingState extends State<DoublesBriefing> {
  int index = 0;

  List<String> _lineup(Json pick) => [
        for (final key in ['lead', 'back'])
          for (final m in (pick[key] as List).cast<Json>()) m['id'] as String,
      ];

  Widget _group(String title, List mons) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          Wrap(spacing: 5, runSpacing: 4, children: [
            for (final m in mons.cast<Json>()) MonPill(m),
            if (mons.isEmpty) const Text('후보 없음'),
          ]),
        ],
      );

  @override
  Widget build(BuildContext context) {
    final r = widget.recommendation;
    final plans = (r['plans'] as List).cast<Json>();
    final current = plans[index.clamp(0, plans.length - 1)];
    final locked = r['locked'] == true;
    return Column(children: [
      Section(
        locked ? '고정한 내 선출' : '추천 선출 · 2선봉 + 2후발',
        subtitle: locked
            ? '선출은 고정하고 상대가 보여 준 선봉에 맞춰 대응만 다시 계산합니다.'
            : '예상 선봉 여러 조합에서 크게 불리해지지 않는 조합을 우선합니다. 점수는 상대 비교용입니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 22, runSpacing: 12, children: [
            _group('선봉', r['lead'] as List),
            _group('후발', r['back'] as List),
          ]),
          const SizedBox(height: 8),
          Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text('상성 점수 ${r['score']} · 가장 까다로운 후보 ${r['floor']}'),
                OutlinedButton.icon(
                  onPressed: () => widget.onLock(locked ? [] : _lineup(r)),
                  icon: LabIcon(locked ? LabGlyph.unlock : LabGlyph.lock,
                      size: 16),
                  label: Text(locked ? '고정 해제' : '이 선출 고정'),
                ),
              ]),
          if ((r['alternatives'] as List).isNotEmpty)
            LabExpansionTile(
              tilePadding: EdgeInsets.zero,
              title: const Text('대안 선출 비교'),
              children: [
                for (final alt in (r['alternatives'] as List).cast<Json>())
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                        '${alt['label']} · ${(alt['lead'] as List).cast<Json>().map(monName).join(' + ')}'),
                    subtitle: Text(
                        '후발 ${(alt['back'] as List).cast<Json>().map(monName).join(' + ')} · 상성 ${alt['score']} · 낮은 시나리오 ${alt['floor']}'),
                    trailing: TextButton(
                        onPressed: () => widget.onLock(_lineup(alt)),
                        child: const Text('선택')),
                  ),
              ],
            ),
        ]),
      ),
      Section(
        '상대 선출 예상과 이론상 첫 턴',
        subtitle: '선봉·후발은 조합과 채용 통계로 추정합니다. 게임에서 확인한 선봉은 직접 선택할 수 있습니다.',
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 6, runSpacing: 4, children: [
            for (final (i, p) in plans.indexed)
              ChoiceChip(
                selected: identical(p, current),
                label: Text(
                    '${p['confirmed'] == true ? '확인' : '후보 ${i + (plans.first['confirmed'] == true ? 0 : 1)}'} · '
                    '${(p['enemyLead'] as List).cast<Json>().map(monName).join(' + ')}'),
                onSelected: (_) => setState(() => index = i),
              ),
          ]),
          const SizedBox(height: 12),
          Wrap(spacing: 22, runSpacing: 10, children: [
            _group(current['confirmed'] == true ? '확인한 선봉' : '예상 선봉',
                current['enemyLead'] as List),
            _group('예상 후발', current['enemyBack'] as List),
          ]),
          const SizedBox(height: 12),
          _PlanDetail(current),
        ]),
      ),
    ]);
  }
}

class _PlanDetail extends StatelessWidget {
  const _PlanDetail(this.plan);
  final Json plan;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final swap = plan['switch'] as Json?;
    final field = {...(plan['field'] as List), ...(plan['strategies'] as List)};
    final actions = (plan['actions'] as List).cast<Json>();
    final risks = (plan['risks'] as List).cast<Json>();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (field.isNotEmpty)
        Text(field.join(' · '), style: TextStyle(color: cs.primary)),
      Text('첫 턴 목표 · ${plan['goal']} · ${monName(plan['focus'] as Json)}',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 6),
      if (swap != null)
        Text(
            '교체 · ${monName(swap['out'] as Json)} → ${monName(swap['in'] as Json)} · 예상 최대 ${fmtPct(swap['takenPct'] as num)}'),
      for (final a in actions)
        Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text([
            '${monName(a['mon'] as Json)} → ${a['moveKo']}',
            if (a['target'] != null) monName(a['target'] as Json),
            if (a['pct'] != null) '예상 ${fmtPct(a['pct'] as num)}',
            if (a['spread'] == true) '전체기',
            if (a['allyPct'] != null) '아군 ${fmtPct(a['allyPct'] as num)}',
            if (a['reason'] != null) a['reason'],
          ].join(' · ')),
        ),
      if (actions.isEmpty && swap == null)
        const Text('안전한 첫 행동 후보를 찾기 어렵습니다. 상대 기술을 확인해 주세요.'),
      if (risks.isNotEmpty)
        for (final risk in risks.take(2))
          Text(
              '주의 · ${monName(risk['from'] as Json)}의 ${risk['moveKo'] ?? risk['move']} → '
              '${monName(risk['to'] as Json)} ${fmtPct(risk['pct'] as num)}',
              style: TextStyle(color: cs.error)),
      const SizedBox(height: 6),
      Text('후반 · ${plan['finish']}',
          style: Theme.of(context).textTheme.labelLarge),
      LabExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('스피드와 변수'),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        expandedAlignment: Alignment.centerLeft,
        children: [
          const Text('동일 우선도 기준 예상 스피드. 숨은 세트·동속·필드 변화에 따라 달라집니다.'),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 4, children: [
            for (final p in (plan['pace'] as List).cast<Json>())
              Chip(
                  label: Text(
                      '${p['side'] == 'mine' ? '내' : '상대'} ${monName(p['mon'] as Json)} ${p['speed']}')),
          ]),
          for (final caution in plan['cautions'] as List) Text('• $caution'),
        ],
      ),
    ]);
  }
}
