# R8 잔여 단계 실행 지시서 — 7단계(V21 재검증) · 8단계(문서 개정)

작성: 2026-08-05 (세션 오퍼스 5). **이 문서만으로 콜드 스타트가 가능하도록** 썼다.
정본 계획서 `etc/plan_h0v21_window.md`(설계·근거·진행 로그)와 짝이며, 이 문서는
**남은 두 단계의 실행 지시**만 담는다. 상위 인계 정본은 `etc/HANDOFF_v2.md`.

---

## §0. 30초 요약

| | |
|---|---|
| 리포 상태 | **green — 440 passed / 3 skipped / 0 failed** (2026-08-05) |
| 끝난 것 | R8-0·a·b·c·d·e·f·g — **창·종료 재정의 구현 전부 완료, 재동결 완료** |
| 남은 것 | **7단계 V21 재검증 배터리**(계산 75~85분 + 사용자 육안 30분) → **8단계 문서 개정** |
| 그 다음 | **Phase A 착수** (`plan_hr_extension.md` R1a = `phase_A_robot_h1.md` Step A1) |
| 미결 결정 | **1건** — H3의 `delivered` 정의(투입 vs 수령). Phase D까지 이월 가능 |
| git | **미사용**(커밋·태그 금지). 리포 이동은 파일 복사 |

---

## §1. 무엇이 바뀌었는지 (7단계 전 반드시 읽을 것)

`configs/baseline_10f.yaml`이 **`window_policy: delivery`**를 선언한다.

| | 이전(legacy_margin) | 현재(delivery) |
|---|---|---|
| 시계 시작 | `min(ORD) − window_margin_sec`(3,600 s) | **`min(ORD) − warmup_sec`(600 s)** |
| 보행자 생성 종료 | `ped_end = max(ORD) + margin` | **컷오프 없음** (`ped_end = cap`) |
| cap | `ped_end + max_overrun` | **`max(ORD) + max_overrun`**(7,200 s) |
| 종료 | 전 주문 배달 **+ 배경 보행자 0** | **전 주문 배달 + 라이더 전원 건물 밖** |

`simulation.window_policy` 키가 없는 config는 **legacy_margin**으로 동작한다 —
`configs/regression_nobasement_10f.yaml`이 그 경로이고, 손대면 안 된다.

### 반드시 지킬 것 4가지

1. **비트 동일성 비교는 원리적으로 불가능하다.** 워밍업 길이가 바뀌면 `ped_rng`
   (seed+1)의 틱 정렬이 달라져 같은 시드도 다른 보행자 실현을 낳는다. 구·신 비교는
   **30시드 CI**로만 한다(§2 그룹 I/II/III).
2. **`results/pre_basement/` 4종을 재생성하지 말 것.** legacy 경로로 계속 재현돼야
   하고, `test_nobasement_replay_matches_pre_basement_snapshot`이 green인 것 자체가
   "건물이 바뀐 것이지 모델이 바뀐 게 아니다"의 증명이다(HANDOFF_v2 §3.6).
3. **v2 수치는 코드로 재생성되지 않는다.** 유일한 기록이
   `archive/h0_v2_frozen/`(읽기 전용, MANIFEST 참조). 비교·인용은 전부 거기서.
4. **스냅샷 구조 비교에 `cmp`/`md5sum` 금지** — `runtime_wall_sec`(벽시계) 때문에
   항상 "다르다"가 나온다. volatile 키 제외 + NaN 동치 구조 비교를 쓸 것.

---

## §2. 판정 도구 — KPI 3그룹 (사전 선언, 재론 금지)

| 그룹 | KPI | 합격 기준 |
|---|---|---|
| **I. 불변이어야 함** | T_e2e, T_lobby, W_EV, SLA율, n_by_mode, lobby_cost, rider_wait, `delivered` | 구·신 **30시드 CI95가 겹칠 것**. 안 겹치면 결함 |
| **II. 구조적으로 변해야 함** | ticks, wall_span, `utilization`(full), pedestrian n_spawned/n_completed, termination_reason | 방향 사전 선언 — **R8-e에서 6항목 전건 확인 완료**(아래) |
| **III. 정의상 불변** | `utilization_orderspan`, opex(라이더 체류 중에만 적산) | 통계적 동일 |

**그룹 II는 이미 확인됐다**(R8-e): ticks **−29.2~−40.5%**, `utilization` 상승해
`utilization_delivery`로 수렴(차 < 0.06), `n_in_building_at_end` > 0,
`termination_reason == delivery_complete`, 전 주문 인도. 7단계에서는 **그룹 I**을
30시드 CI로 판정하는 것이 본체다.

---

## §3. 7단계 — V21 재검증 배터리

### 실행 순서와 명령

배정 모델·effort는 계획서 §8.2. **Fable 미사용**, 같은 실패 2회 → 1단계 상향.

