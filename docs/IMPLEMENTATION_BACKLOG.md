# 구현 백로그 (Workbench)

상태: ✅ 구현·테스트 · 🟡 일부 · ⬜ 미구현. 근거 문서는 같은 폴더의 각 명세.

## Phase 0 — 감사

| 항목 | 상태 | 근거 |
|---|---|---|
| 기존 팀 생성·평가·시뮬레이터·편집·상성 기능 조사, 재사용 결정 | ✅ | `VEXTRUM_WORKBENCH_ARCHITECTURE.md` 6장 |
| 메가 처리 수정 확인 | ✅ | `tests/test_sim_rules.py` (턴 시작 진화, 1회), 직접 배틀 선택(1.15.0) |
| CPU 편향 대응 확인 | ✅ | 엔진 v6, 진단 보고서 12장 |
| 기술 효과 · 전략 설명 오류 | 🟡 | 미구현 요소 목록과 후보 제외(1.15.0), 미구현 특성 다수 남음 |

## Phase 1 — Live Team Editing ✅ (`INTERACTIVE_TEAM_BUILDER_SPEC.md`)
- ⬜ 슬롯 순서 드래그, 필드 단위 Undo, 서버 측 버전 이력

## Phase 2 — Replacement Finder ✅ (`REPLACEMENT_RECOMMENDATION_ENGINE.md`)
- ⬜ 보유 포켓몬 목록 입력 화면 (API는 지원)
- ⬜ 위협 맞춤 새 세트 합성, 정적 점수를 연구 DB 실제 승패로 보정
- ⬜ 선택한 포켓몬의 최적 기술·도구·특성 (기존 `set_tuner`를 잠금 필드와 함께 노출)

## Phase 3 — Matchup Intelligence ✅ (`MATCHUP_INTELLIGENCE_ENGINE.md`)
- ⬜ 기술 조합 가설, 상대 팀 붙여넣기 가져오기

## Phase 4 — Simulation Lab 🟡 (`SIMULATION_LAB_SPEC.md`)
- ✅ 팀/세트 A·B 실험, 난이도, 결과 화면
- ⬜ 선봉·아키타입·스타일 선택 화면, 결과 나란히 비교, 실험 기록

## Phase 5 — Battle Feedback 🟡
- ✅ 기존 전적 기록 기반 분석
- ⬜ 입력 항목 확장, 기록별 모의전 예측 비교, 자동 입력 조사

## Phase 6 — 통합 🟡
- ✅ 한 화면(워크스페이스)에 편집·분석·교체·대응·실험·기록 연결, 반응형(1200px 이상 3열, 그 아래 1열)
- ⬜ 경쟁 서비스 대비 사용성 테스트 (실사용자)

## 데이터·규칙

- ⬜ Champions Battle Data 재배포 조건 확인 (배포판 dataset.json 동봉)
- ⬜ 공식 M8 데이터 (원본 미개설)
- ⬜ 남은 미구현 특성·기술 (저주받은바디, 강제 교체류, 멸망의노래 등)
- ⬜ 조종 AI 대칭화 (진단 6장, 순위 상관 0.12)
