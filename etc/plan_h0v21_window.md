# H0 v2.1 개정 계획서 — 창(window)·종료(termination) 재정의

작성: 2026-08-05 (세션 오퍼스 5/high). 지위: **R8 단계의 정본 실행 계획서**.
상위 문서 `etc/research_plan_scie.md`, 선행 `etc/plan_h0_revision.md`(R0~R7),
`etc/plan_h0v2_verification.md`(W1~W8), 인계 정본 `etc/HANDOFF_v2.md`.

**사용자 확정 2026-08-05**: ①워밍업 3,600초 → **600초**(실측 포화시간) + 게이트
강제 ②H0 종료를 **"전 주문 배달 + 라이더 전원 건물 밖"**으로 변경, H1~H3는
**구현하지 않고 기록만** ③`simulation.window_policy` config 키로 분리해
`results/pre_basement/` 비트 동일성 잠금 보존.

---

## §0. 30초 요약

| | |
|---|---|
| 무엇을 | 시뮬레이션의 **초기 상태(워밍업)와 완료 조건**을 데이터 근거 위에 다시 세운다 |
| 왜 | 현행 워밍업 3,600초는 임의값이고, 종료 조건에 **배경 보행자 배출**이 들어가 배달 시스템의 완료 정의와 어긋난다 |
| 핵심 제약 | 워밍업 길이가 바뀌면 `ped_rng` 틱 정렬이 달라져 **같은 시드라도 결과가 달라진다** → 구/신 비교는 비트 동일성이 아니라 **30시드 CI**로만 가능 |
| 하위호환 | `window_policy: legacy_margin`(기본값)이 현행 동작을 100% 보존 → `pre_basement` 4종 잠금 유지 |
| 재동결 | `results/baseline_h0_*` 4종만. `results/pre_basement/` 4종은 **손대지 않고 green 유지로 무변화를 증명** |
| 예산 | 계산 75~85분 + 전체 스위트 + 사용자 육안 30분 |

---

## §1. 실측 근거 (2026-08-05, 이 계획의 전제)

세 실험을 먼저 돌리고 그 결과 위에 설계를 얹었다. 재현 스크립트는 §6에서
`experiments/`로 정식 편입한다.

### 1.1 배경 트래픽은 600초면 포화하고, 발산하지 않는다

4시간 워밍업(K50_1, seed 42·7)을 600초 구간으로 절단:

- 유입 7.5명/분 = 처리량 7.5명/분, spawned 3,991 = completed 3,991 → **안정 시스템**
- EV 가동률은 0~600초 구간만 0.64로 낮고, 이후 13,800초까지 **추세 없이 0.60~0.89 진동**(평균 0.75)
- 첫 주문 시점 상태(8시드, 직전 300초): 가동률 **0.779**, 체류 보행자 **6.3명**, 대기 **2.5명**

즉 현행 워밍업은 "1시간 유휴 여유"가 아니라 이미 **데워진 건물**을 만들고 있었고,
필요량의 6배였다.

### 1.2 워밍업 길이는 배달 KPI를 바꾸지 않는다

꼬리(`ped_end`)를 3,600초에 **고정**한 채 머리만 0~7,200초로 바꿔 8시드 × 7수준 ×
2시나리오 = 112 run:

| 시나리오 | head=0 | 300 | 600 | 900 | 1800 | 3600 | 7200 | SE |
|---|---|---|---|---|---|---|---|---|
| K100_1 W_EV | 22.99 | 22.50 | 24.48 | 24.94 | 23.94 | 23.54 | 22.79 | ±0.5~1.2 |
| K100_1 util_orderspan | 0.853 | 0.856 | 0.862 | 0.857 | 0.854 | 0.846 | 0.848 | |
| K300_4 W_EV | 37.39 | 34.43 | 35.94 | 35.51 | 36.51 | 36.91 | 35.01 | ±0.6~1.0 |

**단조 추세 없음, 전부 ±1 SE 내.** 주문 구간(6,300~7,100초)이 완화시간(600초)의
10배 이상이라 초기 200~300초의 가벼운 건물이 평균에 묻힌다.

> ⚠️ **함정 기록**: `window_margin_sec`만 스윕하면 **머리와 꼬리가 동시에** 움직여
> "워밍업이 길수록 혼잡해진다"는 착시가 나온다(margin 0에서 W_EV 23.0→16.6, −28%).
> 진짜 원인은 `ped_end = max(ORD) + margin`이 당겨져 **후반 주문이 배경이 끊긴
> 건물에서 배달**된 것이다. 머리를 분리하면 효과가 사라진다. 이 함정이 §2.1에서
> 보행자 컷오프를 폐지하는 직접적 근거다.

### 1.3 이용률 왜곡의 5%p는 워밍업에서, 0.05%p만 보행자 종료 조건에서 왔다

종료를 앞당기는 것은 현재 run의 **엄격한 prefix**이므로(종료 판정은 루프만 끊고
상태를 바꾸지 않는다) 주문 단위 KPI는 불변이고 창 정규화 KPI만 움직인다. 같은
run에서 4개 창을 정확히 계산(4시나리오 × 3시드):

| 시나리오 | 꼬리 합계 | 그중 `ped_end` 가드 | 그중 `peds==0` | (a) 현행 | (b) 라이더 퇴장 종료 | (c) [첫 주문, 라이더 퇴장] | (d) 현행 `utilization_orderspan` |
|---|---|---|---|---|---|---|---|
| K50_1 | 1,243s | 1,197s | **46s** | 0.780 | 0.785 (+0.005) | 0.819 (**+0.039**) | 0.819 |
| K100_1 | 823s | 771s | **52s** | 0.799 | 0.805 (+0.006) | 0.848 (**+0.049**) | 0.848 |
| K200_1 | 1,028s | 966s | **62s** | 0.828 | 0.836 (+0.008) | 0.898 (**+0.070**) | 0.898 |
| K300_4 | 141s | 104s | **37s** | 0.845 | 0.846 (+0.001) | 0.904 (**+0.059**) | 0.905 |

**결론**: `peds==0` 조건 단독 기여는 37~62초(0.05%p), 꼬리 전체가 0.1~0.8%p,
**워밍업 머리가 4~7%p**로 지배적이다. 그리고 (c)는 기존 `utilization_orderspan`과
소수 셋째 자리까지 같다 — **올바른 값은 이미 계산되고 있었고, 문제는
`utilization`이 주 지표 자리에 있는 것**이었다.

---

## §2. 설계

### 2.1 창 정책 두 가지 (`simulation/model.py`)

새 config 키 2개. `configs/regression_nobasement_10f.yaml`은 **한 글자도 건드리지
않는다** — 키가 없으면 코드 기본값 `legacy_margin`으로 현행 동작이 보존된다.

```yaml
simulation:
  window_policy: delivery      # legacy_margin | delivery
  warmup_sec: 600.0            # delivery 정책 전용
  max_overrun_sec: 3600.0      # delivery에서 의미 변경: cap = max(ORD) + overrun
```

| | `legacy_margin` (기본값·현행 보존) | `delivery` (신규, baseline_10f.yaml) |
|---|---|---|
| clock_start | `min(ORD) − window_margin_sec` | **`min(ORD) − warmup_sec`** |
| 보행자 생성 종료 | `ped_end = max(ORD) + margin` | **컷오프 없음 — 시뮬레이션 종료까지 계속 생성** |
| cap | `ped_end + max_overrun` | **`max(ORD) + max_overrun`** |
| 종료 | drain-all (보행자 0 포함) | `_pipeline_empty ∧ _delivery_complete ∧ _carriers_settled` |

**보행자 컷오프 폐지의 근거는 §1.2 함정**이다. 새 종료 조건은 배달 기준이므로
배경 컷오프가 애초에 불필요하고, 남겨 두면 후반 주문에 인공 편향을 주입한다.

### 2.2 종료 조건 (`_check_termination` 교체)

```
cap 검사 → 정책 분기 → (delivery) K==0 축퇴 가드 → 3조건 AND
```

- `_pipeline_empty()` — `rider_events` / `dispatch_events` / `pending_arrivals` /
  `rider_pool.waiting` 전부 빔. **`pending_releases`(return_leg 복귀)는 의도적
  제외** — 라이더는 이미 건물 밖이고, 전 주문 배달 시점에 그 복귀가 풀어 줄 대기
  주문은 존재할 수 없다.
