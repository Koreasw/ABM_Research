# analysis/h0v21_insights/ — H0 v2.1 인사이트 트랙 (T0~T3) 산출물

2026-08-06 수행. **H1~H3 로봇 모드 착수 전**, 현행 H0 v2.1 시스템을 ①에이전트
클래스별 KPI ②수요 K∈{50,100,200,300} ③H1·H2·H3 확장 방향성의 세 축으로
코퍼스 28 시나리오 전수 진단한 결과의 **자기완결 폴더**.

**핵심 문서: [`note_h0v21_insights.md`](note_h0v21_insights.md)**
(발견 + Phase별 사전 고려 체크리스트 18항 + 정본 문서 정정 목록 10건).

---

## 이 폴더와 `analysis/h0_insights/`의 관계

| 폴더 | 무엇인가 | 지위 |
|---|---|---|
| **`h0v21_insights/`** (여기) | **v2.1 축**의 진단. EV 4대 · 공용 EV3·EV4 · 코퍼스 28개 | **현행 정본** |
| `h0_insights/` | W7의 v1↔v2 대조 노트 `note_v1_v2_comparison.md` **+ v1 축 분석을 v2.1 데이터에 돌린 산출물** | 대조 노트만 유효. **`tables/`·`figures/`의 로봇 지표는 EV2 기준이라 무효** |
| `archive/h0_v1/analysis_outputs/h0_insights/` | 2026-08-03 v1 진단(EV 2대 · 38 시나리오) | **읽기 전용. 절대값 인용 금지**, 정성 예측만 유효 |

> ⚠️ `h0_insights/tables/robot_prediagnosis.csv`의 `ev2_*`·`h1_ev2_trip_ratio`
> 열은 **사람 전용 차(EV2)** 를 재고 있다. 로봇이 쓰는 것은 공용 EV3·EV4이며,
> 그 값은 이 폴더의 `hr_h1_prediagnosis.csv`에 있다.

---

## 파일 색인

### 표 (`tables/`)

| 파일 | 행 | 내용 |
|---|---|---|
| `agent_kpi_by_k.csv` | 70 | **T1** 에이전트 클래스 × 지표 × K (wide). customer / rider / elevator(+dedicated/shared) / pedestrian / building |
| `agent_kpi_by_scenario.csv` | 1,960 | 같은 지표의 시나리오 단위 long 포맷 |
| `ev_by_car.csv` | 16 | 차 1대 단위 (K × EV1~EV4). 탑승 주체별 보딩·대기 분해 포함 |
| `rider_by_hire_type.csv` | 12 | BIKE / WALK / CAR 별 T_lobby·T_e2e·계단비율·임금 |
| `kpi_by_floor.csv` | 36 | 배달 층(2~10F)별 T_e2e·T_lobby·EV 대기·계단 비율 |
| `demand_scaling_by_k.csv` | 10 | **T2** 주요 KPI의 K 스케일링 + K별 시나리오 min/max/CV |
| `ev_knee_by_scenario.csv` | 28 | 가동률 vs 대기 (무릎 산점도의 원자료) |
| `variance_decomposition.csv` | 9 | between-K / within-K 시나리오 / seed 분산 분해 |
| `te2e_decomposition_by_k.csv` | 4 | **T3** T_e2e 7성분 분해 (K별, 비율 포함) |
| `te2e_decomposition_by_scenario.csv` | 84 | 같은 분해의 run 단위 |
| `hr_h1_prediagnosis.csv` | 28 | **H1** 상금 상한 · 공용 EV 거부 노출 · 트립 이관 · 양면 외부성 영점 |
| `h2_queue_inputs.csv` | 28 | **H2** 건물 도착 c_a² · 증폭 · 로봇 1주기 · ρ · 최소 로봇 대수 · 큐 상한 |
| `h3_locker_sizing.csv` | 16 | **H3** K × τ(5·10·15·30분) 층당 최대 동시 점유 |
| `h3_locker_by_scenario.csv` | 112 | 같은 값의 시나리오 단위 |
| `scenario_traits.csv` | 28 | S0 원시 수요 특성 (사본, 폴더 자기완결용) |
| `h0_kpi_by_scenario.csv` | 84 | S1 run 단위 KPI 전 필드 (사본) |

### 그림 (`figures/`)

| 파일 | 내용 |
|---|---|
| `g1_agent_scaling.png` | 에이전트 클래스별 K 스케일링 (6 패널) |
| `g2_shared_vs_dedicated.png` | 공용(EV3·EV4) vs 전용(EV1·EV2) — 로봇 도입 전 영점 |
| `g3_util_wait_knee.png` | 가동률 vs 대기 무릎 (라이더 / 보행자) |
| `g4_te2e_decomposition.png` | T_e2e 7성분 누적 막대 (건물 내 비중) |
| `g5_h1_prediagnosis.png` | H1 상금 상한 · 거부 노출 · 공용 EV 부하 증가 |
| `g6_h2_queue_inputs.png` | c_a² 증폭 · 로봇 대수별 ρ |
| `g7_h3_locker_sizing.png` | 락커 칸 수 vs 체류시간 τ |
| `g8_variance_decomposition.png` | 분산 분해 (수요 크기 / 패턴 / seed) |

팔레트는 dataviz 레퍼런스 인스턴스이며 2026-08-06 재검증
(`validate_palette.js` — ALL CHECKS PASS, 대비 WARN은 직접 라벨 + 동봉 CSV로 해소).

---

## 재현

```bash
.venv/bin/python -m experiments.h0_descriptive --tier all   # T0: 84 run (~6s, 40워커)
.venv/bin/python -m analysis.h0v21_stats                    # T1~T3 + 그림 (~30s)
```

- 원본 run: `results/h0_stats/runs/{stem}_s{seed}.json.gz` (84개)
- `h0_descriptive`는 `delivered`를 `results/vv/all39_battery.csv`와 전수
  교차검증한다 (84행 비교, **0 불일치**).
- `h0v21_stats`는 T_e2e 분해의 float-exact 무결성 게이트를 **15,600 주문
  전건에 재적용**한다 (위반 시 SystemExit).
- 입력 가드: 28 시나리오 × 3 seed가 아니거나 `window_policy != delivery`이거나
  `termination_reason != delivery_complete`이면 **조용히 분석하지 않고 중단**한다.

## 거버넌스

- **진단 트랙(3 seed).** 논문 인용 수치의 정본은 Phase D(30 seed + CRN).
- **v2.1 수치는 `archive/h0_v2_frozen/`과 run 단위 비교 불가** (R8 워밍업 변경으로
  같은 시드가 다른 보행자 실현을 낳음 — HANDOFF_v2 §3.8-1).
- 시뮬레이션 코드 변경은 T0의 additive KPI 1건
  (`kpi.elevator.*.n_boardings_by_kind` / `w_ev_*_by_kind_sec` /
  `shared_with_robot`). 전체 스위트 **441 passed / 3 skipped**, 동결 스냅샷
  게이트 포함 green.
