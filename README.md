# Champions Meta Lab

Pokémon Champions 메타 분석 + 팀 빌더 + 조커 파인더. 더블배틀 기본, 싱글배틀 전환 지원.

```
backend/   FastAPI + 분석 엔진 (Python), SQLite 순위 스냅샷
app/       Flutter 앱 (web / windows / android) — Riverpod, GoRouter, Dio
```

## 실행

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m app.collector          # 데이터 수집 (처음 1회, 이후 갱신할 때)
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

`app/build/web` 이 있으면 백엔드가 웹 앱까지 같이 서빙하므로 http://localhost:8000 만 열면 된다.

```bash
cd app
flutter build web --release      # 웹 빌드 (백엔드가 서빙)
flutter run -d windows           # 또는 데스크톱 앱으로 실행
flutter run --dart-define=API_BASE=http://10.0.2.2:8000   # 안드로이드 에뮬레이터
```

## 데이터

- 배틀 데이터: [Pokémon Champions Battle Data](https://championsbattledata.com) API — 순위, 기술/도구/특성/성격/능력 포인트 채용률, 동료.
  **Battle data provided by Pokémon Champions Battle Data.** (공개 시 출처 표기 필수, 원본 데이터 재배포 금지)
- 기술 정보(타입/위력/명중/우선도): Pokémon Showdown `moves.json`
- 한글 이름: PokeAPI CSV
- 아이콘: 원본 사이트 에셋을 백엔드가 받아 `backend/data/cache/img` 에 캐시

## 분석 방식과 한계

- 원본에 종 단위 **사용률(%)이 없고 순위만** 있다. 메타 가중치는 `1/sqrt(순위)`, 조커 조건은 "N위 밖"으로 처리한다.
- 능력치 = Lv.50 실수치 + 능력 포인트(1포인트 = +1, 한 능력치 32 / 총 66) × 성격 보정.
- 데미지는 근사치다 (평균 난수, 급소·랭크 변화·날씨 지속·테라 등 미반영). 상대는 "가장 흔한 세트"로 가정한다.
- 승률, 선봉 데이터는 원본에 없다. 상대 분석의 **예상 선봉은 추정치**다
  (동료 채용 순서 + 역할 시너지 + 내 팀 압박도, `backend/app/enemy.py`).
- 7일/14일 추세는 수집할 때마다 `backend/data/history.sqlite` 에 쌓이는 스냅샷으로 계산한다
  (지금은 지난 시즌 대비 변동만 표시).

## 다음 단계 (미구현)

- Phase 5: 턴 1 어시스턴트, 정밀 데미지 계산기
- 주기 수집(cron), LLM 설명 레이어
