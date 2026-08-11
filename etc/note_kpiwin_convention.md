# V-KPIWIN — KPI 측정 윈도우 규약 (Stage V6 → **R8에서 확정**)

> ## ★ 확정 규약 (R8, 2026-08-06) — **§0~§5보다 이것이 우선한다**
>
> §4의 "사용자 결정 대기"는 **닫혔다**. 창은 **3+1종**이고 주 지표는
> **`utilization_delivery`** 다. 아래 §0~§5는 2026-07-11의 v1 측정 기록이며,
> 그 수치는 **2 EV·800 ㎡·지하 없음 건물**의 것이라 지금 인용하면 안 된다.
> 근거·재검증: `etc/plan_h0v21_window.md` §1.3 · `etc/verification_report_h0v2.md`
> §8.5 · 규약 요약 `etc/HANDOFF_v2.md` §3.8.
>
> ### 창 3+1종
>
> | 창 | 구간 | 용도 | 필드 |
> |---|---|---|---|
> | **warmup** | `[clock_start, 첫 ORD)` | **A13 게이트 입력** | `simulation.warmup.*` |
> | **delivery** | `[첫 ORD, 마지막 라이더 퇴장]` | ★ **주 지표 창** | `utilization_delivery`, `mean_passengers_delivery`, `opex_running_krw_delivery`, `wall_span_delivery_sec` |
> | **run (full)** | `[clock_start, clock_end]` | **진단용** (강등) | `utilization`, `opex_running_krw`, `wall_span_sec` |
> | **orderspan** | `[첫 ORD, 마지막 배달]` | **기존 동결 필드 — 정의·값 불변** | `utilization_orderspan`, `*_orderspan` |
>
> `delivery`와 `orderspan`은 **마지막 배달 ~ 마지막 라이더 퇴장(55~91 s)** 만큼만
> 다르다. 실측 차이는 소수 셋째 자리(±0.15 %p)이므로 **둘 중 어느 쪽을 쓰든 결론이
> 같다.** 그래도 `delivery`를 주 지표로 잡은 이유는 **종료 정의와 같은 사건**
> (마지막 라이더 퇴장)에 걸려 있어 창과 완료 조건이 한 문장으로 설명되기 때문이다.
> `orderspan`은 v2 동결 이력이 걸려 있어 **정의·값 그대로 보존**한다.
>
> ### 왜 `utilization`(full)이 강등됐나
>
> 분모에 **워밍업 머리**가 들어간다. 같은 run 안에서 창만 바꿔 정확히 귀속하면
> (`experiments/vv_window_compare.py`, 12 run):
>
> | 원인 | 기여 |
> |---|---|
> | **워밍업 머리** | **4.566 ~ 7.486 %p** ← 지배적 |
> | `ped_end` 가드 꼬리 | −0.054 ~ 0.652 %p |
> | `peds == 0` 종료 조건 | 0.082 ~ 0.220 %p |
> | orderspan 잔차 | −0.041 ~ 0.145 %p |
>
> **올바른 값은 이미 `utilization_orderspan`으로 계산되고 있었다** — 문제는
> `utilization`이 주 지표 자리에 있었던 것이다. §3의 "EV 가동률은 윈도우-강건"이라는
> v1 결론은 **2 EV 준-포화 건물에서만 성립**했고, 4 EV·지하 2층 건물에서는 머리가
> 5 %p를 만든다.
>
> ### 표기 규약 3가지 (논문·콘솔·그림 공통)
>
> 1. **주 지표 = `utilization_delivery`.** 표시 경로 4곳(`simulation/run.py` 콘솔 ·
>    `analysis/plot_baseline.py` · `simulation/visualize.py` 라이브 패널 ·
>    `analysis/h0_baseline_stats.py`)은 2026-08-06에 전환 완료. legacy 정책 run에는
>    delivery 창이 없으므로 **자동으로 full-window로 폴백**하고, 어느 창인지 라벨에
>    항상 표시한다.
> 2. **가동률은 적재율이 아니다.** DOORS + MOVING + 호출 있는 IDLE의 **시간 비율**이다.
>    같은 run의 평균 재차 인원은 4대 합계 **2.9~4.8명 / 정원 60석(4.8~8.0%)**.
>    `mean_passengers_delivery`를 **반드시 병기**할 것 — 심사자가 85%를 적재율로 읽는다.
> 3. **`opex`는 창 논쟁에서 자유롭다.** 라이더 체류 중에만 적산되므로
>    `opex_running_krw_delivery == opex_running_krw`(실측 일치)다. §3-3의 v1 결론이
>    여기서는 그대로 유효하다.
>
> ### 가산 규약은 유지된다
>
> R8-b가 추가한 17종 필드는 **전부 가산**이고 **기존 필드는 값·이름 불변**이다
> (동결본 키 전건 대조: 변경 0건 / 신규 17종). V6-KPIWIN이 세운 이 관례가 R8에서도
> 지켜졌기 때문에 `pre_basement` 잠금이 살아남았다.

