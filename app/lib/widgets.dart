import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'lab_icons.dart';
import 'api.dart';
import 'i18n.dart';

const typeKo = {
  'Normal': '노말', 'Fire': '불꽃', 'Water': '물', 'Electric': '전기', 'Grass': '풀', 'Ice': '얼음',
  'Fighting': '격투', 'Poison': '독', 'Ground': '땅', 'Flying': '비행', 'Psychic': '에스퍼', 'Bug': '벌레',
  'Rock': '바위', 'Ghost': '고스트', 'Dragon': '드래곤', 'Dark': '악', 'Steel': '강철', 'Fairy': '페어리',
};
const typeColor = {
  'Normal': Color(0xFF9FA19F), 'Fire': Color(0xFFE62829), 'Water': Color(0xFF2980EF),
  'Electric': Color(0xFFE0B000), 'Grass': Color(0xFF3FA129), 'Ice': Color(0xFF3DBFD9),
  'Fighting': Color(0xFFE08A00), 'Poison': Color(0xFF9141CB), 'Ground': Color(0xFF915121),
  'Flying': Color(0xFF6FA8E0), 'Psychic': Color(0xFFEF4179), 'Bug': Color(0xFF91A119),
  'Rock': Color(0xFFAFA981), 'Ghost': Color(0xFF704170), 'Dragon': Color(0xFF5060E1),
  'Dark': Color(0xFF624D4E), 'Steel': Color(0xFF60A1B8), 'Fairy': Color(0xFFEF70EF),
};
const statKeys = ['hp', 'atk', 'def', 'spa', 'spd', 'spe'];
const statKo = {'hp': 'HP', 'atk': '공격', 'def': '방어', 'spa': '특공', 'spd': '특방', 'spe': '스피드'};
const categoryKo = {'Physical': '물리', 'Special': '특수', 'Status': '변화'};

/// 성격 -> (상승, 하락)
const natureEffects = <String, List<String?>>{
  'Hardy': [null, null], 'Docile': [null, null], 'Serious': [null, null], 'Bashful': [null, null],
  'Quirky': [null, null], 'Lonely': ['atk', 'def'], 'Brave': ['atk', 'spe'], 'Adamant': ['atk', 'spa'],
  'Naughty': ['atk', 'spd'], 'Bold': ['def', 'atk'], 'Relaxed': ['def', 'spe'], 'Impish': ['def', 'spa'],
  'Lax': ['def', 'spd'], 'Timid': ['spe', 'atk'], 'Hasty': ['spe', 'def'], 'Jolly': ['spe', 'spa'],
  'Naive': ['spe', 'spd'], 'Modest': ['spa', 'atk'], 'Mild': ['spa', 'def'], 'Quiet': ['spa', 'spe'],
  'Rash': ['spa', 'spd'], 'Calm': ['spd', 'atk'], 'Gentle': ['spd', 'def'], 'Sassy': ['spd', 'spe'],
  'Careful': ['spd', 'spa'],
};

String natureLabel(String name, String? ko) {
  final e = natureEffects[name];
  final fx = e == null || e[0] == null ? tr('보정 없음') : '${tr(statKo[e[0]]!)}↑ ${tr(statKo[e[1]]!)}↓';
  final local = ko ?? name;
  return local == name || !showEnglishNames ? '$local · $fx' : '$local ($name) · $fx';
}

String fmtPct(num? v) => v == null ? '' : '${v.toStringAsFixed(v >= 10 || v == v.roundToDouble() ? 0 : 1)}%';

class Sprite extends StatelessWidget {
  final String name;
  final double size;
  const Sprite(this.name, {super.key, this.size = 48});
  @override
  Widget build(BuildContext context) => Image.network(spriteUrl(name),
      width: size,
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      errorBuilder: (_, __, ___) =>
          SizedBox(width: size, height: size, child: LabIcon(LabGlyph.ball, size: size * .6)));
}

class SpriteBadge extends StatelessWidget {
  const SpriteBadge(this.name, {super.key, required this.type, this.size = 56});
  final String name;
  final String? type;
  final double size;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tone = typeColor[type] ?? cs.primary;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        gradient: RadialGradient(colors: [tone.withOpacity(.23), cs.surfaceContainer]),
        border: Border.all(color: tone.withOpacity(.28)),
        borderRadius: BorderRadius.circular(size * .23),
      ),
      child: Center(child: Sprite(name, size: size * .88)),
    );
  }
}

