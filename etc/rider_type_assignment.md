# 라이더 type 배정 규칙 (Rider Type Assignment)

> H0 baseline ABM에서 "라이더 선택" = **주문마다 라이더 type(BIKE/WALK/CAR) 하나를
> 확률적으로 배정**하는 것. H0는 주문당 라이더 1명이 즉시 생성되므로 type을 뽑는 것이
> 곧 라이더 선택이다. 구현: `analysis/rider_arrival_model.py`의
> `_sample_rider_type_for_order`. 계획서 §2.5(framework) 근거.

## 배정 규칙 (2단계)

**1단계 — 적재가능(capa) 필터**
주문 부피 `VOL(i)`를 실을 수 있는 type만 후보로 남긴다: `r.capa >= vol`.
후보가 하나도 없으면(최대 capa < VOL) `ValueError`.

**2단계 — available_number 가중 추출**
후보 집합에서 `available_number`에 비례한 확률로 하나를 뽑는다.

```
                          available_number_t
P(type = t | VOL) = ───────────────────────────────      단,  t ∈ { s : capa_s ≥ VOL }
                      Σ_{s: capa_s ≥ VOL} available_number_s
```

## K50_1 데이터의 실제 값 (`RIDERS` 테이블, load_data.py)

| type | speed (m/s) | capa | available_number | service_time (s) | w_R (KRW/h) |
|------|------------:|-----:|-----------------:|-----------------:|------------:|
| BIKE | 5.291 | 100 | 10 | 120 | 8,000 |
| WALK | 1.323 |  70 | 15 | 120 | 6,500 |
| CAR  | 4.233 | 200 | 50 | 180 | 10,000 |

**VOL 구간별 후보와 가중치**
- `VOL ≤ 70` → 셋 다 후보, 가중 BIKE:WALK:CAR = 10:15:50
- `70 < VOL ≤ 100` → BIKE·CAR만, 가중 10:50
- `100 < VOL ≤ 200` → CAR만 (강제)

**K50_1 실행 결과 분포**: CAR 36 / WALK 9 / BIKE 5
(CAR의 available_number=50이 커서 비중이 높음)

## 왜 capa 필터를 먼저 두는가

`available_number`만으로 뽑던 이전(주변부 marginal) 방식은 약 **0.4%가 배차 불가능한
배정**(라이더 capa < 주문 VOL)을 만들었다. capa 조건부로 바꿔 배차 가능성(dispatch
feasibility)을 강제해 이를 제거했다.

## 이 선택이 결정하는 하류 값 (한 번의 type 배정이 셋을 동시에 확정)

1. **이동속도** `speed_mps` → 외부 도로 이동시간 `DIST[i][K+i] / speed`
   → 라이더 건물 도착시각 `t_arrival`
2. **서비스(인도) 시간** → BIKE/WALK 120s, CAR 180s (데이터값 그대로)
3. **임금** `w_R = fixed_cost + var_cost × throughput(50)`
   → 체류 기회비용 `w_R × T_lobby`

## RNG 규약 (재현성)

- 단일 시드 `default_rng(42)`로 **전 주문 type을 먼저 벡터로 샘플**(`type_by_order`),
  **그 다음** 도착노이즈 ε 벡터를 샘플. 이 소비 순서 고정 덕분에 σ_ε를 0↔0.15로 바꿔도
  **type 배정은 불변**.
- ABM은 이 로직을 재구현하지 않는다. `analysis/scenario_loader.py`의 `load_replay_v4`가
  `sample_rider_arrivals`를 **그대로 호출**해 `BuildingOrderV4.rider_type`으로 받는다.
  즉 라이더 선택은 리플레이 로딩 시점에 **사전 확정**되고, 시뮬레이션 중 동적으로
  재선택되지 않는다.

## 범위(scope)에 대한 주의

- 이는 "어떤 **type**을 쓰나"의 선택이지, 개별 라이더 개체 풀에서 특정 라이더를
  고르거나 가용 라이더가 소진되는(재고 차감) 모델이 아니다 — H0는 주문당 라이더가
  **무한 공급**으로 즉시 생성된다.
- 건물 **내부** 수단선택(엘리베이터 vs 계단, 이항 로짓)과 **EV 배차**(어느 EV를
  부를지)는 별개 메커니즘이다. 전자는 `simulation/vertical_transport.py`의
  `sample_mode`, 후자는 `simulation/agents/control_system.py`의 `choose_elevator`.

## 관련 파일

| 파일 | 역할 |
|------|------|
| `analysis/rider_arrival_model.py` | `_sample_rider_type_for_order`(배정 규칙), `sample_rider_arrivals`(도착시각 합성), `compute_w_R_krw_per_h`(임금) |
| `analysis/load_data.py` | `RIDERS` 로더 (`Rider.capa/speed_mps/available_number/service_time_sec/var_cost/fixed_cost`) |
| `analysis/scenario_loader.py` | `load_replay_v4` — 위 샘플러 호출 결과를 `BuildingOrderV4.rider_type`으로 ABM에 전달 |
| `simulation/model.py` | `BuildingHandoffModel` — 주문당 `ExternalRiderAgent` 생성 시 type별 `service_time_for(rider_type)` 적용 |