| # | 항목 | 명령 | 산출물 | 합격 기준 | 예산 |
|---|---|---|---|---|---|
| 1 | **V21-W1 AUD** | `.venv/bin/python -m experiments.vv_all39` 의 감사 스윕 부분 | 콘솔 | **A1~A14 전건 PASS**(A12는 SKIP 정상) | ~2분 |
| 2 | **V21-W2 GP** | `pytest tests/test_vv_golden_path.py tests/test_vv_golden_path_v2.py` | — | 14 passed. **v2의 손계산 상수를 그래프 조회로 바꾸지 말 것**(HANDOFF_v2 §3.5) | 초 |
| 3 | **V21-W3 ALL28** | `.venv/bin/python -m experiments.vv_all39` | `results/vv/all39_battery.csv` | 배터리 84/84 + 감사 28/28 | ~2.3분 |
| 4 | **V21-W4a EXT** | `pytest tests/test_vv_extreme.py` | — | 15 passed. 드레인 예산은 R8-d에서 **재측정 완료**(아래 §3.1) — 재확인만 | ~1분 |
| 5 | **V21-W4b MONO** | `.venv/bin/python -m experiments.vv_monotonicity` | `results/vv/monotonicity.csv` | **6방향 전건 PASS**. dir5 fallback 감소는 `gate=False` 정보행(기지 현상) | ~3분 |
| 6 | **V21-W5a·b** | `analysis/vv_decomp.py`, `analysis/vv_face.py` | `decomp_by_k.csv`, `face_*.csv`(4), PNG | **그룹 I이므로 값이 같아야 정상**. 잔차 ~1e-12 유지 | ~3분 |
| 7 | **V21-W5c·d** | `analysis/vv_balance.py`, `analysis/vv_evsel.py` | `ev_balance.csv`, `evsel_stale.csv` | 균형 max/min ≤ 1.5. **evsel은 절단 이벤트를 이미 거른다**(vv_evsel.py 89행) | ~4분 |
| 8 | **V21-W5e DET/VAR** | `.venv/bin/python -m experiments.vv_variance` | `variance_30seed.csv`, `variance_summary.csv` | **그룹 I 판정의 유일 도구.** 구(`archive/h0_v2_frozen/vv/`)·신 CI95 겹침 | **~46분** |
| 9 | **V21-W6 TIER** | `--tier {primary,extreme,all}` 3회 | CSV `tier` 열 | 행수 20/8/28, **보류 11개 0건 유입**. ⚠️ `--tier all`이어도 `tier` 열엔 시나리오별 실제 티어가 찍힌다 | ~3분 |
| 10 | **V21-W6 WIN 재정의** | `experiments/vv_window_bias.py` **수정 필요** | `window_bias.csv` | §3.2 참조 | ~5분 |
| 11 | **V21-NEW** | §3.3 신규 스크립트 2종 | `warmup_bias.csv`, `window_compare.csv` | 정식화 + `CORPUS_SCRIPTS` 등재 | ~5분 |
| 12 | **V21-W7 VISUAL** | 사용자 육안 | `checklist_visual_h0v2.md` §6 신설 | §3.4 참조 | 사용자 30분 |
| 13 | **V21-W8** | 구조 비교 + 보고서 | `verification_report_h0v2.md` 개정 | §3.5 참조 | ~10분 |

### §3.1 W4a에서 이미 재측정된 것 (다시 재지 말 것)

- **`RUSH_OVERRUN_SEC` 900 → 7200.** 구 근거("보행자 백로그 150~180 s")는 **무효** —
  cap 기준점이 ped_end에서 **마지막 주문**으로 옮겨졌고 종료가 배경을 안 기다린다.
  재실측: 30/분에서 마지막 퇴장 = 마지막 주문 **+2,796 s**(K50_1 +2,468 s).
- **60/분 배경은 종료하지 않는다.** overrun 7,200·28,800 s 양쪽 cap 트립, 건물 내
  보행자 **3,614 → 10,072명 발산**. 컷오프를 없앤 결과 **용량 초과 부하는 영원히
  배출되지 않는다.** 그래서 극단 테스트의 무거운 팔을 **30/분**(`SATURATING_PED_RATE`)로
  내렸다. 30/분은 완주하면서 4대 전부 가동률 1.000(대조군 0.092).
- **`test_tick_convergence`는 시드 평균으로 판정하도록 고쳤다.** 시드별 비교는
  dt 변경이 RNG 정렬을 흔들어 **몬테카를로 잡음**을 재고 있었다(시드별 최대 18.99 s
  vs 시드 평균 2.19 s). 진짜 이산화 편향은 1.1~2.2 s.

### §3.2 W6 V2-WIN은 **재정의가 필요하다** (스크립트 수정 있음)