- `_delivery_complete()` — 전 `CustomerAgent.delivered_at_sec is not None`.
- `_carriers_settled()` — **H0 = 건물 내 `ExternalRiderAgent` 0.**
- `K == 0` 축퇴 가드 — 주문이 없으면 "모두 배달됨"이 공허참이라 1틱에 끝난다.
  이때만 `ped_end`(또는 `max_overrun`) 기준으로 되돌린다.
- 신규 필드 **`termination_reason`** ∈ {`delivery_complete`, `drain_all`, `cap`}.

구 `clock ≥ ped_end` 가드를 **뺄 수 있는 이유**: 그 가드는 "Poisson의 순간 0을
완료로 오판"하는 것을 막으려던 것인데(model.py 구 844~846행), 새 조건에는 보행자가
등장하지 않으므로 오판 경로 자체가 없다.

### 2.3 H1~H3 — 구현하지 않고 기록만 (사용자 지시)

`_carriers_settled()` 안에 **실행되지 않는 분기 + docstring**으로 남기고, 문서
3곳에 박는다. 생성자의 `NotImplementedError`(model.py 114~117행)는 그대로 둔다.

| 모드 | 완료 조건 | 기록 위치 |
|---|---|---|
| **H1** | H0 조건 + **로봇이 1F 로비 로봇존에 IDLE 복귀** (R3에서 대기＝충전을 1F로 통합했으므로 홈이 단일 노드로 잘 정의됨) | `_carriers_settled()` 스텁 + `etc/scie_phase/phase_A_robot_h1.md` |
| **H2** | **분기 불필요** — "라이더 전원 퇴장 ∧ 로봇 전원 홈"의 AND가 주문별 혼재를 자동 처리한다. 주문마다 누가 배달했는지 볼 필요가 없다 | 같은 스텁 + `phase_C_*.md` |
| **H3** | H1과 동일 + (미결) `delivered`를 **사물함 투입**으로 볼지 **고객 수령**으로 볼지 | `phase_D_*.md`에 **미결 결정**으로 등재 |

**H3 미결 결정에 대한 권고**: **투입 시점**을 `delivered`로 하고 수령 지연은 별도
KPI(`T_pickup`)로 분리할 것. 수령 시점으로 잡으면 ①`CustomerAgent`를 능동화해야
하고(현재 완전 수동, `customer.py` 51~54행) ②종료가 고객 수령까지 늘어지며
③T_e2e에 수령 지연이 섞여 **H0~H2와 비교 가능성이 깨진다.**

---

## §3. KPI 재정의 (`simulation/kpi.py`)

### 3.1 창 3+1종을 1급 개념으로

| 창 | 구간 | 용도 |
|---|---|---|
| warmup | `[clock_start, first ORD)` | A13 게이트 입력 |
| **delivery** | `[first ORD, last rider exit]` | **주 지표 창** |
| run(full) | `[clock_start, clock_end]` | 진단용 |
| orderspan | `[first ORD, last delivery]` | **기존 동결 필드 — 정의·값 불변** |

### 3.2 신규 필드 (전부 가산 — V6-KPIWIN 관례 준수, 기존 필드 불변)

```
elevator[ev].utilization_delivery          ← 주 지표로 승격
elevator[ev].mean_passengers_delivery      ← model._ev_pax_cum 신설 필요
building.opex_running_krw_delivery
pedestrian.n_in_building_at_end            ← 절단 규모 기록
simulation.window_policy / warmup_sec / termination_reason
simulation.delivery_window_sec / wall_span_delivery_sec
simulation.warmup{util_at_first_order, peds_at_first_order,
                  peds_waiting_at_first_order, boardings_per_min}
```

### 3.3 모델 측 배선 2가지

- **`model._ev_pax_cum`** — 현재 `_ev_busy_cum`·`_opex_cum`만 누적하므로(model.py
  366~368행) 창 제한 평균 재차 인원을 낼 수 없다.
- **`model._warmup_snapshot`** — 첫 주문 틱을 지나는 시점에 직전 300초 EV busy
  비율·보행자 수를 1회 스냅샷. KPI가 datacollector에 의존하지 않게 한다.

### 3.4 주 지표 승격 (인용 경로 전부)

`run.py`(콘솔 출력) · `analysis/plot_baseline.py` · `simulation/visualize.py` ·
`analysis/h0_baseline_stats.py`(이미 `_orderspan` 사용 → `_delivery`로 통일) ·
논문 인용. `utilization`은 **진단용으로 강등**한다.

### 3.5 심사자 오해 방지 (겸사겸사)

`utilization`은 DOORS+MOVING+호출 있는 IDLE의 **시간 비율이지 적재율이 아니다.**
실측 평균 재차 인원은 4대 합계 3.2~4.7명(정원 60석). `mean_passengers_delivery`를
병기하고 KPI 정의 각주에 명시한다.

---

## §4. 게이트 (`analysis/verify_h0.py`): A1~A12 → **A1~A14**

| 검사 | 조치 |
|---|---|
| **A1** 주문 보존 | 잔여 보행자 0 단언(구 204~205행) → `delivery`면 **면제**(라이더 0은 A14 담당). `legacy_margin`이면 현행 유지 |
| **A8** 창 정합 | 구 627~652행 정책 분기. delivery: `clock_start == min(ORD) − warmup_sec`, `cap == max(ORD) + overrun`, `last_exit ≤ clock_end ≤ cap`, ped_end 검사 제거 |
| **A6·A11** EV 보존 | **정책 무관 항등식으로 교체** — `boardings − alights == 종료 시점 탑승 인원`. "빈 차/빈 큐" 조건은 drain_all에서만 |
| **A13** warm-up adequacy (신규) | ① `head_sec ≥ 600` ② `util_at_first_order ≥ **0.35** × utilization_delivery` ③ `peds_at_first_order > 0` ④ 스냅샷 head가 선언 창과 일치. **②③은 `arrival_rate_per_min > 0`일 때만 적용** |
| **A14** termination reason (신규) | `reason == 선언 정책`이고 `cap` 아님, 전 주문 배달·전 라이더 퇴장, `delivery_complete`면 **clock_end == 마지막 퇴장(±1틱)** |

**A13-② 임계값은 R8-c에서 분포로 확정한다 (2026-08-05 개정).** 초판은 §1.1의
**8시드 평균**(600초→0.771, 배달창 0.85 → 비율 0.91)에서 0.6을 잡았는데, R8-b에서
**단일 시드 실측이 훨씬 흩어진다**는 것이 드러났다 — 같은 300초 lookback으로
`util_at_first_order`가 head=3600에서 **0.708**, head=600에서 **0.597**(seed 42),
비율로는 0.826 / **0.684**다(둘 다 통과하지만 여유가 초판 가정보다 얇다). 워밍업
궤적의 600초 구간 값이 0.54~0.89로 진동하므로 300초 추정량의 σ는 0.08~0.10이다.

→ **R8-c 착수 시 먼저 `head ∈ {0, 600}` × 10시드로 비율 분포를 측정**하고, 두 분포가
분리되는 지점에 임계를 놓는다. 후보 조정 2가지: ①lookback을 `min(head, 600)`으로
늘려 분산을 줄인다 ②임계를 0.5로 낮춘다(head=0은 비율이 0에 붙으므로 판정력은 유지).
**평균으로 임계를 잡으면 운 나쁜 시드에서 거짓 FAIL이 난다.**

A13-④를 게이트가 아니라 정보행으로 두는 이유는 §10-3.

`analysis/verify_baseline.py`의 대응 검사도 같은 계열로 정리한다.

---

## §5. 테스트

**신규 2종**

- `tests/test_termination_policy.py` — 두 정책의 종료 사유·틱수, `K==0` 축퇴, cap
  트립, **prefix 성질**(같은 시드에서 delivery 종료 시점까지 legacy와 상태 동일)
- `tests/test_warmup_gate.py` — A13이 warmup 0/300/600에서 fail/pass/pass 하는지 +
  뮤테이션 감도

**개정 4종**