# (이하 원문 — 2026-07-11 v1 측정 기록, 인용 금지)

# V-KPIWIN — KPI 측정 윈도우 규약 (Stage V6, 병기 구현 + 규약 제안)

> 작성: 2026-07-11, 오퍼스/medium (`archive/h0_v1/docs/plan_h0_verification.md` §4 V6 V-KPIWIN 배정).
> 구현: `simulation/kpi.py`(additive `*_orderspan` 필드) + `simulation/model.py`
> (per-tick 누적 스냅샷 `_ev_busy_cum`/`_opex_cum`) + `tests/test_kpi_window.py`(10개).
> 아래 수치는 전부 `python -m simulation.run` in-process 실행(seed 42, profile:uniform)
> stdout을 그대로 옮긴 것이며 수기 계산 없음. **§5-1 사용자 결정 대기 — 확정 아님.**

## 0. 문제 (plan §0.3 사실 5)

가동률·비용류 KPI의 **분모(측정 윈도우)** 가 정의되어 있지 않다. 현행 EV 가동률은
풀 윈도우(`wall_span_sec` = `clock_end − clock_start` = `tick_count × dt`)를 분모로 쓴다.
scenario ±1 h 보행자 윈도우(D4) 아래 이 풀 윈도우는 첫 주문 1 h 전 워밍업 헤드와
마지막 배달 후 최대 1 h 쿨다운 테일을 포함하므로, "가동률 93~95%"가 이 헤드·테일
때문에 왜곡된 값인지 규명하고 측정 윈도우를 명문화해야 한다.

## 1. 두 윈도우 정의 (병기 구현 완료)

| 윈도우 | 구간 | 필드 |
|---|---|---|
| **풀 윈도우** (현행, 불변) | `[clock_start, clock_end]` = `[min ORD − 1 h(워밍업), 마지막 이벤트]` | 기존 `utilization`, `opex_running_krw`, `wall_span_sec` — **값·이름 불변** |
| **주문 구간** (신규) | `[min ORD_TIME, 마지막 delivered]` | `utilization_orderspan`, `opex_running_krw_orderspan`, `orderspan_window_sec`, `wall_span_orderspan_sec` |

주문 구간은 배달 수요가 실제 존재하는 유일한 구간이다(첫 주문 이전엔 라이더 0, 마지막
배달 이후엔 잔여 라이더 퇴장뿐). 구현은 **순수 additive**: model이 매 tick 누적 스냅샷
`_ev_busy_cum[ev]`·`_opex_cum`을 append하고, `kpi.summarize`가 주문 구간 tick 인덱스
`[j0, j1]`(가장 가까운 tick 반올림·클램프)로 분자·분모를 잘라낸다. 기존 KPI 계산 경로는
한 줄도 바뀌지 않아 풀-윈도우 값은 bit-동일(동결 회귀 보장, 테스트 ①).

### 윈도우 의존 KPI 전수 식별

`kpi.py`에서 분모가 wall_span인 KPI는 **`elevator[ev].utilization` 단 하나**
(= `busy_ticks / tick_count`). 그 외:
- **`building.opex_running_krw`** 는 분모 정규화 없는 *누적 비용*(numerator-only). 라이더
  체류가 주문 구간 안에 있어 **윈도우 거의 불변**이나, "비용류 병기" 요구에 맞춰
  `_orderspan` 변형을 추가(풀 대비 차이 = 마지막 라이더의 배달 후 퇴장 테일뿐, §2).
- **나머지 전부**(`t_e2e_*`, `t_lobby_*`, `w_ev_*`, `lobby_cost_total_krw`,
  `cost_per_order_krw`, `sla_violation_rate`, `ev_wait_*` 등)는 per-order/per-rider/
  per-boarding 집계로 **측정 윈도우와 무관**. 병기 불필요.

## 2. 차이 수치 (K50_1·K300_4·K1000_1 × seed 42, profile:uniform)

### EV 가동률 (풀 vs 주문 구간)