`experiments/vv_window_bias.py`는 `scenario_window=False`를 명시 전달하는데,
delivery config에서는 **ValueError로 거부된다**(명시적 모순은 조용히 덮지 않는 설계).
비교 축을 바꿔야 한다:

- 구: `scenario_window` False ↔ True (고정 점심창 ↔ 데이터 유도)
- 신: **`window_policy` legacy_margin ↔ delivery**

구현: config 사본에 `window_policy`를 넣어 `run_baseline(config_path=...)`로 양팔을
돌린다(테스트 `tests/test_kpi_window.py::_legacy_summary`가 같은 패턴을 쓴다).
구 결론("고정 창이 혼잡을 W_EV +37.8~53.3% 과소평가")은 **축이 달라졌으므로 폐기**하고
재산출한다.

### §3.3 신규 검증 2종 — 이번 개정의 정당화 근거

측정은 **이미 끝났고** 스크립트화만 남았다. 원본은 세션 스크래치패드에 있었으므로
`experiments/`로 옮겨 재현 가능하게 만든다.

1. **`experiments/vv_warmup_bias.py`** → `results/vv/warmup_bias.csv`
   워밍업 머리 0/300/600/900/1800/3600/7200 × 8시드 × 2시나리오(112 run), **꼬리 고정**.
   결론: 배달 KPI 전부 ±1 SE, 단조 추세 없음 → **600 s로 충분**.
   ⚠️ **`window_margin_sec`만 스윕하면 안 된다** — 머리·꼬리가 동시에 움직여
   "워밍업이 길수록 혼잡"이라는 착시가 난다(진짜 원인은 후반 주문이 배경 끊긴 건물에서
   배달되는 것, W_EV −28%).
2. **`experiments/vv_window_compare.py`** → `results/vv/window_compare.csv`
   4창 비교. 결론: 이용률 왜곡의 **4~7%p는 워밍업 머리**, ped_end 꼬리 0.1~0.8%p,
   `peds==0` 조건은 **0.05%p**뿐.

둘 다 `CORPUS_SCRIPTS` 가드에 등재할 것(전례 = `analysis/vv_balance.py`).

### §3.4 W7 V2-VISUAL 부분 재서명 (사용자 액션)

- **면제**: `checklist_visual_h0v2.md` §3 기하 6항목 — R8은 기하를 건드리지 않았다.
- **재관찰 필요**: §4 거동 항목 중 **종료 직후 화면**(라이더 0인데 보행자·EV 잔여가
  남아 있는 것이 정상임을 확인)과 **배경 지속 생성**(ped_end 이후에도 보행자가 계속
  생기는지).
- **신규 확인 2가지**: ①앱 사이드바가 이제 논문 트랙 창을 쓴다(구 판본은 레거시
  고정창으로 돌고 있었다) ②**`FloorDemandPanel`**(신설)이 현재 프로파일·창 정책과
  설계 확률 대 실제 층 히스토그램을 보여 준다 — 프로파일을 바꿔 **Reset**한 뒤
  분포가 실제로 움직이는지 눈으로 확인.
- 실행: `.venv/bin/solara run simulation/app.py`
  (⚠️ 원격이면 `solara-assets` 설치 + `SOLARA_ASSETS_PROXY=True` + SSH 터널,
  `starlette<1.0` 핀 — 안 그러면 흰 화면)
- 판정 원본은 `etc/checklist_visual_h0v2.md`에 **§6 "R8 재서명"**을 신설해 기록.

### §3.5 W8 마무리

1. **구조 비교**: 재동결본을 2회 재생성해 상호·디스크 동일 확인(volatile 키 제외).
2. **grep 소탕**: 문서에 남은 구 수치·구 규약. 최소한 다음을 훑을 것 —
   `utilization`(주 지표 강등됨), `ped_end`(더는 종료 조건이 아님),
   "보행자 전원 완료"(계약 변경), `A1~A12`(→ A1~A14), 437(→ 440).
   ⚠️ **grep은 의미 반전을 못 잡는다**(V2-DOC 교훈) — 서사 판정은 8단계가 담당.
3. **`etc/verification_report_h0v2.md` 개정** — 게이트 표에 A13·A14 행 추가,
   §7.1 논문 재료 수치를 delivery 기준으로 교체.

---

## §4. 8단계 — 문서 개정