| 파일 | 무엇이 | 조치 |
|---|---|---|
| `test_kpi_window.py` 56~59행 | 동결 `utilization` 상수 4개 | **legacy 정책으로 명시 핀**(이 테스트 목적이 "full-window 필드 불변") |
| `test_scenario_window.py` | `ped_end`·cap 산식 단언 | 정책별 파라미터화 |
| `test_vv_extreme.py` 493~499행 | `RUSH_OVERRUN_SEC=900`의 근거("cap을 트립시키는 건 보행자 배출")가 **무효화** | 재측정 후 상수·주석 개정 |
| `test_h0_frozen_snapshot.py` | 재생 파라미터 | 스냅샷별 정책 명시(pre_basement=legacy, baseline=delivery) |

**골든패스 2종**은 `arrival_rate_per_min=0`이라 거동 불변 예상 — 종료 시점만
바뀐다. 상수 재확인만 하고 **그래프 조회로 바꾸지 않는다**(HANDOFF §3.5).

**`simulation/app.py` 동반 수정**: 현재 `scenario_window`를 넘기지 않아 레거시
고정창으로 돌고 있다(81~88행). `window_policy`를 명시 전달해 앱과 논문 트랙을
일치시킨다 — §7의 V2-VISUAL 재서명과 연결된다.

---

## §5.2 R8-g — 수요 프로파일 가시성 (사용자 제기 2026-08-05)

### 진단: 모델은 정상, **가시성이 결함**이다

사용자가 "프로파일을 uniform ↔ bottom으로 바꿔도 결과가 같다"고 보고했다. 3중으로
확인한 결과 **모델은 완전히 정상**이다.

| 확인 경로 | 결과 |
|---|---|
| 동결 결과 JSON 3종 | 층분포 2..10F가 확연히 다름 — uniform `[3,4,3,5,9,10,4,7,5]` / bottom_heavy `[7,7,17,4,4,6,3,0,2]` / top_heavy `[0,2,0,5,2,5,17,8,11]` |
| 모델 직접 생성 | `floor_demand.probs`가 config의 프로파일과 일치, 같은 `floor_seed=42`에서도 층분포가 다름 |
| **앱 Reset 경로 재현** | mesa `do_reset()`이 하는 `type(model)(**model_params)`를 그대로 재현 → 위와 동일하게 다름 |

게이트도 이미 있다 — **A9 `check_floor_profile`**이 provenance에서 (floor, office,
mode)를 재유도해 정확 일치를 요구하고, `_gof`가 관측 히스토그램 대 `floor_probs`의
카이제곱을 낸다. 모델 층에서 프로파일이 무시되면 A9가 즉시 잡는다.

### 그러면 무엇이 문제인가 — 표시 계층에 게이트가 없다

1. **`etc/building_10f_layout.html`은 수요를 표현할 수단이 아예 없다.** 이 파일은
   `META`(층수·복도 길이·사무실 위치·EV)만 하드코딩한 **정적 기하 도면**이고, 유일한
   컨트롤은 **층 선택 버튼**(B2~10F 평면도 전환)이다. 시뮬레이션도 주문도 없다.
   → **구현이 잘못된 게 아니라 그 기능이 부재**한다. 다만 이름·성격상 사용자가
   수요를 확인하러 갈 만한 자리라, 부재 자체가 오해를 만든다.
2. **앱에서 프로파일 변경은 Reset을 눌러야 적용된다.** mesa 3.5.1의 `do_reset()`만이
   모델을 재생성한다(solara_viz.py 578~598행). Select 변경은 reactive dict만 갱신하고
   **돌고 있는 모델은 그대로**다. 이 사실이 `app.py` docstring에만 있고 **UI에는
   전혀 표시되지 않는다.**
3. **Reset을 눌러도 눈으로 구분하기 어렵다.** 수요에 의존하는 유일한 시각 요소가
   `draw_cross_section`의 **미인도 주문 마커**(visualize.py 210~212행)인데, 이는
   *현재 미배달분*만 그리므로 K50에서는 동시에 몇 개뿐이다. **현재 적용 중인
   프로파일 표시도, 누적 층별 분포도 없다.**

### 조치 (R8-g)

| # | 대상 | 내용 |
|---|---|---|
| ① | `simulation/app.py` | `window_policy`/`scenario_window` 명시 전달(§5 기존 항목과 통합) + 사이드바에 **"변경은 Reset 후 적용" 안내 문구** |
| ② | `simulation/visualize.py` | **층별 수요 패널 신설** — 현재 모델의 설계 확률(`floor_demand.probs`)과 실제 주문 층 히스토그램을 나란히, 상단에 **현재 프로파일·창 정책 배지**. 프로파일 적용 여부가 한눈에 보인다 |
| ③ | `etc/building_10f_layout.html` | config `demand.floor_profiles`를 `META`에 미러링하고 **프로파일 토글 + 층별 가중치 막대**를 평면도 옆에 추가. 시뮬 결과가 아니라 **설계 가중치**임을 라벨에 명시 |
| ④ | `tests/test_visualize.py` | **회귀 고정** — 프로파일 3종이 서로 다른 층 히스토그램을 만든다는 단언. 이번 사건을 재발 방지로 박는다 |

**③의 성격 주의**: 정적 도면은 시나리오·시드와 무관해야 하므로 **설계 가중치만**
표시하고 실측 분포는 넣지 않는다. 실측은 ②(앱)의 몫이다. 둘을 같은 화면에 섞으면
"도면이 특정 run을 대표한다"는 더 나쁜 오해를 만든다.

---

## §6. 재실행·재동결

1. **`archive/h0_v2_frozen/`에 현행 동결본 전체 복사** — git 미사용이라 이 복사가
   v2 수치의 유일한 이력이 된다(R0의 `archive/h0_v1/`과 같은 취급, **읽기 전용**).
2. `results/baseline_h0_*` 4종 재생성(delivery 정책).
3. `results/pre_basement/` 4종은 **재생성하지 않고**,
   `test_nobasement_replay_matches_pre_basement_snapshot`이 green인지로 무변화를 증명.
4. `results/h0_stats/`는 primary 티어(20 시나리오·60 run) 상태로 재생성.

**신규 실험 2종 정식화**(이번 변경의 정당화 근거, 이미 측정 완료 → 정식화만):

- `experiments/vv_warmup_bias.py` → `results/vv/warmup_bias.csv` (§1.2)
- `experiments/vv_window_compare.py` → `results/vv/window_compare.csv` (§1.3)

둘 다 `CORPUS_SCRIPTS` 가드에 등재한다(W5c `vv_balance.py` 전례).

---

## §7. 재검증 배터리 (V21)

### 7.1 비교 도구를 먼저 선언한다

비트 동일성이 **원리적으로 불가능**하므로(§0), KPI를 세 그룹으로 사전 선언하고
각각 다른 판정을 건다. 이걸 먼저 못박지 않으면 "값이 달라진 것"이 결함인지 의도인지
사후에 구분할 수 없다.

| 그룹 | KPI | 합격 기준 |
|---|---|---|
| **I. 불변이어야 함** | T_e2e, T_lobby, W_EV, SLA율, n_by_mode, lobby_cost, rider_wait | 구/신 **30시드 CI95가 겹칠 것**. 안 겹치면 결함 |
| **II. 구조적으로 변해야 함** | ticks, wall_span, `utilization`(full), pedestrian n_spawned/n_completed, termination_reason | **방향까지 사전 선언**: ticks **−40%**(R8-a 실측 K50_1 10,612→6,318; 시나리오별 폭은 배터리에서 확정), `utilization` 상승해 `utilization_delivery`로 수렴, `n_in_building_at_end` > 0, `termination_reason == "delivery_complete"` |
| **III. 정의상 불변** | `utilization_orderspan`, opex(라이더 체류 중에만 적산) | 통계적 동일 |

### 7.2 단계 매핑

