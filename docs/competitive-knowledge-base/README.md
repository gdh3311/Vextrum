# Vextrum Competitive Knowledge Base

2026-11-14 KST 기준. Pokémon Champions의 M8 랭크 더블배틀을 분석하는 Vextrum 1.18.0 베타용 자료다. 공식 게임 규정, Vextrum 코드 동작, 통계 표본, 운영 가설마다 근거를 붙였다. **확인됨**은 해당 근거 범위에서 확인, **추정**은 참조 구현·간접 자료·전술 가설, **미확인**은 증거 부족, **미구현**은 Vextrum에 해당 동작이 빠졌음을 뜻한다.

| 문서 | 내용 |
|---|---|
| [A · Master Reference](A-master-reference.md) | 공식 룰, 앱 차이, 기술·특성·도구·날씨·필드·메가진화, 계산 방법 |
| [B · Pokémon Competitive Database](B-pokemon-database.md) | JSON 구조, 재생성 방법, 대표 세트 및 데이터 해석 |
| [C · Current Meta Report](C-current-meta.md) | M8, 비교 가능한 M7 표본, 공개 M-C 대회 파티 |
| [D · Team Building Framework](D-team-building.md) | 사용자 성향, 파티 점검, 선출 비교, 14개 아키타입, 계산·검증 규칙 |
| [E · Battle Matchup Playbook](E-matchup-playbook.md) | 13개 매치업의 선봉·초반 턴·교체·승리 조건 |
| [F · Unverified & Missing Data](F-unverified.md) | 확인 불가 항목, 재현이 필요한 규칙, 데이터 갱신 순서 |

**확인된 범위**

- 공식 M8 랭크는 M-C다. 참가 웹 목록의 엔트리 코드를 직접 읽어 전국도감 번호 231종과 비메가 엔트리 262폼을 확인했다. 29폼은 9월에 열린 M-C 스탠더드 셀렉트에 추가된 항목이다. [공식 M8](https://champions-news.pokemon-home.com/en/page/867.html) · [공식 M-C 참가 목록](https://web-view.app.pokemonchampions.jp/battle/pages/events/rs178713870219xeaaio/ko/pokemon.html) · [스탠더드 셀렉트](https://champions-news.pokemon-home.com/ko/page/821.html)
- Vextrum 스냅샷에는 263개 폼 레코드와 메가 데이터 81개가 있다. 앱의 대전 데이터 공급원은 조사일에 `M8` 조회에 `Unknown season`(400)을 반환했다. 앱의 채용률은 2026-11-12 13:55 KST에 생성된 M7 계열 표본을 사용한다. 지식 기반에는 별도로 확인한 11월 13일자 M8 더블 상위 12종과 랭크 15위 사례 1팀을 추가했다. [대전 데이터 API 명세](https://championsbattledata.com/api_guide) · [Pokémon Zone M8 표본](https://www.pokemon-zone.com/champions/ranked-seasons/doubles/?page=1) · [Pokémon Trainer Dex 랭커 사례](https://www.pokemonchamp.club/en/teams/4445/)
- 대량 구조화 데이터는 로컬 `backend/data/competitive-kb/`에 있다. 생성기와 사람이 읽을 문서는 저장소에서 버전 관리할 수 있고, 공급원 기반 데이터는 로컬 분석에 사용한다. [데이터 사용 조건](https://championsbattledata.com/api-rules/)

다른 AI에 전달할 때는 이 폴더와 로컬 `manifest.json`을 먼저 읽도록 하고, 필요한 포켓몬·기술·메가 항목을 ID로 불러오면 된다. 신규 팀의 승률이나 실제 1타·2타 여부를 요구할 때는 상대 세트·필드·행동 조건을 함께 입력한다.

## 출처 식별자

| ID | 자료 | 확인일 |
|---|---|---|
| OFF-M8 | [공식 랭크 시즌](https://champions-news.pokemon-home.com/en/page/867.html) | 2026-11-14 |
| OFF-MC | [공식 레귤레이션](https://champions-news.pokemon-home.com/ko/page/816.html) · [참가 목록](https://web-view.app.pokemonchampions.jp/battle/pages/events/rs178713870219xeaaio/ko/pokemon.html) | 2026-11-14 |
| PATCH | [Nintendo 업데이트 이력](https://en-americas-support.nintendo.com/app/answers/detail/a_id/71525/p/897) · [M-C 적용 공지](https://champions-news.pokemon-home.com/en/page/817.html) | 2026-11-14 |
| VGC | [공식 대회 규정 §2, §4](https://mcdn.pokemon.com/pokemon-prod/raw/upload/v1/live/static-assets/content-assets/cms2/pdf/play-pokemon/rules/play-pokemon-vgc-tournament-handbook-en.pdf) | 2026-11-14 |
| VX | [코드 v1.18.0-beta](https://github.com/gdh3311/Vextrum/tree/v1.18.0-beta), `sim-2026.11.14`, `cpu-tiers-v6`, `champions-local-2026.11-r1` | 2026-11-14 |
| CBD | Battle data provided by [Pokémon Champions Battle Data](https://championsbattledata.com/api_guide) | 스냅샷 2026-11-12 · 원격 2026-11-14 |
| M8-PUBLIC | [Pokémon Zone M8 더블 집계](https://www.pokemon-zone.com/champions/ranked-seasons/doubles/?page=1) · [Pokémon Trainer Dex 공개 팀·코어](https://www.pokemonchamp.club/en/insights/?format=double&season=M-8) | 2026-11-14 |
| PS | [Showdown 도감](https://play.pokemonshowdown.com/data/pokedex.json) · [기술](https://play.pokemonshowdown.com/data/moves.json) · [Champions 보정](https://github.com/smogon/pokemon-showdown/tree/master/data/mods/champions) | 로컬 캐시 및 2026-11-14 원격 |
| GD | [그단스크 공개 팀시트](https://standings.limitlessvgc.com/0044/standings) · [대회 주최 측 결과](https://championships.pokemon.com/en-us/events/regionals/2026/gdansk) | 2026-11-14 |
