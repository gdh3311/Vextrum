# Vextrum Workbench 아키텍처

2026-11-13 · 앱 화면 `/workspace` (팀 워크스페이스) · 백엔드 `backend/app/workbench.py`

## 1. 흐름

```
팀 편집(왼쪽) ──► 빠른 분석(가운데, 정적, 수십 ms)
     │                    │
     │                    └─► 전략 연결성·속도·약점·메타 위협·선봉
     ▼
교체 추천 / 상대 대응 / 실험실 / 실전 기록 (오른쪽)
     │        정적 후보·가설 (즉시)
     └─► 모의전 작업 (비동기, 진행률, 취소) ──► 결과 + 신뢰구간 + teamRevision
```

## 2. 두 층

| 층 | 무엇 | 응답 | 승률 표시 |
|---|---|---|---|
| Fast Analysis | 규칙 점검, 타입·화력, 역할, 속도·속도 조작·선제기, 메가 선택지, 메타 상위 20종 정적 상성, 전략 태그와 무결성 점검, 정적 선봉 | 동기 HTTP. 측정: 첫 호출 243~292ms(엔진 캐시 준비), 이후 캐시 없이 23ms, 같은 팀 재요청 7ms(HTTP) | 하지 않음 (`basis: "static"`) |
| Deep Validation | 교체 후보 검증, 상대 6마리 선출 비교, 팀·세트·선봉 실험 | 비동기 작업 (`/api/workbench/job/{id}`), 진행률·취소 | 같은 상대·난수 짝지은 비교 + 95% 신뢰구간, 0을 넘지 않으면 '결론 보류' |

## 3. 버전 관리

- `teamRevision`: 앱이 팀 세트 JSON의 해시로 계산한다 (`workspace_state.teamRevisionOf`). 같은 구성이면 같은 번호라 되돌리기 후에도 결과가 다시 유효해진다.
- 모든 요청·응답·작업에 `teamRevision`이 붙는다.
- 빠른 분석: 응답의 revision이 현재와 다르면 버린다 (테스트: `app/test/workspace_test.dart` 마지막 시나리오).
- 작업: 같은 범위(`scope`, 예: `replace:4`, `matchup`, `experiment`)의 새 작업이 시작되면 이전 작업을 취소한다. 취소된 작업의 결과는 저장되지 않는다
  (테스트: `test_newer_revision_cancels_older_job_in_same_scope`).
- 화면: 결과의 revision이 현재 팀과 다르면 "이전 버전 팀의 것" 경고를 붙인다 (`staleBanner`).

## 4. 잠금

- 슬롯별 `pokemon / moves / item / ability / nature / points` 잠금. 기기 저장(`workspace_locks_v1`, 팀 이름별).
- 서버 `workbench.apply_locks`, 앱 `applyLocks` 같은 규칙: 포켓몬이 잠기면 교체 거부, 필드가 잠기면 원래 값 유지.
- 교체 추천은 잠긴 자리를 대상으로 하지 않는다 (400).

## 5. 정확성 장치

- 규칙 점검(`workbench.legality`): 배우지 못하는 기술, 불가능한 특성, 없는 도구·성격·메가 폼, 메가스톤 불일치, 능력 포인트(0~32, 합 66), 같은 종·같은 도구.
  high 등급이 있으면 모의전 작업을 거부한다.
- 모의전 미구현 요소(`simulation.UNIMPLEMENTED_*`, `move_supported`)가 들어간 실험은 `precise: false`로 표시한다.
- 상대의 비공개 정보: 선출·CPU 판단은 공개 정보만 쓴다 (`Battle._seen`, `test_v3`).
- 시즌: 원본 M7 표본은 공식 M8과 구분해 경고 (`regulation.data_warnings`), 이전 시즌 랭커 팀은 가중치를 낮춘다 (`season_weight`).

## 6. 재사용한 기존 구현

| 기능 | 기존 모듈 |
|---|---|
| 정적 팀 분석 | `engine.analyze_team` |
| 정적 상성·후보 세트 | `auto_team._pool`, `_candidate` |
| 전략 태그 | `strategy.analyze` |
| 선봉 가이드 | `guide.team_guide` |
| 1:1 데미지 | `lab.duel` |
| 상대 6마리 선출 | `enemy.analyze_enemy` (`preview.DoublesPreview`) |
| 상대 전략 확률 | `battle_lab.preview_strategy` |
| 모의전 | `parallel.compare_teams` (짝지은 비교, CPU 스타일 순환) |
| 팀 저장·전환·복제 | 앱 `team_state.TeamNotifier` |
| 실전 기록 입력 | 앱 `match_journal` (상대 분석 화면) |

## 7. API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/workbench/fast` | 빠른 분석 |
| POST | `/api/workbench/replace` | 한 자리 교체 후보 (정적) |
| POST | `/api/workbench/replace/validate` | 후보 모의전 검증 작업 |
| POST | `/api/workbench/matchup/pokemon` | 상대 포켓몬 하나 대응 (가설 세트) |
| POST | `/api/workbench/matchup/team` | 상대 6마리: 선출 추천 + 전략 가설 |
| POST | `/api/workbench/matchup/validate` | 선출 후보 모의전 비교 작업 |
| POST | `/api/workbench/experiment` | 두 구성 실험 작업 |
| GET | `/api/workbench/job/{id}` | 작업 상태·진행률·결과 |
| POST | `/api/workbench/job/{id}/cancel` | 작업 취소 |
| POST | `/api/workbench/feedback` | 실전 기록 분석 (기록은 기기 저장, 서버는 계산만) |

모의전 작업 중에는 자동 연구가 쉰다 (`LAB.busy`).