| 구 단계 | 재실행 | 이유·변경점 | 예산 |
|---|---|---|---|
| **W1 V2-AUD** | ✅ 필수+개정 | A1·A8 개정, A13·A14 신설 → **A1~A14**. 감사 스윕 28 run | ~2분 |
| **W2 V2-GP** | ✅ 확인 | 보행자 0이라 거동 불변 예상. 손계산 상수 유지 확인 | 초 단위 |
| **W3 V2-ALL28** | ✅ 필수 | 84 run + 감사 28 → 새 정본 수치 | ~2.3분 |
| **W4a V2-EXT** | ✅ 필수+개정 | **드레인 예산 근거 무효** — 보행자가 더는 종료를 게이트하지 않음. `RUSH_OVERRUN_SEC` 재측정 | ~5분 |
| **W4b V2-MONO** | ✅ | 6방향 단조성 재확인, 130 run | ~3분 |
| **W5a DECOMP / W5b FACE** | ✅ | 그룹 I이므로 **값이 같아야** 정상 | ~3분 |
| **W5c BAL / W5d EVSEL** | ✅ | 배경이 종료까지 계속 생성되므로 후반 분포 변화 가능 | ~4분 |
| **W5e DET/VAR** | ✅ **핵심** | 그룹 I 판정의 **유일한 측정도구**. 구·신 840 run씩 | **~46분** |
| **W6 TIER** | ✅ | 티어 3종 실행 확인 | ~3분 |
| **W6 WIN** | 🔄 **재정의** | legacy vs scenario_window → **legacy_margin vs delivery** 비교로 교체 | ~5분 |
| **W7 CMP** | 📝 문서 | v1↔v2 비교 노트에 **v2.1 열 추가** | — |
| **W7 VISUAL** | 🔶 **부분 재서명** | 기하 6항목 불변 → 면제. 거동 8항목 중 **종료 직후 화면·배경 지속 생성** 관련만 재관찰(+ app.py 수정 확인) | 사용자 30분 |
| **W8 SNAP/DOC** | ✅ 필수 | baseline 4종 재동결 + pre_basement 무변화 증명 + 보고서 개정 | ~10분 |

**총 예산**: 계산 75~85분 + 전체 pytest(437→약 450건) + 사용자 육안 30분 + 문서.

---

## §8. 모델·effort 배정

> **Fable 전면 미사용**(사용자 확정 2026-08-03, 잔여 크레딧 0). 구 Fable 배정
> 구간은 **오퍼스 `max`**로 대체한다. effort 사다리 `low < medium < high < max`.
> **Escalation**: 같은 테스트·게이트 2회 실패 → 모델 또는 effort **1단계 상향**.
>
> **실행 주체 주의**: 아래 표는 **각 단계가 요구하는 난도 기준과 재검증 강도**의
> 선언이다. 서브에이전트 위임은 **사용자의 명시 지시가 있을 때만** 한다(현재 지시
> 없음) — 지시가 없으면 세션(오퍼스 5)이 배정 effort에 맞춰 직접 수행하고, 아래
> "독립 재검증" 열의 게이트를 별도로 재실행해 자기검증한다.

### 8.1 개정 단계 (R8)

| Step | 내용 | 난이도 | 모델 | effort | 독립 재검증 | 근거 |
|---|---|---|---|---|---|---|
| **R8-0** | 계획서 신설 + 동결본 백업 | 하 | 세션(오퍼스) | medium | 백업 파일 수·크기 대조 | 정본 문서·이력 보존 |
| **R8-a** | 창·종료 스위치 | **상** | **오퍼스** | **high** | 전체 스위트 437 green(동작 무변화 증명) | 종료 조건이 **전 KPI의 분모**를 정한다. legacy 비트 동일성 유지가 동시 제약 |
| **R8-b** | KPI 재정의·가산 필드 | 중 | 오퍼스 | medium | 동결 스냅샷 4종 green | 창 인덱싱 off-by-one이 조용히 틀린 값을 만든다 |
| **R8-c** | 게이트 A13·A14 + A1·A8 개정 | **상** | **오퍼스** | **high** | 뮤테이션 감도 시험(임계 근방 3점) | 게이트가 틀리면 **정상을 결함으로, 결함을 정상으로** 판정한다 |
| **R8-d** | 테스트 신설 2 + 개정 4 | 중 | 소넷 | medium | 세션이 뮤테이션 감도 재확인 | 기계적이나 감도 없는 테스트는 무가치 |
| **R8-e** | 재실행·재동결 | 하 | 소넷 | medium | 세션이 구조 비교(volatile 키 제외) | 배치 실행. **`cmp`/`md5sum` 금지**(W8 교훈) |
| **R8-f** | `baseline_10f.yaml` 정책 전환 | 중 | **세션(오퍼스)** | **high** | 사용자 확인 | **되돌릴 수 없는 지점**. `max_overrun_sec: 7200` 동반 필수(§10-1) |
| **R8-g** | 수요 프로파일 가시성 (§5.2) | 중 | 오퍼스 | medium | 프로파일 3종 육안 대조 + 회귀 테스트 | 모델은 정상이고 **표시 계층에만 게이트가 없다.** 판단은 "무엇을 보여야 오해가 안 생기는가"라 소넷 부적합 |

### 8.2 재검증 단계 (V21)

| Stage | 항목 | 난이도 | 모델 | effort | 근거 |
|---|---|---|---|---|---|
| V21-W1 | AUD A1~A14 | 상 | **오퍼스** | **high** | 이후 전 실험의 사후 게이트 |
| V21-W2 | GP 상수 유지 확인 | 중 | 오퍼스 | medium | 그래프 유도 금지 제약 유지 |
| V21-W3 | ALL28 배터리 | 하 | 소넷 | medium | 배치 실행·CSV 집계 |
| V21-W4a | EXT + RUSH 상수 재측정 | 중 | 오퍼스 | medium | 드레인 예산 근거가 무효화됨 — 재설계 판단 |
| V21-W4b | MONO | 하~중 | 소넷 | medium | 러너 재사용 |
| V21-W5a·b | DECOMP·FACE | 하~중 | 소넷 | medium | 그룹 I 확인 |
| V21-W5c·d | BAL·EVSEL | 중 | 오퍼스 | medium | 배경 지속 생성의 분포 영향 판정 |
| V21-W5e | DET·VAR | 하(실행) | 소넷 medium + **세션 해석** | — | 실행은 기계적이나 **그룹 I 판정의 유일 도구** — 해석은 위임 부적합 |
| V21-W6 | TIER · WIN 재정의 | 하~중 | 소넷 | medium | WIN은 비교 축이 바뀌므로 설계 확인 필요 |
| V21-W7 | CMP + VISUAL(사용자) | 중 | **세션(오퍼스)** | **high** | 연구 서사 판단 — 위임 부적합 |
| V21-W8 | SNAP → DOC → 리포트 | 중 | 오퍼스 high + **세션 독립 재검증** | — | 동결·소탕·집계 |
| V21-NEW | WARMUP·WINDOW 실험 정식화 | 중 | 오퍼스 | medium | 이미 측정 완료, 스크립트화·가드 등재 |

---

## §9. 실행 순서와 단계 게이트

| # | 단계 | 완료 게이트 |
|---|---|---|
| 0 | 계획서 + `archive/h0_v2_frozen/` 백업 | 백업 무결성 확인 |
| 1 | R8-a (`legacy` 기본, `delivery` 미사용) | **전체 스위트 437 green** — 이 시점엔 동작이 하나도 안 바뀌어야 함 |
| 2 | R8-b KPI 가산 | 동결 스냅샷 4종 green(가산만이므로) |
| 3 | R8-c 게이트 | legacy 경로에서 A1~A14 전건 PASS |
| 4 | **R8-f 정책 전환** | **baseline 4종 RED 전환 — 예상된 것.** `pre_basement` 4종은 **green 유지 필수** |
| 5 | R8-d 테스트 + **R8-g 가시성** | 신규 2종 green, 개정 4종 green, 프로파일 3종 육안 구분 가능 |
| 6 | R8-e 재동결 | 그룹 II 방향이 §7.1 사전 선언과 일치 |
| 7 | V21 배터리 | 그룹 I CI 겹침, A1~A14 전건 PASS |
| 8 | 문서 개정 | HANDOFF_v2 / plan_h0_revision / plan_h0v2_verification / research_plan_scie 결정 #23~#25 / phase_A~D 종료조건 |

**4단계가 되돌릴 수 없는 지점.** 그 전까지는 전부 가산·무해 변경이라 언제든 중단
가능하다. 4단계 진입 전 **사용자 확인 필수**.