| 시나리오 | EV | util_full % | util_orderspan % | Δpp |
|---|---|---|---|---|
| K50_1  | EV1 | 92.44 | 95.57 | **+3.13** |
| K50_1  | EV2 | 93.28 | 92.73 | **−0.55** |
| K300_4 | EV1 | 94.15 | 96.21 | +2.05 |
| K300_4 | EV2 | 94.63 | 95.68 | +1.05 |
| K1000_1| EV1 | 95.22 | 97.88 | +2.66 |
| K1000_1| EV2 | 95.54 | 96.96 | +1.42 |

### 윈도우 폭·OPEX

| 시나리오 | wall_span_s | orderspan_s | span/full | opex_full | opex_orderspan |
|---|---|---|---|---|---|
| K50_1  | 10610 | 5668 | 0.534 | 29,336.1 | 29,162.8 |
| K300_4 | 10843 | 7036 | 0.649 | 264,177.4 | 264,050.7 |
| K1000_1| 10848 | 7160 | 0.660 | 1,502,058.1 | 1,501,880.3 |

## 3. 핵심 발견 — EV 가동률은 윈도우-**강건**(사실 5 정밀화)

주문 구간이 풀 윈도우의 53~66%로 좁아졌는데도 가동률은 **양쪽 다 92~98%**로 거의
같다(최대 Δ +3.1pp, 심지어 K50_1 EV2는 −0.55pp로 **역전**). 이유: EV는 라이더뿐
아니라 **보행자**를 태우고, 보행자 스트림은 주문 구간보다 넓은 ±1 h 보행자 윈도우
전체에 퍼져 있어 EV가 창 전체에서 준-포화 상태다. 따라서:

1. **"93~95%가 유휴 분모 탓"이라는 사실 5의 가설은 EV 가동률에 대해선 기각** — 값은
   측정 윈도우 선택과 거의 무관하게 실재하는 높은 값이다.
2. **plan §2 L7 제안 불변식 `util_orderspan ≥ util_full`은 성립하지 않음**(K50_1 EV2
   반례). 테일(보행자 워밍업/쿨다운)이 주문 구간보다 더 바쁠 수 있기 때문. 테스트는
   실재 불변식만 잠근다: 주문 구간 ⊂ 풀 윈도우, busy-분자 단조(`busy_span ≤ busy_full`),
   util ∈ [0,1]. 방향성 부등식은 `test_util_window_robust_not_directional`이 오히려
   양방향 관측을 확인해 재도입을 방지.
3. **OPEX는 윈도우-불변**(차이 0.01~0.6%, 전부 마지막 배달 후 퇴장 테일). 비용류 KPI는
   측정 윈도우 논쟁에서 자유롭다.

## 4. 규약 **제안** (§5-1 — 사용자 결정 대기, 확정 금지)

- **제안**: 논문 본문 = **주문 구간** `[min ORD, 마지막 배달]`, 풀 윈도우 **병기**(부록/각주).
  근거: 주문 구간이 배달 수요가 실제 존재하는 구간이라 배달 KPI와 서사가 일관되고,
  ±1 h 보행자 마진(D4)이 시나리오마다 다른 워밍업/쿨다운 폭으로 KPI에 흘러드는 것을 차단.
- **단, EV 가동률에 한해 nuance**: EV 활동 창은 보행자 때문에 사실상 보행자 윈도우
  (≈ 풀 윈도우)이므로, 가동률만은 풀 윈도우가 더 자연스러운 "활동 창"일 수 있다.
  본문 규약이 주문 구간으로 확정되더라도 §3 발견(윈도우-강건, 양쪽 92~98%)을 각주로
  병기하면 어느 정의든 결론 불변임을 보인다.
- **결정 필요 사항(§5-1)**: (a) 본문 기본 윈도우 = 주문 구간 vs 풀 윈도우, (b) 가동률만
  예외로 풀 윈도우 표기할지. 구현은 이미 두 값을 모두 산출하므로 결정은 **표기 선택**일 뿐,
  재실행 불필요.

## 5. 산출물

- 코드: `simulation/kpi.py`(helpers `_order_span`·`_tick_index` + `*_orderspan` 필드,
  docstring에 전수 식별 명시) / `simulation/model.py`(`_ev_busy_cum`·`_opex_cum`
  per-tick 스냅샷, audit-off bit-identical 보존).
- 테스트: `tests/test_kpi_window.py` 10개 — ①동결 풀-윈도우 스냅샷 ②helper 폐형식
  (`_tick_index`·`_order_span`·윈도우 분수식) ③④주문 구간 util·OPEX의 모델 독립 재계산
  대조 ⑤주문 구간 ⊂ 풀 + 분자 단조(3 시나리오) ⑥윈도우-강건·비방향성.
- 데모 스크립트: §2 표는 `run_baseline` in-process 3 시나리오 stdout.