class ItemIcon extends StatelessWidget {
  final String? name;
  final double size;
  const ItemIcon(this.name, {super.key, this.size = 22});
  @override
  Widget build(BuildContext context) => name == null
      ? SizedBox(width: size, height: size)
      : Image.network(itemUrl(name!),
          width: size,
          height: size,
          errorBuilder: (_, __, ___) =>
              SizedBox(width: size, height: size, child: LabIcon(LabGlyph.box, size: size * .8)));
}

class TypeChip extends StatelessWidget {
  final String type;
  final bool dense;
  const TypeChip(this.type, {super.key, this.dense = false});
  @override
  Widget build(BuildContext context) {
    final base = typeColor[type] ?? Colors.grey;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final ink = Color.lerp(base, dark ? Colors.white : const Color(0xFF091429), dark ? .49 : .43)!;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: dense ? 6 : 9, vertical: dense ? 2 : 3),
      decoration: BoxDecoration(
        color: base.withOpacity(dark ? .16 : .13),
        border: Border.all(color: base.withOpacity(dark ? .35 : .22)),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(typeKo[type] ?? type,
          style: TextStyle(color: ink, fontSize: dense ? 11 : 12.5, fontWeight: FontWeight.w600, height: 1.2)),
    );
  }
}

/// 타입 색 점 (기술 옆에 붙는 작은 표시)
class TypeDot extends StatelessWidget {
  final String? type;
  const TypeDot(this.type, {super.key});
  @override
  Widget build(BuildContext context) => Tooltip(
        message: typeKo[type] ?? '',
        child: Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(
              color: typeColor[type] ?? Theme.of(context).colorScheme.outline, shape: BoxShape.circle),
        ),
      );
}

class TypeRow extends StatelessWidget {
  final List types;
  final bool dense;
  const TypeRow(this.types, {super.key, this.dense = false});
  @override
  Widget build(BuildContext context) =>
      Wrap(spacing: 3, runSpacing: 2, children: [for (final t in types) TypeChip(t as String, dense: dense)]);
}

/// 한글 이름(크게) + 영문 이름(작게)
class NameBlock extends StatelessWidget {
  final String? ko;
  final String name;
  final double size;
  final CrossAxisAlignment align;
  const NameBlock(this.ko, this.name, {super.key, this.size = 14.5, this.align = CrossAxisAlignment.start});
  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Column(crossAxisAlignment: align, mainAxisSize: MainAxisSize.min, children: [
      Text(ko ?? name,
          style: TextStyle(fontSize: size, fontWeight: FontWeight.w600, height: 1.25),
          maxLines: 1,
          overflow: TextOverflow.ellipsis),
      if (ko != null && ko != name && showEnglishNames)
        Text(name,
            style: TextStyle(fontSize: size < 14 ? 12 : size * .82, color: muted, height: 1.3),
            maxLines: 1,
            overflow: TextOverflow.ellipsis),
    ]);
  }
}

/// 기술 칩: 타입 점 + 한글 이름 (영문은 툴팁)
class MoveChip extends StatelessWidget {
  final String name;
  final String? ko;
  final String? type;
  final bool expand;
  const MoveChip(this.name, {super.key, this.ko, this.type, this.expand = false});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final label =
        Text(ko ?? name, style: const TextStyle(fontSize: 13, height: 1.2), maxLines: 1, overflow: TextOverflow.ellipsis);
    return Tooltip(
      message: name,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
        decoration: BoxDecoration(color: cs.surfaceContainer, borderRadius: BorderRadius.circular(8)),
        child: Row(mainAxisSize: expand ? MainAxisSize.max : MainAxisSize.min, children: [
          TypeDot(type),
          const SizedBox(width: 7),
          expand ? Expanded(child: label) : Flexible(child: label),
        ]),
      ),
    );
  }
}

class Section extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget child;
  final Widget? trailing;
  const Section(this.title, {super.key, this.subtitle, required this.child, this.trailing});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            Container(
              width: 3, height: 19,
              decoration: BoxDecoration(
                color: cs.primary.withOpacity(.78), borderRadius: BorderRadius.circular(2)),
            ),
            const SizedBox(width: 9),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, letterSpacing: -.2)),
                if (subtitle != null) ...[
                  const SizedBox(height: 3),
                  Text(subtitle!, style: TextStyle(fontSize: 12.5, color: cs.onSurfaceVariant, height: 1.35)),
                ],
              ]),
            ),
            if (trailing != null) ...[const SizedBox(width: 12), trailing!],
          ]),
          const SizedBox(height: 16),
          child,
        ]),
      ),
    );
  }
}