---

## §10. 사전에 밝혀 둔 위험 3가지

1. **cap 산식 변경**(`ped_end + overrun` → `max(ORD) + overrun`)으로 여유가 크게
   줄어든다. **⚠️ 2026-08-05 정정** — 이 계획서 초판은 "마지막 배달은 max(ORD) 이후
   약 1,000초"라고 적었으나 **실측은 2,346~3,496초**다(마지막 주문도 cook 평균
   ~1,050초 + street + 건물 내를 거치므로 당연하다). 계산: `last_exit − max(ORD)` =
   K50_1 **2,346** · K100_1 2,829 · K200_1 2,634 · **K300_4 3,496**.

   따라서 `max_overrun_sec = 3600`이면 K300_4의 cap 여유가 **104초**밖에 안 남아
   시드만 바뀌어도 cap 트립이 난다. **delivery 정책 config는 `max_overrun_sec:
   7200.0`을 선언해야 한다**(R8-f 필수 항목). 7200에서 K50_1 실측 여유 4,854초.
   legacy 경로는 `ped_end + overrun`이라 이 값을 올려도 안전 여유만 늘 뿐이다.
   **W4a에서 러시 조건으로 재확인**한다.
2. **보행자 KPI 절단** — 종료 시점에 건물 안에 있던 보행자가 `ped_done_log`에 안
   들어가 `ev_wait_mean`이 미세하게 하향 편향된다. **R8-b 실측(K100_1·seed 42):
   5명 / 890명 = 0.56%** (초판이 적은 0.15%는 legacy의 긴 run 기준이었다 — delivery
   정책은 run이 짧아 총 보행자 수가 1,350→890으로 줄어 비율이 올라간다).
   `n_in_building_at_end`로 규모를 매 run 기록하고, 논문이 보행자 대기를 인용한다면
   배달창 제한값을 쓴다.
3. **초반 10% 주문은 워밍업과 무관하게 계속 낙관적이다**(실측: head 7,200초에서도
   W_EV 17.0 vs 전체 22.8). 이건 초기화 편향이 아니라 **점심 피크 주문 램프**
   때문이며, A13-④를 게이트가 아닌 정보행으로 두는 이유다. 논문에 "초반 주문이 빠른
   것은 모델 아티팩트가 아니다"를 명시해야 심사에서 방어된다.

---

## §11. 진행 로그

| 날짜 | Step | 배정 | 내용 | 게이트 |
|---|---|---|---|---|
| 2026-08-05 | 실측 3종 | 세션(오퍼스/high) | 워밍업 궤적·머리 분리 스윕(112 run)·4창 비교(12 run) → §1 | — |
| 2026-08-05 | R8-0 | 세션(오퍼스/medium) | 이 계획서 신설 + `archive/h0_v2_frozen/` 백업(115파일/54MB, `diff -r` 무차이) + HANDOFF_v2 §0 갱신 | ✅ 완료 |
| 2026-08-05 | **R8-a** | 세션(오퍼스/high) | `model.py`: `window_policy`/`warmup_sec` 도입, 창 분기, `_pipeline_empty`/`_delivery_complete`/`_carriers_settled` 신설, `_check_termination` → cap + 정책 2분기, `termination_reason` 기록. H1~H3는 `_carriers_settled` docstring에 **기록만**(코드 미구현) | ✅ **437 passed / 3 skipped — 착수 전과 동일**(동작 무변화 증명). 독립 재검증: ①기본값 legacy 확인 ②delivery 스모크 = `reason=delivery_complete`·50/50 인도·**종료 시점 == 마지막 라이더 퇴장(차 0s)**·cap 여유 4,854s ③가드 2종(잘못된 정책명·delivery+`scenario_window=False`) ValueError |

**R8-a에서 새로 드러난 것 (§10-1 정정 사유)**: cap 여유가 계획서 초판 가정보다
훨씬 얇다. `last_exit − max(ORD)`가 **2,346~3,496초**(초판은 "약 1,000초"로 오기)라
`max_overrun_sec = 3600`이면 K300_4 여유가 **104초**다. → **R8-f에서 delivery config에
`max_overrun_sec: 7200.0` 선언 필수**로 등재.

| 2026-08-05 | **R8-b** | 세션(오퍼스/medium) | `model.py`: `_ev_pax_cum`·`first_order_sec`·`_warmup_snapshot`(+`_take_warmup_snapshot`). `kpi.py`: `_delivery_span` + **가산 필드 17종**(EV별 `utilization_delivery`·`mean_passengers_delivery`, `opex_running_krw_delivery`, `n_in_building_at_end`, simulation 6종 + `warmup` 블록) | ✅ **437 passed / 3 skipped**. 독립 검산: ①4대 전부 창 인덱스 **손계산 1e-12 내 일치**(양 정책) ②`utilization_delivery ≈ utilization_orderspan`(0.857/0.857, 0.872/0.873 — 예측대로) ③**동결본 키 전건 대조 변경 0건 / 신규 17종**(가산 규약 준수) ④`opex_delivery == opex_full`(라이더 체류 중에만 적산되므로 — 배달창이 옳은 창임을 뒷받침) |

| 2026-08-05 | **R8-c** | 세션(오퍼스/high) | `verify_h0.py`: **A13**(warm-up adequacy)·**A14**(termination reason) 신설, **A1·A6·A8·A11 정책 분기**, 모듈 독스트링 A1~A14 개정. `test_verify_h0.py` SKIP 계약 개정 | ✅ **437 passed / 3 skipped**. 뮤테이션 배터리 **13종 전건 통과**(정상 4 + A13 3 + JSON 주입 6). ruff 신규 유입 0 |

| 2026-08-05 | **R8-f** | 세션(오퍼스/high) | `baseline_10f.yaml` → `window_policy: delivery` · `warmup_sec: 600` · `max_overrun_sec: 7200`. 부수: `scenario_window` 기본값을 **센티널 `None`**으로 변경 | ✅ **게이트 충족** — `pre_basement` 2건 **green 유지**(§3.6 잠금 무사), baseline 4종 RED(예상). 잔여 RED 22건은 전부 R8-d/R8-e 대상으로 분류 완료 |

| 2026-08-05 | **R8-d** | 세션(오퍼스/medium) | RED 18건을 정책 인지형으로 개정 — `test_scenario_window`(LEGACY_CFG 핀 + 모순 가드 테스트 신설), `test_kpi_window`(legacy 핀), 골든패스(`warmup_sec` 동반 설정), `test_agents`·`test_h0_endtoend`·`test_dynamic_pool`·`test_vv_evsel`·`test_vv_extreme` | ✅ **436 passed / 4 failed**(잔여는 R8-e 재동결 대상 스냅샷뿐). 스위트 3분40초 → **2분38초** |
| 2026-08-05 | **R8-g** | 세션(오퍼스/medium) | `visualize.FloorDemandPanel` 신설(설계 확률 vs 실제 층 히스토그램 + 프로파일·정책 배지 + Reset 안내), `app.py` 라벨·주석, `building_10f_layout.html`에 **설계 가중치 토글** 추가, 회귀 테스트 2종 신설 | ✅ 13 passed |

| 2026-08-05 | **R8-e** | 세션(오퍼스/medium) | 픽스처 7종 재동결(delivery) + `results/h0_stats/` primary 재생성(60 run) + 음성 테스트 2건 수정 | ✅ **440 passed / 3 skipped — 전면 green.** `pre_basement` 2건 green 유지. **그룹 II 6개 항목 전건 사전 선언과 일치** |

**R8-e 재동결 결과** (`archive/h0_v2_frozen/` 대비):

| 픽스처 | ticks | `utilization`(full) | `utilization_delivery` | 잔여 보행자 |
|---|---|---|---|---|
| K50_1 uniform | 10,612 → **6,318 (−40.5%)** | 0.800 → 0.816 | 0.834 | 15 |
| K100_1 uniform | 10,733 → 6,965 (−35.1%) | 0.815 → 0.852 | 0.872 | 5 |
| K200_1 uniform | 10,870 → 6,857 (−36.9%) | 0.846 → 0.895 | 0.920 | 7 |
| K300_4 uniform | 10,848 → 7,678 (−29.2%) | 0.857 → 0.886 | 0.906 | 1 |
| K50_1 bottom_heavy | 10,601 → 6,327 (−40.3%) | 0.800 → 0.824 | 0.843 | 15 |
| K50_1 top_heavy | 10,615 → 6,311 (−40.5%) | 0.803 → 0.844 | 0.866 | 13 |
| K50_1 v5 매핑 | 10,611 → 6,393 (−39.8%) | 0.709 → 0.815 | 0.833 | 12 |

