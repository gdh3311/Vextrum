import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:shared_preferences/shared_preferences.dart';

import 'lab_icons.dart';
import 'settings.dart';
import 'widgets.dart';
import 'i18n.dart';

const _seenKey = 'last_read_app_update';

const _releases = [
  (
    version: appVersion,
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.bolt,
        title: '챔피언스 실제 규칙으로 바뀐 배틀',
        detail: '화상·마비·잠듦·독·얼음을 챔피언스 수치(마비 12.5%, 잠듦 최대 2턴, 급소 1/24)로 계산하고, 벽·설치 기술·대타·앙코르·하품 등 실전 보조기와 바뀐 기술 위력을 반영합니다. 메가스톤이 잘못 연결된 11마리도 바로잡았습니다.',
      ),
      (
        glyph: LabGlyph.controller,
        title: '진짜 게임 같은 배틀 화면',
        detail: '타입 색 기술 이펙트, 급소·효과 굉장 시 화면 흔들림, 비·쾌청·모래바람·눈과 필드 연출, 몬스터볼 등장과 메가진화 연출, 상태 이상·능력 변화 표시, 한 글자씩 나오는 메시지 창을 더했습니다.',
      ),
    ],
  ),
  (
    version: '1.4.0',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.crystal,
        title: '실전 플레이어 수준의 챔피언 CPU',
        detail: '내 행동을 예측하고 2턴 앞까지 내다보며, 막혔을 때의 최악의 경우까지 따집니다. 같은 팀끼리 붙였을 때 표준 CPU를 상대로 81% 승리합니다.',
      ),
      (
        glyph: LabGlyph.team,
        title: '더 자세한 팀 자동 구성과 시뮬레이션',
        detail: '평가 깊이와 검증 CPU를 고를 수 있고, 후보 비교표, 팀 분석, 포켓몬별 활약·선봉 조합 승률·위협적인 상대·승률 신뢰 구간을 보여 줍니다.',
      ),
    ],
  ),
  (
    version: '1.3.0',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.controller,
        title: '게임처럼 진행되는 가상 배틀',
        detail: '원근감 있는 경기장, 이름표와 HP 바, 메시지 창에서 한 턴의 행동이 차례로 재생됩니다. 기술은 타입 색 버튼으로 고르고 대상마다 상성이 표시됩니다.',
      ),
      (
        glyph: LabGlyph.bolt,
        title: '스피드 티어 · PokePaste',
        detail: '메타 상위권의 실전 스피드와 내 팀을 한 줄에 놓고 비교합니다. 팀 가져오기에 pokepast.es 링크를 붙여 넣을 수 있습니다.',
      ),
    ],
  ),
  (
    version: '1.2.1',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.swap,
        title: '가상 배틀 교체 전술',
        detail: '유턴이나 막말내뱉기 뒤 교체할 포켓몬을 고를 수 있습니다. CPU도 상성과 특성을 보고 교체합니다.',
      ),
      (
        glyph: LabGlyph.bolt,
        title: '선공기와 특성',
        detail: '기습의 성공 조건과 그래스슬라이더의 우선도, 위협·재생력·피뢰침 등의 효과를 반영합니다.',
      ),
    ],
  ),
  (
    version: '1.2.0',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.spark,
        title: '설정 화면',
        detail: '언어, 테마, 글자 크기, 서버 주소, 데이터 갱신을 한곳에서 바꿀 수 있습니다.',
      ),
      (
        glyph: LabGlyph.meta,
        title: 'English · 日本語 지원',
        detail: '앱 화면과 포켓몬·기술·도구 이름을 영어와 일본어로 볼 수 있습니다.',
      ),
    ],
  ),
  (
    version: '1.1.0',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.archive,
        title: '공식 시즌 M8과 M-C 규정',
        detail: '메타에서 새 영입 라인업과 메가진화를 볼 수 있습니다. 랭킹에는 통계를 수집한 시즌이 표시됩니다.',
      ),
      (
        glyph: LabGlyph.controller,
        title: '마스터볼·챔피언 CPU',
        detail: '더블배틀에서 상대의 예상 행동을 바탕으로 집중 공격, 방어, 교체 조합을 비교합니다.',
      ),
      (
        glyph: LabGlyph.spark,
        title: '교체할 수 있는 경기장 테마',
        detail: '메타 화면의 화살표로 야간, 빗속, 결승전 경기장을 둘러보세요.',
      ),
    ],
  ),
  (
    version: '1.0.0',
    date: '2026.11.11',
    entries: [
      (
        glyph: LabGlyph.team,
        title: '팀 빌더와 자동 파티',
        detail: '포켓몬과 선호 전략을 고르고, 후보 파티의 시뮬레이션 결과를 비교할 수 있습니다.',
      ),
      (
        glyph: LabGlyph.versus,
        title: '실전 상대 분석과 가상 배틀',
        detail: '선출을 비교하고 직접 배틀하거나 반복 시뮬레이션으로 팀의 강점과 약점을 살펴보세요.',
      ),
    ],
  ),
];