/// 이름 + 퍼센트 + 막대
class UsageBar extends StatelessWidget {
  final Widget leading;
  final num? pct;
  final Color? color;
  const UsageBar({super.key, required this.leading, this.pct, this.color});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Stack(children: [
        if (pct != null)
          Positioned.fill(
            child: FractionallySizedBox(
              alignment: Alignment.centerLeft,
              widthFactor: (pct! / 100).clamp(0.0, 1.0).toDouble(),
              child: DecoratedBox(
                  decoration:
                      BoxDecoration(color: cs.primary.withOpacity(.13), borderRadius: BorderRadius.circular(7))),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 7),
          child: Row(children: [
            Expanded(child: leading),
            if (pct != null)
              Text(fmtPct(pct),
                  style: const TextStyle(
                      fontWeight: FontWeight.w600, fontSize: 13, fontFeatures: [FontFeature.tabularFigures()])),
          ]),
        ),
      ]),
    );
  }
}

class Stars extends StatelessWidget {
  final int n;
  const Stars(this.n, {super.key});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 0; i < 5; i++)
        LabIcon(i < n ? LabGlyph.starFill : LabGlyph.star,
            size: 18, color: i < n ? Colors.amber : cs.outlineVariant),
    ]);
  }
}

/// 스프라이트 + 이름이 들어간 작은 포켓몬 버튼
class MonPill extends StatelessWidget {
  final Json mon;
  final String? caption;
  final VoidCallback? onTap;
  const MonPill(this.mon, {super.key, this.caption, this.onTap});
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Material(
      color: cs.surfaceContainer,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(6, 5, 12, 5),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Sprite(mon['sprite'] as String, size: 36),
            const SizedBox(width: 8),
            Flexible(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              Text((mon['ko'] ?? mon['name']) as String,
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, height: 1.25)),
              Text(caption ?? mon['name'] as String,
                  style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant, height: 1.3)),
            ])),
          ]),
        ),
      ),
    );
  }
}

class LabExpansionTile extends StatefulWidget {
  const LabExpansionTile({
    super.key, required this.title, required this.children, this.subtitle, this.leading,
    this.tilePadding, this.childrenPadding, this.expandedAlignment, this.expandedCrossAxisAlignment,
    this.initiallyExpanded = false,
  });
  final Widget title;
  final List<Widget> children;
  final Widget? subtitle;
  final Widget? leading;
  final EdgeInsetsGeometry? tilePadding;
  final EdgeInsetsGeometry? childrenPadding;
  final Alignment? expandedAlignment;
  final CrossAxisAlignment? expandedCrossAxisAlignment;
  final bool initiallyExpanded;

  @override
  State<LabExpansionTile> createState() => _LabExpansionTileState();
}

class _LabExpansionTileState extends State<LabExpansionTile> {
  late bool expanded = widget.initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final reduced = MediaQuery.disableAnimationsOf(context);
    return ExpansionTile(
      title: widget.title,
      subtitle: widget.subtitle,
      leading: widget.leading,
      tilePadding: widget.tilePadding,
      childrenPadding: widget.childrenPadding,
      expandedAlignment: widget.expandedAlignment,
      expandedCrossAxisAlignment: widget.expandedCrossAxisAlignment,
      initiallyExpanded: widget.initiallyExpanded,
      onExpansionChanged: (value) => setState(() => expanded = value),
      expansionAnimationStyle: reduced ? AnimationStyle.noAnimation : null,
      trailing: AnimatedRotation(
        turns: expanded ? .5 : 0,
        duration: reduced ? Duration.zero : const Duration(milliseconds: 180),
        child: const LabIcon(LabGlyph.down, size: 18),
      ),
      children: widget.children,
    );
  }
}

class PickItem<T> {
  final T value;
  final String title;
  final String? subtitle;
  final Widget? leading;
  final String? trailing;
  final String? group;
  const PickItem(this.value, this.title, {this.subtitle, this.leading, this.trailing, this.group});
}