`results/h0_stats/`(20 시나리오 × 3 시드)도 재생성 — ticks 평균 **−37.6%**,
`delivered` 대조 60/60 일치(그룹 I 불변량 확인).

**재동결하지 않은 것 2종**: `results/pre_basement/`(legacy 경로 잠금 — green 유지가
곧 증명) · `results/baseline_h0_K50_1.json`(static + legacy window 픽스처. delivery
config에서는 명시적 `scenario_window=False`가 거부되므로 재생성 불가이고, R8 이전
정적 경로의 기록으로 남긴다).

**⚠️ 재동결이 음성 테스트 하나의 이빨을 뽑았다 (수정 완료).**
`test_a6_negative_residual_passengers`는 `ev1_pax[-1] = 2`를 주입해 "차가 비어 있지
않다"로 A6를 떨어뜨렸는데, 이제 **잔여 탑승이 정상**이라 그 리터럴 2가 실제 잔여와
우연히 일치해 **뮤테이션이 무효화**됐다. 진실 대비 상대 교란(`+= 1`)으로 바꿔 항등식
자체를 깨도록 고쳤고, A11도 함께 떨어지는지 확인한다. 같은 이유로
`test_frozen_mapping_run_skips_a9_and_passes`의 "비스킵 10개" **매직 넘버를 스킵
집합 단언으로 교체**했다 — 게이트가 늘 때마다 숫자만 키우면 진짜 신규 스킵이 숨는다.

**R8-d에서 계약을 고친 원칙**: "완료"를 단언하던 것을 **"보존"**으로 바꿨다. 약화가
아니라 정확화다 — 예: `ped_spawned == len(ped_done_log)` →
`ped_spawned == len(ped_done_log) + 건물 내 잔여`, `boards == alights` →
`boards − alights == 종료 시점 탑승 인원`, `pool.free == initial` →
`free + returning == initial`. 셋 다 drain_all에서는 원래 진술과 **동치**다.

**⚠️ R8-d가 실측으로 뒤집은 것 2가지**

1. **60명/분 배경은 이제 종료하지 않는다.** 배경 컷오프를 없앤 결과, EV 용량을 넘는
   부하는 **영원히 배출되지 않는다** — overrun 7200 s·28800 s 양쪽에서 cap 트립,
   건물 내 보행자가 **3,614 → 10,072명으로 발산**. legacy는 `ped_end`에서 생성을
   끊어 백로그가 빠졌기 때문에 완주했다. 그래서 `zero_vs_x10`(60/분)을
   **`zero_vs_saturated`(30/분)**으로 교체했다. 30/분은 완주하면서도 4대 전부
   가동률 **1.000**(대조군 0.092)이라 대비는 오히려 선명해졌다. `SATURATING_PED_RATE`
   상수에 이 한계를 기록해 뒀다.
