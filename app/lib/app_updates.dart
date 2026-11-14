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
    date: '2026.11.14',
    entries: [
      (
        glyph: LabGlyph.versus,
        title: '공개 정보로 판단하는 배틀 CPU',
        detail: '마스터볼 이상에서 양쪽 CPU가 같은 판단 엔진으로 공격·방어·교체를 비교합니다. 모의전에서 쓴 선출과 상대 성향을 연습에 가져옵니다.',
      ),
    ],
  ),
  (
    version: '1.17.0',
    date: '2026.11.14',
    entries: [
      (
        glyph: LabGlyph.versus,
        title: '전략 실행 기록과 패배 매치 연습',
        detail: '자동 구성에서 핵심 선출, 전략 발동, 효과 활용을 확인하고 같은 상대와 선출로 다시 연습합니다.',
      ),
    ],
  ),
  (
    version: '1.16.0',
    date: '2026.11.14',
    entries: [
      (
        glyph: LabGlyph.stack,
        title: '팀 워크스페이스',
        detail: '팀을 고치면 규칙·전략·속도·약점·메타 위협 분석이 바로 바뀝니다. 되돌리기, 포켓몬·항목 잠금, 한 자리 교체 추천과 그 이유, 상대 포켓몬·상대 팀 대응, 모의전 실험과 실전 기록 분석을 한 화면에서 이어서 할 수 있습니다.',
      ),
      (
        glyph: LabGlyph.check,
        title: '추천은 모의전으로 확인',
        detail: '교체 후보는 정적 지표로 찾고, 같은 상대·같은 난수의 모의전과 별도 상대군 재검증으로 개선·악화·결론 보류를 판정합니다. 팀을 고치면 이전 결과에는 이전 버전 표시가 붙습니다.',
      ),
    ],
  ),
  (
    version: '1.15.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.book,
        title: '보류 상대 검증과 메가진화 선택',
        detail: '자동 구성 후보를 보류 상대 코어로 평가하고, 직접 배틀에서는 메가진화할 포켓몬과 턴을 선택할 수 있습니다.',
      ),
    ],
  ),
  (
    version: '1.14.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.book,
        title: '선출과 모의전을 연결한 전략 가이드',
        detail: '현재 선출의 기술과 특성으로 대응을 안내합니다. 상대 전략별 선출, 실제 첫 턴 행동과 전적을 보고 같은 상대와 연습할 수 있습니다.',
      ),
    ],
  ),
  (
    version: '1.13.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.swap,
        title: '팀과 선출을 처음부터 함께 탐색',
        detail: '좋은 6마리가 나쁜 선출 때문에 탈락하지 않도록, 탐색 중간에도 선출을 먼저 바꿔 보고 그 계획을 깔고 멤버 교체를 비교합니다. 자동 연구도 이제 팀과 선출 계획을 한 묶음으로 기록합니다.',
      ),
      (
        glyph: LabGlyph.note,
        title: '상대 전략을 확률로 읽기',
        detail: '미리보기 6마리를 순풍·트릭룸 중 하나로 단정하지 않고, 랭커 채용률로 각 전략의 가능성을 계산합니다. 애매하면 두 전략을 함께 대비하는 선출을 따로 검증합니다.',
      ),
      (
        glyph: LabGlyph.spark,
        title: '독창성 다섯 갈래와 데이터 경고',
        detail: '종 구성·세트·운영·새 조합·실전성을 따로 보여 주고, 무엇을 바꿨을 때 나아졌는지(선출·세트·멤버)를 나눠 적습니다. 순위 표본이 공식 시즌보다 오래되면 경고하고, 표본 중 이전 시즌의 랭커 팀은 덜 반영합니다.',
      ),
    ],
  ),
  (
    version: '1.12.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.swap,
        title: '선출까지 함께 최적화',
        detail: '같은 6마리라도 상대 전략(미리보기로 추정)마다 선봉 2·후발 2를 직접 바꿔 보고, 새 상대군에서도 확실히 나아진 선출만 계획으로 채택합니다. 팀을 고치기 전에 선출 문제인지 먼저 가립니다.',
      ),
      (
        glyph: LabGlyph.controller,
        title: '플레이 스타일이 다른 CPU',
        detail: '같은 랭크에서도 공격형·수비형·전개형·피벗형·카운터형 CPU가 서로 다른 판단을 합니다. 마스터볼 리그는 여러 스타일과, 스트레스 리그는 승리 조건을 노리는 카운터형과 싸웁니다.',
      ),
    ],
  ),
  (
    version: '1.11.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.ball,
        title: '랭크별 리그로 검증하는 팀',
        detail: '추천 팀을 몬스터볼·하이퍼볼·마스터볼·챔피언 CPU와 각각 싸워 보고, 가장 약한 상대 전략만 모은 스트레스 리그까지 결과와 95% 범위로 보여 줍니다. 챔피언 리그에서 무너지는 팀은 경고합니다. CPU는 이제 상대의 숨겨진 도구·능력 포인트를 모른 채 판단합니다.',
      ),
      (
        glyph: LabGlyph.note,
        title: '선출 계획과 실제 패배 원인',
        detail: '상대 전략마다 실제 모의전에서 가장 많이 쓴 선봉 2·후발 2와 첫 턴 행동, 그 전적을 보여 줍니다. 진 판은 선제기·광역기·행동 전 기절·트릭룸 대응 실패처럼 배틀에서 실제로 일어난 일로 원인을 적습니다.',
      ),
    ],
  ),
  (
    version: '1.10.0',
    date: '2026.11.13',
    entries: [
      (
        glyph: LabGlyph.book,
        title: '전략부터 짜는 팀 자동 구성 V2',
        detail: '비+순풍, 트릭룸+사이코필드 같은 주·보조 전략 조합부터 초안을 만들고, 결과를 공격형·안정형·변칙형처럼 서로 다른 전략 가족으로 고릅니다. 팀마다 주 승리 조건과 막혔을 때의 계획, 다른 CPU 상대 성적, 쓸 만한 선봉 수, 자주 지는 이유를 보여 줍니다.',
      ),
      (
        glyph: LabGlyph.shield,
        title: '규칙 검증과 데이터 출처',
        detail: '날따름·사이코필드·와이드가드·방음·틀깨기 등 핵심 규칙을 테스트로 고정하고, 방음과 선출 정보(상대의 실제 세트를 미리 보던 문제)를 고쳤습니다. 공식 시즌·레귤레이션과 데이터의 시즌 표기를 따로 보여 줍니다.',
      ),
    ],
  ),
  (
    version: '1.9.0',
    date: '2026.11.12',
    entries: [
      (
        glyph: LabGlyph.spark,
        title: '계속 연구하는 자동 연구',
        detail: '앱 서버가 켜져 있는 동안 팀을 계속 새로 만들고, 한 마리씩 바꾸고, 서로 섞어 매번 새로운 상대와 싸워 봅니다. 성적과 함께 쓴 포켓몬의 시너지가 쌓여 오래 연구할수록 강하고 다양한 팀이 남고, 팀 자동 구성도 여기서 찾은 팀에서 출발합니다. 자동 연구 화면에서 진행 상황과 발견한 팀, 배운 조합을 볼 수 있습니다.',
      ),
    ],
  ),
  (
    version: '1.8.0',
    date: '2026.11.12',
    entries: [
      (
        glyph: LabGlyph.swap,
        title: '모의전으로 파티 멤버 교체',
        detail: '패배한 상대와 전략을 보고 포켓몬을 한두 마리 바꿉니다. 새 상대군에서도 개선된 조합을 남기고, 결과에서 교체 전후 전적을 볼 수 있습니다.',
      ),
      (
        glyph: LabGlyph.star,
        title: '나만의 팀을 만드는 팀 개성',
        detail: '메타 중심·균형·독창적 중에서 고릅니다. 균형은 랭커 파티와 최대 3마리, 독창적은 2마리까지만 겹치게 하고 그 안에서 승률이 가장 높은 팀을 찾습니다. 후보를 여러 에이스에서 훨씬 많이 만든 뒤 짧은 모의전부터 단계적으로 걸러, 다양하면서도 강한 팀이 남습니다.',
      ),
      (
        glyph: LabGlyph.ball,
        title: '실전처럼 메가진화를 쓰는 CPU',
        detail: '가상 배틀의 상대 파티는 거의 항상 메가진화 포켓몬을 넣고 선출에도 데려옵니다. 도구도 실전 채용대로 지닙니다.',
      ),
    ],
  ),
  (
    version: '1.7.1',
    date: '2026.11.12',
    entries: [
      (
        glyph: LabGlyph.controller,
        title: '팀 자동 구성 진행 화면',
        detail: '기다리는 동안 단계별 장면이 바뀝니다. 랭커 노트를 훔쳐보고, 후보를 면접 보고, 모의전에서 맞붙고, 세트를 하나씩 바꿔 보는 모습을 실제 진행 상황과 모의전 수, 지금 시험 중인 변경으로 보여 줍니다.',
      ),
    ],
  ),
  (
    version: '1.7.0',
    date: '2026.11.12',
    entries: [
      (
        glyph: LabGlyph.spark,
        title: '더 잘 만드는 팀 자동 구성',
        detail: '조커·메가진화·타입 조합·세트 최적화를 고를 수 있습니다. 팀을 짤 때 사용률보다 랭커 파티의 동시 채용 코어를 중시하고, 최종 후보는 도구·특성·기술·능력 포인트를 바꿔 보며 시뮬레이션으로 확인된 변경만 반영합니다. 랭커 파티 상대 전적과 그 기준의 순위도 볼 수 있습니다.',
      ),
      (
        glyph: LabGlyph.bolt,
        title: '실전 도구와 4배 빠른 시뮬레이션',
        detail: '필드 시드, 하양허브, 멘탈허브, 잠깨는열매, 노말주얼, 빛의가루, 기합의머리띠, 힘의머리띠, 박식안경의 효과를 배틀에 반영했습니다. 시뮬레이션을 CPU 코어에 나눠 돌려 추천과 팀 구성이 더 많은 판을 빠르게 검증합니다.',
      ),
    ],
  ),
  (
    version: '1.6.0',
    date: '2026.11.12',
    entries: [
      (
        glyph: LabGlyph.archive,
        title: '랭커 연구로 만드는 추천 파티',
        detail: '시즌 최종 상위 랭커 29팀의 코어를 분석해 추천의 출발점으로 삼고, 모든 후보를 메타 상대군과 랭커 파티 상대로 수천 판 시뮬레이션합니다. 조커 제외·허용·필수와 평가 깊이, 검증 CPU를 고를 수 있고 랭커 파티별 유리·호각·불리를 보여 줍니다.',
      ),
      (
        glyph: LabGlyph.controller,
        title: '더 편한 배틀 명령과 제대로 쓰는 순풍',
        detail: '넓은 화면에서는 명령 메뉴가 경기장 옆에 붙고, 포켓몬마다 한 장씩 명령을 고릅니다. 숫자 키·S·Enter 단축키와 기술별 상성 표시를 더했습니다. CPU는 순풍·트릭룸이 뒤집는 스피드 관계를 계산해 엘풍 같은 시동 요원이 첫 턴에 순풍을 겁니다.',
      ),
    ],
  ),
  (
    version: '1.5.0',
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