/// 검색 가능한 선택 다이얼로그 (한글/영문 모두 검색)
Future<T?> showPicker<T>(BuildContext context, String title, List<PickItem<T>> items) {
  return showDialog<T>(
    context: context,
    builder: (context) {
      var q = '';
      return StatefulBuilder(builder: (context, setState) {
        final filtered = q.isEmpty
            ? items
            : items
                .where((i) =>
                    i.title.toLowerCase().contains(q) || (i.subtitle ?? '').toLowerCase().contains(q))
                .toList();
        return AlertDialog(
          title: Text(title),
          contentPadding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          content: SizedBox(
            width: 440,
            height: 520,
            child: Column(children: [
              TextField(
                autofocus: true,
                decoration: InputDecoration(
                    prefixIcon: LabIcon(LabGlyph.search), hintText: tr('이름으로 검색 (한글/영문)'), isDense: true),
                onChanged: (v) => setState(() => q = v.trim().toLowerCase()),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (context, i) {
                    final it = filtered[i];
                    final header = it.group != null && (i == 0 || filtered[i - 1].group != it.group);
                    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      if (header)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(8, 10, 8, 2),
                          child: Text(it.group!,
                              style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: Theme.of(context).colorScheme.primary)),
                        ),
                      ListTile(
                        dense: true,
                        leading: it.leading,
                        title: Text(it.title),
                        subtitle: it.subtitle == null ? null : Text(it.subtitle!),
                        trailing: it.trailing == null ? null : Text(it.trailing!),
                        onTap: () => Navigator.pop(context, it.value),
                      ),
                    ]);
                  },
                ),
              ),
            ]),
          ),
          actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('닫기'))],
        );
      });
    },
  );
}

/// 포켓몬 선택 다이얼로그: 스프라이트 그리드 + 검색
Future<Json?> showPokemonPicker(BuildContext context, List<Json> all, String fmt) {
  final sorted = [...all]..sort((a, b) =>
      ((a['ranks'][fmt] ?? 999) as int).compareTo((b['ranks'][fmt] ?? 999) as int));
  return showDialog<Json>(
    context: context,
    builder: (context) {
      var q = '';
      return StatefulBuilder(builder: (context, setState) {
        final list = q.isEmpty
            ? sorted
            : sorted
                .where((p) =>
                    (p['name'] as String).toLowerCase().contains(q) || ((p['ko'] ?? '') as String).contains(q))
                .toList();
        return AlertDialog(
          title: const Text('포켓몬 선택'),
          contentPadding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          content: SizedBox(
            width: 640,
            height: 560,
            child: Column(children: [
              TextField(
                autofocus: true,
                decoration: InputDecoration(
                    prefixIcon: LabIcon(LabGlyph.search), hintText: tr('이름으로 검색 (한글/영문)'), isDense: true),
                onChanged: (v) => setState(() => q = v.trim().toLowerCase()),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: GridView.builder(
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: 104, mainAxisExtent: 104, crossAxisSpacing: 4, mainAxisSpacing: 4),
                  itemCount: list.length,
                  itemBuilder: (context, i) {
                    final p = list[i];
                    final rank = p['ranks'][fmt];
                    return InkWell(
                      borderRadius: BorderRadius.circular(8),
                      onTap: () => Navigator.pop(context, p),
                      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                        Sprite(p['sprite'] as String, size: 52),
                        Text((p['ko'] ?? p['name']) as String,
                            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                        Text('${rank == null ? '' : '#$rank '}${p['name']}',
                            style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                      ]),
                    );
                  },
                ),
              ),
            ]),
          ),
          actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('닫기'))],
        );
      });
    },
  );
}

/// 로딩/오류 공통 처리
class AsyncView<T> extends StatelessWidget {
  final AsyncValue<T> value;
  final Widget Function(T) builder;
  final VoidCallback? onRetry;
  const AsyncView(this.value, this.builder, {super.key, this.onRetry});
  @override
  Widget build(BuildContext context) => value.when(
        skipLoadingOnReload: true,
        data: builder,
        loading: () => const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator())),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const LabIcon(LabGlyph.cloud, size: 40),
              const SizedBox(height: 8),
              Text('서버에 연결하지 못했습니다 ($apiBase)\n백엔드가 실행 중인지 확인하세요.', textAlign: TextAlign.center),
              if (onRetry != null) TextButton(onPressed: onRetry, child: const Text('다시 시도')),
            ]),
          ),
        ),
      );
}