2. **`RUSH_OVERRUN_SEC` 900 → 7200.** 구 근거("보행자 백로그 150~180 s, 라이더는
   ped_end보다 726 s 먼저 끝남")는 **양쪽 다 무효**가 됐다 — cap 기준점이 ped_end에서
   **마지막 주문**으로 옮겨졌고, 종료가 더는 배경을 기다리지 않는다. 재실측:
   30/분에서 마지막 퇴장이 마지막 주문 **+2,796 s**(K50_1 +2,468 s) → 7200은 ×2.6 여유.

**⚠️ `test_tick_convergence`는 애초에 잘못 재고 있었다 (R8-d에서 발견·수정).**
dt 1.0 대 0.5를 **시드별로** 비교했는데, dt를 바꾸면 보행자 RNG 정렬이 달라져
같은 시드 쌍이 사실상 **독립 실현 2개**가 된다. 실측(K50_1, 5시드):

| | 값 |
|---|---|
| 시드별 \|Δt_lobby\| 최대 | **18.99 s** (13 s 봉투 초과 → RED) |
| **5시드 평균 차** | **2.19 s** ← 진짜 이산화 편향 |

세 KPI·두 시나리오 전부 평균 차가 **1.1~2.2 s**로 봉투의 1/6이다. 그래서 수렴 주장은
**시드 평균 차**로 단언하고, 총체적 이산화 오류를 놓치지 않도록 시드별 봉투(×3)를
느슨하게 남겼다. 워밍업 단축이 분산을 키운 것이 **아님**도 확인했다 — 머리 길이별
t_lobby SD가 3.29~7.06으로 무추세이고 최대값이 오히려 head=3600이다.

**⚠️ R8-f에서 설계를 하나 고쳤다 — `scenario_window` 가드가 과잉이었다.** 전환 직후
**56 failed / 21 errors**가 났는데, 그중 약 55건이 "`scenario_window`의 기본값 `False`에
의존하던 호출부"였다. `test_agents`·`test_elevator_scan`·`test_dynamic_pool`·
`test_h0_endtoend` 같은 **창과 무관한 단위 테스트들이 모델을 만들 때 기본값을 쓰고
있었고**, delivery config와 충돌해 전부 ValueError로 죽었다.

`scenario_window`는 **`legacy_margin` 정책 전용 스위치**(고정 점심창 ↔ 데이터 유도
±margin)이고, delivery 정책은 **항상** 주문 데이터에서 창을 유도하므로 이 인자가
애초에 적용 대상이 아니다. 그래서 기본값을 **`bool | None = None`(센티널)**로 바꿨다:

- `None`(기본) → **정책이 결정**. legacy_margin이면 `False`(R8 이전 기본값 그대로),
  delivery면 데이터 유도.
- **명시적** `False` + delivery config → **여전히 ValueError**. 명시적 모순은 조용히
  덮지 않는다(`run.py --legacy-window`, `vv_window_bias.py`가 이 경로).

이 한 줄로 **56 → 22**가 됐고, 부수 효과로 **`app.py`가 자동으로 논문 트랙과
일치**한다(§5의 "앱이 레거시 창으로 돈다" 항목이 여기서 해소됐다).

**잔여 RED 22건 분류** (전부 예상된 계약 변경, 모델 결함 0건):

| 군 | 건수 | 내용 | 처리 |
|---|---|---|---|
| A 재동결 | **4** | `test_h0_frozen_snapshot` — diff가 `clock_start` 37800→40800(=첫 주문−600), `ped_end`=cap로 **정확히 예상대로** | R8-e |
| B 배경 보행자 절단 | **11** | drain-all 계약을 단언하는 것들 — `pedestrians_all_completed`(860 spawned/855 completed), `elevator_conservation`(240 승차/239 하차 = 1명 탑승 중), `kpi_summary_complete`, `mid_run_conservation_per_type`(BIKE 3명 복귀 중), `evsel_on_smoke`(미탑승 이벤트 `observed_wait_sec=None`), `vv_extreme` 5종, `test_all_agents_instantiate` | R8-d |
| C legacy 창 계약 | **5** | `test_scenario_window` 4종 + `test_kpi_window` 동결 상수 | R8-d (legacy config로 핀) |
| D 창 시작 상수 | **2** | `test_vv_golden_path::test_golden_dynamic` — `clock_start` 41340(첫주문−margin) → 40800(첫주문−600) | R8-d |

**확인된 것 — `analysis/vv_evsel.py`는 이미 안전하다.** 89행이
`observed_wait_sec is not None`으로 절단 이벤트를 거르고 있어, W5d harm 추정이
절단 편향을 먹지 않는다. 만약 걸러지지 않았다면 미탑승 대기를 0으로 세어 harm이
과소평가됐을 것이다.

**R8-c에서 임계값을 분포로 확정**(n=80: K100_1·K300_4 × head {0,300,600,900} × 10시드,
산출물 `scratchpad/a13_threshold.csv`):

| head | ratio 평균 | σ | 최소 | 최대 |
|---|---|---|---|---|
| **0** | **0.000** | 0.000 | **0.000** | **0.000** |
| 300 | 0.732 | 0.150 | 0.498 | 1.037 |
| 600 | 0.859 | 0.125 | 0.628 | 1.053 |
| 900 | 0.851 | 0.130 | **0.554** | 1.032 |

냉각 건물은 **정확히 0.000**(20 run 전건 — 보행자가 없으니 EV가 아예 안 움직인다)이라
두 모집단이 구간 (0.000, 0.554] 전체로 분리된다. **임계 = `WARMUP_RATIO_FLOOR = 0.35`**
— head=600 평균에서 4σ 아래라 거짓 FAIL이 나지 않고, 잡아야 할 실패(워밍업 누락·배경
스트림 정지)는 확정 적발한다. **초판의 0.6이었다면 head=900의 한 시드(0.554)가 거짓
FAIL이었다.**

**⚠️ R8-c가 잡은 진짜 결함 — A6/A11이 정책을 모르고 있었다.** delivery 정책은 마지막
*라이더*가 나갈 때 멈추므로 **배경 보행자가 EV에 타고 있는 채로** 종료될 수 있다.
그러면 `boardings != alights`가 되어 A6·A11이 **정상 run을 전건 FAIL**시켰다(실측
EV1 228 대 226). 부등호로 완화하면 검사가 아무것도 안 하게 되므로, **더 강한
항등식으로 교체**했다:

```
boardings − alights == 종료 시점 탑승 인원 (model_vars ev{i}_pax[-1])
```

drain_all에서는 잔여가 0이라 기존 등식과 **같은 진술**이므로 동결 결과에 영향이 없고,
delivery에서는 보존 주장을 정확히 유지한다. 이 결함은 **뮤테이션 배터리가 아니었으면
4단계에서 전건 FAIL로 터졌을 것**이다.

**설계 판단 1건 — A13 경험적 항목의 적용 범위.** `arrival_rate_per_min == 0`이면 건물을
*데울 대상 자체가 없으므로* 경험적 두 항목(가동률 비율·보행자 존재)은 **적용 불가**로
두고, 구조·머리 길이 항목은 계속 살린다. 골든패스 픽스처와 보행자 0 극단 케이스가 이
경우다(전자를 빼먹어 `test_extreme_pedestrian_zero_vs_x10`이 한 번 RED가 됐다).
**통째 SKIP이 아니라 범위 축소**라는 점이 중요하다 — config가 7.5/분을 선언했는데
보행자가 안 생기는 진짜 고장은 여전히 적발된다.

**범위 조정 1건**: `tests/test_verify_h0.py`의 SKIP 계약 개정을 R8-d에서 당겨왔다.
"A12만 SKIP"을 단언하던 것을 **"픽스처가 그 필드를 실제로 안 가진 경우에만 A13/A14
SKIP 허용"**으로 바꿔, R8-e 재동결 뒤에는 두 게이트가 **자동으로 살아나도록** 했다.
기대 집합을 넓히지 않은 이유는 §3.4의 거짓 green 함정을 그대로 두지 않기 위해서다.

**R8-b 실측 부수 확인**: 평균 재차 인원 4대 합계 **3.23명 / 정원 60석(5.4%)**인데
시간가동률은 0.857 — §3.5의 "시간가동률 ≠ 적재율" 주장이 수치로 확인됐다.
delivery 정책 ticks는 K100_1에서 10,733 → **6,965(−35.1%)**.

**⚠️ R8-b가 드러낸 것 — A13 임계값을 평균으로 잡으면 안 된다.** 위 §4 개정 참조.

**설계 판단 1건 (초판 §2.2 대비 단순화)**: `K == 0` 축퇴 가드를
`_check_termination` 안에 넣지 않고 **생성자의 창 분기에서 `and orders` 조건으로**
처리했다. 주문이 없으면 애초에 `termination_policy`가 `drain_all`로 남아 legacy 창을
쓰므로, 틱마다 축퇴를 재검사할 필요가 없다. 판정 지점이 한 곳(생성자)으로 모인다.

---

## §12. 7·8단계 진행 로그 (2026-08-06)

실행 지시서 `etc/HANDOFF_r8_step78.md`. 서브에이전트 위임 **없이** 세션(오퍼스)이
§8.2 배정 effort에 맞춰 직접 수행하고, 게이트는 별도로 재실행해 자기검증했다
(§8 "실행 주체 주의" 규정대로 — 사용자의 위임 지시가 없었다).

### 콜드 스타트 게이트

| 검사 | 결과 |
|---|---|
| `pytest -q` | **440 passed / 3 skipped / 0 failed** (2회 독립 실행, 157.8 s / 158.8 s) |
| `verify_h0 baseline_h0_K50_1_uniform_s42.json` | **13 passed / 1 skipped(A12) / 0 failed** — A13·A14 포함 |

### 7단계 — V21 재검증 배터리

| # | 항목 | 결과 |
|---|---|---|
| 1·3 | **AUD + ALL28** | 배터리 **84/84**, 감사 스윕 **28/28**. A4 최소 slack **−0.367 s**(허용 1 tick), A9 p<0.05 **0/112**, skipped 집합 = {A12}만. 84 run 102.6 s |
| 2 | **GP** | 골든패스 14 + 극단 15 = **29 passed**(63.6 s). 손계산 상수 그대로 |
| 4 | **EXT** | 위에 포함. R8-d 재측정 상수(`RUSH_OVERRUN_SEC` 7200 · `SATURATING_PED_RATE` 30/분) 유효 |
| 5 | **MONO** | **6/6 PASS**, 130 run·132.5 s. dir6 사다리 23.85 → 35.78 → 42.25. dir5 fallback 감소는 `gate=False` 정보행(기지) |
| 6 | **DECOMP·FACE** | 잔차 **3.638e-12 s**(구본과 동일 자릿수). FACE = stairs PASS / slope CAUTION / slack CAUTION(위반 **0/15,600**, 최소 **12.27분**) / tlobby PASS(4.12→4.63분 단조) — **CAUTION 2건 다 v2와 같은 성격** |
| 7 | **BAL·EVSEL** | G1 max/min **1.177**(한계 1.5) · G2 **0.924~1.066**. evsel stale 52.95%, harm 상한 mean 28.81 s |
| 8 | **DET/VAR** | **그룹 I 30시드 CI95 15/15 겹침** (아래) |
| 9 | **TIER** | 20 / 8 / 28행. `--tier all`의 `tier` 열 = primary 20 + extreme 8, **보류 11개 0건**. 검사 후 `results/h0_stats/`를 primary로 복원 |
| 10 | **WIN 재정의** | 축 교체 완료(§12.1) |
| 11 | **NEW 2종** | 정식화 완료(§12.2) |
| 12 | **VISUAL** | `etc/checklist_visual_h0v2.md` **§6 신설** — 재검증 실행 시점(2026-08-06)에는 사용자 재서명 대기. **→ 2026-08-07 PASS 서명 완료**(K50_1 완주 관찰, 4항목 전건 기대 일치). 판정 원본은 §6.3 |
| 13 | **W8** | 동결 픽스처 **7/7 구조 동일**(2회 재생성 상호 + 디스크, volatile 키 제외·NaN 동치). `baseline_h0_K50_1.json`은 static+legacy 픽스처라 delivery config에서 재생 불가 → **의도적 SKIP**(§11 R8-e "재동결하지 않은 것 2종"과 일치) |

**그룹 I 판정 (본체)** — 구 = `archive/h0_v2_frozen/vv/variance_summary.csv`:

| KPI | K50_1 | K200_1 | K300_4 |
|---|---|---|---|
| T_e2e mean | +0.0% ✅ | −0.0% ✅ | −0.1% ✅ |
| T_e2e p95 | +0.1% ✅ | −0.1% ✅ | +0.1% ✅ |
| T_lobby mean | −0.3% ✅ | −0.6% ✅ | −0.5% ✅ |
| W_EV mean | −0.9% ✅ | −2.0% ✅ | −1.7% ✅ |
| rider_wait | 0.000 ✅ | 0.000 ✅ | 0.000 ✅ |

**15/15 CI95 겹침.** 추가로 `delivered`가 배터리 **112/112 run에서 구본과 완전 일치**한다
(창을 바꿔도 배달 결과 자체는 한 건도 안 바뀐다는 뜻).

### §12.1 W6 V2-WIN 축 재정의

구 축(`scenario_window` False ↔ True)은 delivery config에서 **ValueError로 실행 불가**다.
새 축 = **`window_policy` legacy_margin ↔ delivery**. 양팔 모두
`run_baseline(config_path=...)`로 돌리도록 임시 config 2벌을 생성한다
(`tests/test_kpi_window.py::_legacy_summary` 패턴). legacy 팔은 `max_overrun_sec: 3600`
(pre-R8 값) + `scenario_window=True`로 **R8 이전 논문 트랙을 정확히 재현**한다.

**구 결론("고정 창이 혼잡을 W_EV +37.8~53.3% 과소평가")은 폐기**하고 재산출했다.
그룹 I은 Welch \|t\| 0.16~0.68로 일치, 그룹 II는 사전 선언대로 이동
(ticks −29.2~−40.1%, `utilization` +4.3~+7.4%), 그룹 III는 \|t\| 0.90~1.96로 동일.

> **정직하게 남긴 관찰 1건**: 그룹 III의 부호가 3 시나리오 전부 양(+)이다. n=5에서
> 유의하지 않고, 30시드 그룹 I 판정이 W_EV에서 오히려 음(−)을 주므로 계통 편향으로
> 보긴 어렵다. **논문에 `utilization_orderspan`의 정책 간 차이를 주장하지 말 것.**

### §12.2 V21-NEW 2종

| 스크립트 | 규모 | 결론 |
|---|---|---|
| `experiments/vv_warmup_bias.py` | 7 head × 8 seed × 2 시나리오 = **112 run**·171.9 s | 배달 KPI **단조 추세 없음**(max z 0.49~2.58, 최대값도 사다리 중간의 비단조 융기). A13 비율은 head=0에서 **정확히 0.000**, head≥300에서 0.71~0.95 → 임계 0.35가 두 모집단 사이 |
| `experiments/vv_window_compare.py` | 4 시나리오 × 3 seed = **12 run**·18.4 s | 이용률 왜곡의 **워밍업 머리 4.566~7.486 %p**, ped_end 꼬리 −0.054~0.652 %p, `peds==0` **0.082~0.220 %p** |

**꼬리 고정을 스크립트가 자체 검사한다.** delivery 정책에서는 꼬리가 주문 데이터에
앵커되므로 `warmup_sec`는 순수 머리 knob이고, `check_tail_invariance()`가 매 실행
`ped_end` 불변을 단언한다(K100_1 52,100 s · K300_4 52,196 s 전 수준 동일). §5-1의
함정("`window_margin_sec` 단독 스윕은 머리·꼬리를 함께 움직인다")을 **구조적으로**
못 밟게 만든 것이다.

`vv_window_compare`는 **같은 run 안에서** 4창을 계산한다 — 종료를 앞당기는 것이 엄격한
prefix이므로 재시뮬레이션이 필요 없고, 4개 정책을 따로 돌렸다면 **서로 다른 보행자
실현 4개를 비교해 잡음을 재게** 됐을 것이다. 로컬 추정량이 `kpi.py`의 shipped 필드와
1e-9 내 일치하는지도 매 run 단언한다.

> ⚠️ **가드 등재 위치를 지시서와 다르게 했다.** 지시서 §3.3은 두 스크립트를
> `CORPUS_SCRIPTS`에 넣으라고 했으나, 그 가드는 소스에 **`== 28` 코퍼스 카운트 단언**과
> `scenario_tiers` import를 요구한다(`tests/test_scenario_tiers.py`). 두 스크립트는
> 대표 부분집합을 쓰므로 그 단언을 만들면 **거짓말**이 된다. 실제로 보호가 되는
> **`SUBSET_SCRIPTS`**(제외 시나리오 stem을 대표로 쓰지 않는지 검사)에 등재했다.

### 8단계 — 문서 개정

| 문서 | 무엇을 |
|---|---|
| `etc/HANDOFF_v2.md` | §0 상태·정본 목록, **§3.8 창·종료 규약 신설**(규약 7 → 8가지), §4에 R8 완료 기록, §6 파일 지도에 `plan_h0v21_window.md`·`archive/h0_v2_frozen/`·`note_kpiwin_convention.md` |
| `etc/verification_report_h0v2.md` | 상단 배너 + **§8 V21 재검증 신설**(§8.1 그룹 I 원표 ~ §8.8 전체 판정). §0~§7은 v2 기록으로 보존 |
| `etc/checklist_visual_h0v2.md` | **§6 R8 재서명 신설** — 재관찰 4항목(종료 직후 화면·배경 지속 생성·논문 트랙 창 표시·`FloorDemandPanel`), 기하 6 + 거동 6항목 면제 |
| `etc/plan_h0_revision.md` | §1 상단에 **창·종료는 R8 소관** 배너 |
| `etc/plan_h0v2_verification.md` | L2를 **A1~A14**로 확장 + **정책 분기 표**(A1·A6·A8·A11) + A13 임계 확정 근거 |
| `etc/research_plan_scie.md` | **결정 #23~#25 등재**, §7 판별력 한계에 **5(보행자 절단)·6(60/분 비종료)** 추가 + 주 지표 표기 규약, §5.1·§6 수치 갱신, §10 진행 로그 2행 |
| `etc/scie_phase/phase_A_robot_h1.md` | **H1 종료 조건** 신설(로봇 1F 로비존 IDLE 복귀) + A13/A14 승계 지침 |
| `etc/scie_phase/phase_B_h2_queue.md` | **H2는 분기 불필요** — AND가 자동 처리 + "완료가 아니라 보존을 단언하라" 경고 |
| `etc/scie_phase/phase_C_h3_locker.md` | **H3 미결 결정 등재** — `delivered` = 투입(권장) vs 수령, 대가 3가지 |
| `etc/note_kpiwin_convention.md` | 상단에 **확정 규약** 신설 — 창 3+1종, 주 지표 = `utilization_delivery`, 표기 규약 3가지 |

> **문서 letter 주의**: 지시서 §4는 H2를 `phase_C_*`, H3를 `phase_D_*`로 적었으나
> 실제 파일은 **H2 = `phase_B_h2_queue.md`, H3 = `phase_C_h3_locker.md`** 다
> (`phase_D_experiments_economics.md`는 실험·경제성). **내용 기준으로** 배치했다.

**주 지표 승격 (§4-1) — 표시 경로 4곳 전환 완료**

| 파일 | 무엇을 |
|---|---|
| `simulation/run.py` | 콘솔 `util(delivery)=..% full=..% pax=..`. 창 배너도 `window=delivery(warmup 600s)`로 — 구 `scenario±1h`는 delivery run에 대해 **거짓말**이었다 |
| `analysis/plot_baseline.py` | 제목에 delivery 가동률 + **어느 창인지 명시** |
| `simulation/visualize.py` | 라이브 패널 "가동률·재차·탑승·W_EV" + 보행자 행에 **건물내 잔여** 노출 |
| `analysis/h0_baseline_stats.py` | `ev{1,2}_util_os` → **`ev{1,2}_util_del`** + `ev{1,2}_pax_del` 신설, f3 무릎 그림 x축 라벨 정정 |

전부 **legacy 경로에서는 자동으로 full-window로 폴백**한다(delivery 창이 없으므로).
`tests/test_plot_baseline.py`에 스텁 갱신 + **창 라벨 회귀 테스트 신설**
(`test_ev_wait_title_quotes_the_delivery_window` — 두 정책 다 검사).

### 최종 게이트

| 검사 | 결과 |
|---|---|
| `pytest -q` (8단계 후) | §12 말미 참조 |
| 동결 픽스처 구조 비교 | 7/7 PASS |
| `results/h0_stats/` | primary 티어(20 시나리오·60 run)로 재생성 — 주 지표 열 교체 반영 |

**남은 것 1건**: `etc/checklist_visual_h0v2.md` §6 **사용자 육안 재서명**(4항목·30분).
Phase A 착수를 막지 않지만 논문 V&V 절의 마지막 빈칸이다.