class UpdatesButton extends StatefulWidget {
  const UpdatesButton({super.key, this.compact = false});

  final bool compact;

  @override
  State<UpdatesButton> createState() => _UpdatesButtonState();
}

class _UpdatesButtonState extends State<UpdatesButton> {
  bool? _unread;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (mounted && _unread == null) {
        setState(() =>
            _unread = prefs.getString(_seenKey) != _releases.first.version);
      }
    } catch (_) {}
  }

  Future<void> _open() async {
    setState(() => _unread = false);
    await showDialog<void>(
        context: context, builder: (_) => const _UpdatesDialog());
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_seenKey, _releases.first.version);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final unread = _unread == true;
    final glyph = Badge(
      isLabelVisible: unread,
      smallSize: 8,
      backgroundColor: cs.tertiary,
      child: LabIcon(LabGlyph.note, size: 20, color: cs.primary),
    );
    if (widget.compact) {
      return IconButton(
        tooltip: tr(unread ? '새 업데이트 보기' : '업데이트 내역'),
        onPressed: _open,
        icon: glyph,
      );
    }
    return Material(
      color: cs.primary.withOpacity(.07),
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: _open,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
          child: Row(children: [
            glyph,
            const SizedBox(width: 10),
            const Expanded(
                child: Text('업데이트',
                    style: TextStyle(fontWeight: FontWeight.w600))),
            Text('v${_releases.first.version}',
                style: TextStyle(color: cs.onSurfaceVariant, fontSize: 11)),
          ]),
        ),
      ),
    );
  }
}

class _UpdatesDialog extends StatelessWidget {
  const _UpdatesDialog();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final latest = _releases.first;
    return Dialog(
      clipBehavior: Clip.antiAlias,
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Stack(children: [
              Positioned.fill(
                child: Image.asset('assets/arena.jpg',
                    fit: BoxFit.cover,
                    alignment: const Alignment(.85, -.29),
                    excludeFromSemantics: true),
              ),
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(colors: [
                      const Color(0xFF081628),
                      const Color(0xFF081628).withOpacity(.30),
                    ]),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(22, 24, 54, 24),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('v${latest.version}  ·  ${latest.date}',
                          style: const TextStyle(
                              color: Color(0xFFFFD37B),
                              fontWeight: FontWeight.w600)),
                      const SizedBox(height: 4),
                      Semantics(
                        header: true,
                        child: const Text('업데이트 내역',
                            style: TextStyle(
                                color: Colors.white,
                                fontSize: 27,
                                fontWeight: FontWeight.w700)),
                      ),
                    ]),
              ),
              Positioned(
                right: 9,
                top: 8,
                child: IconButton(
                  tooltip: tr('닫기'),
                  color: Colors.white,
                  style: IconButton.styleFrom(
                      backgroundColor: const Color(0xA8142035)),
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const LabIcon(LabGlyph.cross, size: 19),
                ),
              ),
            ]),
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 17),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (final entry in latest.entries)
                        _UpdateEntry(
                            glyph: entry.glyph,
                            title: entry.title,
                            detail: entry.detail),
                      const SizedBox(height: 9),
                      const Divider(),
                      for (final release in _releases.skip(1))
                        LabExpansionTile(
                          tilePadding:
                              const EdgeInsets.symmetric(horizontal: 2),
                          expandedCrossAxisAlignment:
                              CrossAxisAlignment.stretch,
                          title: Text('v${release.version}',
                              style: TextStyle(
                                  color: cs.onSurface,
                                  fontWeight: FontWeight.w600)),
                          subtitle: Text(release.date),
                          children: [
                            for (final entry in release.entries)
                              _UpdateEntry(
                                  glyph: entry.glyph,
                                  title: entry.title,
                                  detail: entry.detail),
                          ],
                        ),
                    ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _UpdateEntry extends StatelessWidget {
  const _UpdateEntry(
      {required this.glyph, required this.title, required this.detail});

  final LabGlyph glyph;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
              color: cs.primaryContainer,
              borderRadius: BorderRadius.circular(10)),
          child: Center(child: LabIcon(glyph, size: 20, color: cs.primary)),
        ),
        const SizedBox(width: 11),
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title,
                style: theme.textTheme.titleSmall
                    ?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(detail, style: theme.textTheme.bodySmall),
          ]),
        ),
      ]),
    );
  }
}