| 문서 | 무엇을 |
|---|---|
| `etc/HANDOFF_v2.md` | §0 상태·다음 단계, §3 규약에 **창·종료 규약 신설**(§3.8), §4에 R8 완료 기록, 파일 지도에 `plan_h0v21_window.md`·`archive/h0_v2_frozen/` |
| `etc/plan_h0_revision.md` | §1에 창·종료가 R8로 개정됐음을 링크 |
| `etc/plan_h0v2_verification.md` | A1~A12 → **A1~A14**, A1·A6·A8·A11이 정책 의존이 됐음 |
| `etc/research_plan_scie.md` | **결정 #23~#25 등재** — ①워밍업 600 s + A13 게이트 ②H0 완료 = 전 주문 배달 + 라이더 전원 퇴장 ③배경 보행자 컷오프 폐지. §7 한계 배너에 **보행자 절단**과 **60/분 비종료** 추가 |
| `etc/scie_phase/phase_A_robot_h1.md` | **H1 종료 조건**(로봇이 1F 로비 로봇존에 IDLE 복귀) 기록 |
| `etc/scie_phase/phase_C_*.md` | **H2는 분기 불필요** — "라이더 전원 퇴장 ∧ 로봇 전원 홈"의 AND가 자동 처리 |
| `etc/scie_phase/phase_D_*.md` | **H3 미결 결정 등재** — `delivered`를 사물함 **투입**(권장)으로 볼지 고객 **수령**으로 볼지 |
| `etc/note_kpiwin_convention.md` | 창 3+1종(warmup / delivery / run / orderspan)과 **주 지표 = `utilization_delivery`** |

### 논문에 반드시 반영할 4가지

1. **주 지표 승격**: `utilization` → **`utilization_delivery`**. 아직 `run.py` 콘솔
   출력·`plot_baseline.py`·`visualize.py`·`h0_baseline_stats.py`의 **표시 경로는
   전환하지 않았다**(R8-b에서 계산만 가산). 8단계에서 전환하고 `test_plot_baseline.py`의
   스텁 dict를 함께 고칠 것.
2. **`utilization`은 적재율이 아니다**: DOORS+MOVING+호출 있는 IDLE의 **시간 비율**.
   실측 평균 재차 인원은 4대 합계 **3.2~4.7명 / 정원 60석(5~8%)**. 정의 각주 +
   `mean_passengers_delivery` 병기 필수 — 심사자가 85%를 적재율로 읽는다.
3. **초반 10% 주문은 워밍업과 무관하게 낙관적이다**(head 7,200 s에서도 W_EV 17.0 vs
   전체 22.8). 초기화 편향이 아니라 **점심 피크 주문 램프**다. A13-④를 게이트가 아닌
   정보행으로 둔 이유이며, "모델 아티팩트가 아니다"를 본문에 써야 방어된다.
4. **보행자 KPI 절단**: 종료 시점 잔여 1~15명(7.5/분 기준 0.56%), 30/분에서는 ~60명.
   `n_in_building_at_end`로 매 run 기록된다. 보행자 대기를 인용하면 절단 편향을 명시.

---

## §5. 이번 개정에서 배운 함정 6가지 (다시 밟지 말 것)

1. **`window_margin_sec` 단독 스윕은 머리·꼬리를 함께 움직인다** → "워밍업이 길수록
   혼잡하다"는 착시. 머리만 보려면 꼬리를 고정할 것.
2. **임계값을 평균으로 잡으면 안 된다.** A13 임계 초안 0.6은 8시드 **평균**에서 나왔는데
   단일 시드 최소가 0.554라 거짓 FAIL이 났을 것이다. **분포로 정하라**(최종 0.35).
3. **가드는 명시적 모순에만 걸어라.** `scenario_window` 기본값 `False`에 의존하던
   호출부가 35곳이라, 정책 충돌을 무조건 raise 했더니 **56건이 죽었다**. 센티널
   `None`(정책이 결정) + 명시적 모순만 거부로 해결.
4. **완료를 단언하지 말고 보존을 단언하라.** `boards == alights` →
   `boards − alights == 잔여 탑승`. 정책이 바뀌어도 살아남고, 옛 정책에서는 동치다.
5. **재동결은 음성 테스트의 이빨을 뽑을 수 있다.** 리터럴 값을 주입하는 뮤테이션은
   새 기준선과 우연히 일치할 수 있다 — **진실 대비 상대 교란**으로 쓸 것.
6. **매직 넘버 단언은 게이트가 늘면 숨는다.** "비스킵 10개" 같은 카운트를 **집합
   단언**으로 바꿀 것.

---

## §6. 콜드 스타트 체크리스트

```bash
cd /home/sw/Research/abm_new
.venv/bin/python -m pytest -q          # 440 passed / 3 skipped 여야 한다
.venv/bin/python -m analysis.verify_h0 results/baseline_h0_K50_1_uniform_s42.json
#   -> A1~A14 중 A12만 SKIP, 나머지 PASS
```

읽을 순서: 이 문서 → `etc/plan_h0v21_window.md`(§1 실측 근거·§2 설계·§11 로그) →
`etc/HANDOFF_v2.md`(상위 상태) → `etc/plan_h0v2_verification.md`(구 배터리 정의).

메모리는 자동으로 따라오지 않는다:
`~/.claude/projects/-home-sw-Research/memory/project_abm_building_delivery.md`.
