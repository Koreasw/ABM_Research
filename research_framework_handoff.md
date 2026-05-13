# 빌딩 로비 핸드오프(Lobby Handoff) 모드의 ABM 기반 다관점 설계 평가

## 연구 제목 (안)

**"A Multi-Stakeholder Agent-Based Simulation of Robot-Mediated Lobby Handoff in Smart Buildings: Comparing Direct Delivery, Synchronous Handoff, Queued Handoff, and Autonomous Docking Lockers under Real Demand Patterns"**

---

## 1. 연구 배경 및 목적

### 1.1 배경
- AI 기반 자율주행 로봇의 빌딩 내 식음료 배달 서비스가 상용화 단계에 진입 (예: Bear Robotics *Servi*, LG *CLOi ServeBot*, 우아한형제들 *Dilly Drive*). 동시에 도시 last-mile 의 인간 라이더 배달은 배달 플랫폼(배달의민족, 쿠팡이츠 등)을 중심으로 안정적인 수요 기반을 형성.
- 두 시스템의 **결합 지점(coupling interface)** 인 *빌딩 로비 핸드오프(lobby handoff)* 는 현실에서 매일 수천 건씩 발생하지만, 학술 연구에서는 다음 한계로 인해 *분석 차원으로 격상*되지 못했다.
  - 기존 indoor robot delivery ABM 은 빌딩 내부만 모델링하고 외부 도착을 단순 Poisson 과정으로 추상화.
  - 기존 last-mile logistics 연구는 도시 측 라우팅·디스패치에 집중하고 빌딩 내부 마지막 100 m 를 단일 노드로 축약.
  - parcel locker / smart locker 연구는 위치·크기 최적화에 집중하지만 *식음료 배달의 실시간 라이더 회전율* 과 결합한 ABM 분석이 부재.
- 핸드오프 방식은 **세 주체의 자원·시간 배분**을 동시에 결정한다.
  - **외부 라이더**: 빌딩 내 핸드오프 대기시간이 길어질수록 시간당 처리량·소득이 감소하는 *gig-economy 후생* 비용
  - **고객**: 핸드오프 단계의 추가 지연이 플랫폼 SLA 위반 (T_e2e > DLV_DEADLINE) · 만족도 저하로 직결
  - **빌딩 관리자**: 자동 도킹 locker 도입의 CAPEX 와 처리량 증가·라이더 회전율 향상의 OPEX 간 NPV 균형
- 본 연구는 4가지 핸드오프 모드(H0–H3)를 **하나의 ABM** 에서 비교 평가하고, 수요 강도 K, 빌딩 규모(5F/10F), 라이더 시간단가 w_R, locker 수 M 의 sweep 하에서 **3-stakeholder Pareto frontier** 를 도출한다.
- 참고 선행: 세종시 공공자전거 *어울링* data-driven ABM — bottom-up calibration 사례.

### 1.2 핵심 framing
배달의민족 데이터의 K=50 시나리오(약 1시간 horizon, 50건 주문)를 **단일 오피스 빌딩 점심피크 1시간**의 실측 수요 자료로 직접 해석한다. K=50 / horizon ≈ 1 h ⇒ 50 ord/h 는 500~1,000 인 오피스(1인당 시간당 주문확률 0.05~0.10)와 자연스럽게 정합되므로, 다운스케일 보정 ρ 없이 데이터 단위와 운영 단위가 직접 매핑된다. K∈{100, 200, 500, 1000}은 동일 빌딩의 *점진적 수요 강도 sweep* 으로 해석.

본 연구의 핵심 방법론적 입장은 **time–space decoupled calibration** — 데이터의 *시간적 수요 · 서비스 · 비용 구조*는 빌딩 시뮬레이션에 그대로 이식하되, *공간 구조* 는 빌딩 내부 prior 로 분리한다. 도시 위경도와 빌딩 층/호실 사이의 의미론적 매핑 함수가 부재하기 때문이다.

### 1.3 목적
1. 핸드오프 모드 집합 H = {H0, H1, H2, H3}을 ABM 내 *공정한 비교가능 구조*로 정식화
2. 배민 라이더 데이터에서 **빌딩 도착 시계열**을 합성하여 H 비교의 외생 boundary condition 으로 주입
3. 라이더·고객·빌딩 3 주체의 KPI 를 동일 시뮬레이션 내에서 산출하고, **3차원 Pareto frontier** 를 K∈{50,100,200,500,1000} × 빌딩 typology {5F, 10F} 조합에서 추적
4. 자동 도킹 locker 도입의 **break-even 라이더 시간단가 w\*** 와 **mode dominance 전환 수요 λ\*** 를 NPV 식의 해로 정식화

### 1.4 Research Questions 및 KPI 매핑

| # | Research Question | Primary KPI | Secondary KPI | 통계 방법 |
|---|---|---|---|---|
| RQ1 | 4가지 핸드오프 모드 간 종합 성능에 통계적으로 유의한 차이가 있는가? | 평균·95p 총 배달시간, 라이더 시간당 처리량, 플랫폼 SLA 위반율 (T_e2e > DLV_DEADLINE) | EV 대기시간, 로봇 가동률 | 4-way ANOVA + Tukey HSD |
| RQ2 | 수요 강도 K 가 증가하면 dominant mode 가 어떻게 전환되는가? | K별 dominant mode 영역도(domination map) | 모드간 KPI 격차 | K-stratified 분석 + bootstrap CI |
| RQ3 | 3 stakeholder (라이더·고객·빌딩) Pareto frontier 의 위치와 모양은? | Pareto front hypervolume, 모드별 비지배 점유 비율 | 모드별 reference-point distance | Hypervolume indicator, ε-dominance |
| RQ4 | 자동 도킹 locker (H3) 도입의 break-even 라이더 시간단가 w\* 는? | `NPV_H3(w*) = NPV_H1(w*)` 해 w\* | w\* 의 K-민감도 | Bootstrap CI (B=1000), Sobol Si_total |

---

## 2. 데이터 설명

### 2.1 데이터 출처
배달의민족 라이더 배달 기록 (JSON 형식). 본 연구에서의 이용 범위·라이선스는 §11 (윤리/데이터 거버넌스) 에 명시.

### 2.2 데이터 구성
- **data/data1/** (42 파일): K 분포 — K=50:2, K=100:9, K=200:9, K=300:8, K=500:5, K=750:1, K=1000:5
- **data/data2/** (10 파일): K=2000 규모의 STAGE3 테스트셋
- **data/data_ex.txt**: 공식 스키마 정의(authoritative)

### 2.3 공식 스키마

#### ORDERS (주문)
```
[ORD_ID, ORD_TIME, SHOP_LAT, SHOP_LON, DLV_LAT, DLV_LON, COOK_TIME, VOL, DLV_DEADLINE]
```

| 필드 | 인덱스 | 관측 범위 | 본 연구에서의 활용 |
|------|--------|--------|------|
| ORD_ID | [0] | 0 ~ K−1 | 식별자 |
| ORD_TIME | [1] | 0 ~ 28,778초 (≈ 8h pooled) | 외부 주문 발생 시점; 라이더 도착 시계열의 *base* |
| SHOP_LAT / SHOP_LON | [2], [3] | 서울 강남구 일대 | 외부 이동시간 합성에만 사용 (빌딩 공간 prior 와 분리) |
| DLV_LAT / DLV_LON | [4], [5] | 서울 일대 | 외부 이동시간 합성에만 사용 |
| COOK_TIME | [6] | 300~3,000초 (5분 이산) | 외부 식당 음식 준비시간 → 라이더 빌딩 도착 시각의 lower bound |
| VOL | [7] | 5~100 | locker compartment 적재 제약, 로봇 capa 대비 제약 |
| DLV_DEADLINE | [8] | 절대시각(초) | 핸드오프 큐잉 허용폭 상한; **플랫폼 SLA target** (배민 알고리즘 ETA = cook + 거리 + 식당 정확도) — L_sla_violation 의 기준 |

#### RIDERS (라이더 유형)
```
[type, speed (m/s), capa, var_cost, fixed_cost, service_time (sec), available_number]
```

| type | speed | capa | var_cost | fixed_cost | service_time | 의미 |
|------|-------|------|---------|-----------|--------------|------|
| BIKE | 5.29 m/s (≈19km/h) | 100 | 60 | 5,000~9,000 | 120 s | 자전거 |
| WALK | 1.32 m/s (≈4.8km/h) | 70 | 30 | 2,000~8,000 | 120 s | 도보 |
| CAR | 4.23 m/s (≈15km/h) | 200 | 100 | 5,000~6,000 | 180 s | 차량 |

- `capa` = 동시 적재 가능 부피
- `var_cost` = 건당 변동비, `fixed_cost` = 시나리오당 라이더 기본 고정비
- `service_time` = 가게/고객 방문 시 픽업/드롭 처리 시간

#### DIST (거리 행렬)
- `(K*2) × (K*2)` 도로 네트워크 거리(m). 인덱스 `0..K-1` = 픽업지점, `K..2K-1` = 배달지점.
- 주문 *i* 의 픽업-드롭 거리 = `DIST[i][K+i]`.

### 2.4 필드 활용 매핑 (handoff 특화)

| 항목 | 데이터 근거 | 본 연구에서의 활용 |
|---|---|---|
| K-stratum별 주문 도착률 λ_K(t) | ORD_TIME 분포 | Replay 모드의 외부 주문 시퀀스 입력 |
| 음식 준비시간 F_prep | COOK_TIME (Gamma 적합) | 라이더 빌딩 도착 시점 합성식의 두 번째 항 |
| 외부 이동시간 분포 | DIST[i][K+i] / speed | 라이더 빌딩 도착 시점 합성식의 세 번째 항 |
| 주문 부피 분포 | VOL | locker compartment V_max 결정, 로봇 capa 제약 |
| 플랫폼 SLA target | DLV_DEADLINE − ORD_TIME = 약속된 ETA 대기시간 | CustomerAgent.dlv_deadline_sec — L_sla_violation 의 비교 기준 |
| 라이더 시간단가 w_R | fixed_cost / horizon + var_cost × 처리량 | ExternalRiderAgent 의 빌딩 잔류시간 화폐화 |
| 픽업/드롭 처리시간 | RIDERS.service_time | 핸드오프 처리시간 baseline (120 s) |
| 공간(픽업) | SHOP_LAT/LON | **빌딩 도착 시간 합성에만 사용** (직접 공간 매핑 없음) |
| 공간(드롭) | DLV_LAT/LON | **미사용**; 각 주문을 빌딩 층/호실에 *uniform random* 으로 무작위 배정, 시드 고정 |

### 2.5 라이더 빌딩 도착 시각 합성식 (Core Calibration)

본 연구의 가장 핵심적인 데이터 변환:

```
t_rider_arrival(i) = ORD_TIME(i) + COOK_TIME(i) + travel_time(i) + ε
travel_time(i)     = DIST[i][K+i] / speed(rider_type(i))
ε                  ~ Lognormal(0, σ_ε²)      // 도로 혼잡 noise, σ_ε = 0.15 baseline
rider_type(i)      ~ Cat(p_BIKE, p_WALK, p_CAR)   // RIDERS.available_number 가중
```

이는 *주문 발생 시각으로부터 라이더가 식당에서 음식을 받고 빌딩 로비에 도착하기까지의 총 시간* 을 데이터 그대로 합성한 것이며, 빌딩 외부의 도시 dynamics 를 ABM 내부에서 추상화 없이 *시간축에 직접 반영* 한다.

| 합성 단계 | 데이터 근거 | 검증 |
|---|---|---|
| ORD_TIME 시퀀스 | 시나리오 ORDERS [1] | K-stratum 별 NHPP λ_K(t) 적합 (§4.1.1) |
| COOK_TIME | Gamma(shape=4.70, scale=223.3 s), AIC 최우수 | §4.1.2, fit_report.md |
| travel_time | DIST[i][K+i] / speed(type); type ∈ {BIKE=5.29, WALK=1.32, CAR=4.23} m/s | §4.1.3, speed 분포는 RIDERS.available_number 가중 **+ capa-conditional eligibility** (아래 단락 참조) |
| ε noise | Lognormal(0, 0.15²) | 도시 도로망 변동 표준 가정, sensitivity sweep σ_ε ∈ [0.0, 0.30] |

**rider_type(i) 샘플링 규칙 (capa-conditional)**: 각 주문 i 의 rider_type 은 *해당 주문의 VOL을 처리할 수 있는 라이더 집합* `{r : r.capa ≥ VOL(i)}` 안에서, `RIDERS.available_number` 가중치로 샘플링한다. 이는 dispatcher 의 capa 제약을 인과 순서대로 (ORDER → ELIGIBLE TYPES → SAMPLED TYPE) 반영하여 *데이터 비일관 할당* (WALK capa 70 인데 VOL > 70 주문 운반 등; 실측 1.9% 주문이 VOL > 70) 을 사전 차단한다. STAGE 1.5 검증에서 `52,000` 합성 events 의 capa 위반 = **0** (이전 marginal 샘플링 0.40% 위반).

**산출물**: `analysis/rider_arrival_model.py` — `sample_rider_arrivals(scenario_path, seed) → list[RiderArrivalEvent]`. 각 이벤트는 `(t_arrival_sec, order_id, vol, rider_type, time_cost_per_sec, deadline_sec)`. capa-conditional 효과의 시각화는 `analysis/figures/fig_vol_by_rider_type.png` 참조.

### 2.6 데이터 단위 ↔ 운영 단위의 정합성

| 데이터 단위 | 빌딩 운영 단위 | 정합 근거 |
|------------|--------------|----------|
| K=50 시나리오 1건 | 빌딩 점심피크 1시간 (11:30–12:30) | K=50 / horizon ≈ 1h ⇒ 50 ord/h 는 500~1,000인 오피스 (1인당 시간당 주문확률 0.05~0.10) 와 자연 정합 |
| K=50 시나리오 2건 + K=100 시나리오 9건 (점심피크 표본) | 11 replications (raw); seed 보강으로 30+ 확보 | 시나리오당 1일분 점심피크로 해석. K=50 표본이 적은 한계는 K=100을 보조 표본으로 결합하여 보완 |
| K ∈ {50,100,200,300} | 빌딩 수요 강도 sweep — **1차 분석** | 일관된 1h horizon → 점심피크 직접 정합 (§7 E2 1차 트랙) |
| K ∈ {500,1000} | 빌딩 수요 강도 sweep — **2차 분석** | stratum 내 horizon 혼재 (1h/2h/4h) → 60min truncate 또는 horizon sub-stratify 필요 (§7 E2 2차 트랙) |

**Horizon 정합성 caveat (data1/ 실측 from STAGE 1.5)**: 시나리오의 ORD_TIME 최대값(horizon)이 K-stratum 별로 다음과 같음.

| K | n | horizon |
|---|---|---|
| 50 | 2 | 56~59 min (≈ 1h 일관) |
| 100 | 9 | 58~60 min (≈ 1h 일관) |
| 200 | 9 | 59~60 min (≈ 1h 일관) |
| 300 | 8 | 60 min (≈ 1h 일관) |
| 500 | 5 | **혼재: 1h × 3, 2h × 1, 4h × 1** |
| 750 | 1 | 2h (단일) |
| 1000 | 5 | **혼재: 1h × 3, 2h × 1, 4h × 1** |

K∈{500, 1000} 의 stratum 내 horizon 혼재는 λ_K(t) 적합 시 60min 이후 분자만 줄어드는 풀링 artifact를 발생시킨다 (분모 = stratum 내 시나리오 수 고정, 분자 = 해당 bin 에 주문이 있는 시나리오 수만 기여). 따라서 **1차 분석은 K∈{50,100,200,300} 만 사용**하고, K∈{500,1000} 은 (a) 60min truncate 또는 (b) horizon sub-stratify (예: "K=1000-1h" vs "K=1000-4h") 한 뒤 2차 분석에서 별도로 다룬다.

**민감도 sweep 변수 ρ**: `demand_model.lambda_t(t_sec, scale=ρ)` 의 `scale` 인자는 *민감도 분석용 수요 강도 배수* 로 정의 (baseline ρ=1.0). Generative 모드의 STAGE 4 stress test 에 한정 사용.

### 2.7 의도적으로 배제한 매핑 (referee 사전 대응)

| 배제 항목 | 검토된 대안 | 배제 근거 |
|----------|------------|----------|
| DLV 좌표 → 빌딩 층 K-means 매핑 | DLV (lat, lon) 클러스터링으로 핫스팟 → 상층 매핑 | (a) 도시 강남구 위경도와 빌딩 1F~5F 사이 *의미론적 매핑 함수 부재*. 도시 위도가 높다고 빌딩 상층이 아님. (b) 본 연구의 **time–space decoupled** 입장과 모순. (c) 층 분포 비균등성은 §7 민감도 분석의 "층 분포 prior" sweep 로 강건성 검증. |
| DIST 행렬 → 빌딩 거리 KS 검정 후 매핑 | 도시 mean ≈ 1.5km 거리 분포를 빌딩 networkx 거리에 scale 보정 | (a) 도시 mean 1.5 km vs 빌딩 max 수백 m 의 *물리적 스케일 차이*. (b) 분포 형태 보존 후에도 *물리적 의미(도로망 vs 복도·EV 그래프)* 가 사라짐. (c) 빌딩 내부 거리는 §5 networkx 그래프에서 *직접 산출* 함이 학술적으로 더 정직. |
| 라이더의 *다음 주문* 위치를 시나리오 내 후속 ORDERS 로 모델링 | 시나리오 ORDERS i+1 의 SHOP 좌표를 차회 픽업지로 사용 | 시나리오 단위 라이더 ID 가 부재하여 "동일 라이더의 연속 주문" 가정이 비검증. **라이더 시간단가 w_R 손실** 로 추상화 (다음 주문 lost ≈ w_R × 빌딩 잔류시간). |
| 다중 빌딩 (멀티 빌딩 네트워크) | 라이더가 여러 빌딩을 순회 | 단일 빌딩 가정으로 유지. 한계는 §7 Discussion 명시. |
| 복도 LWR (Lighthill–Whitham–Richards) 혼잡 모델 | 복도 1m discrete 를 LWR 속도-밀도 관계로 격상 | (a) 본 연구의 종속변수는 *배달·핸드오프 KPI*; pedestrian 은 EV 혼잡 생성기. (b) 빌딩 보행자 속도-밀도 데이터 캘리브레이션이 부재. (c) 현 "혼잡 감속 휴리스틱" 으로 EV 병목 효과 충분 포착. |

---

## 3. 전체 연구 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1. 외부 라이더 도착 시계열 합성                          │
│  (배민 데이터 → t_rider_arrival(i), λ_rider,K(t), w_R)         │
└──────────────────────┬──────────────────────────────────────┘
                       v
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2. 빌딩 로비 핸드오프 환경 모델링                        │
│  (5F/10F networkx 그래프 + 로비 zone + LockerBank)            │
└──────────────────────┬──────────────────────────────────────┘
                       v
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3. 핸드오프 모드 H0~H3 ABM 설계 & 구현 (Mesa)            │
│  (8-agent system + 4-mode dispatcher)                       │
└──────────────────────┬──────────────────────────────────────┘
                       v
┌─────────────────────────────────────────────────────────────┐
│  STAGE 4. 검증(8-step V&V) → 4-mode × K-sweep × typology 실험 │
│  → 3-stakeholder Pareto + Morris→Sobol 민감도                │
└──────────────────────┬──────────────────────────────────────┘
                       v
┌─────────────────────────────────────────────────────────────┐
│  STAGE 5. 논문 작성 & 정책 제언 (SMPT 1순위 투고)               │
└─────────────────────────────────────────────────────────────┘
```

> **RL 확장은 본 연구 범위에서 제외** 하고 Future Work 로 명시 (적응형 핸드오프 모드 선택 정책 학습).

---

## 4. STAGE 1: 외부 라이더 도착 시계열 합성

### 4.1 분석 항목 (공식 스키마 기준)

#### 4.1.1 K-stratum별 NHPP λ_K(t) 추정
- **풀링(pooled) 추정**: 전체 시나리오에 대해 ORD_TIME 5분 bin piecewise-constant λ(t). **주의**: pooled 추정은 시나리오별 horizon 차이로 인한 60/120/240min cliff artifact 가 발생하므로 *χ² 비정상성 evidence 용도* 로만 사용하고 시뮬레이션 입력으로는 직접 쓰지 않는다.
- **K-stratum 추정 (1차)**: K ∈ **{50, 100, 200, 300}** 별 λ_K(t) 분리 산출. 모두 horizon ≈ 1h 로 일관 (§2.6 caveat table) → 빌딩 점심피크 윈도우와 직접 정합.
- **K-stratum 추정 (2차)**: K ∈ {500, 1000} 은 stratum 내 horizon 혼재로 (a) 60min truncate 또는 (b) horizon sub-stratify 처리 후 별도 트랙으로 분석.
- **K-stratum 부트스트랩 CI**: K=50 시나리오 표본이 2건으로 적은 점을 보완하기 위해 K=50 + K=100 + K=200 + K=300 보조 표본을 결합, 시나리오 단위 부트스트랩 (B=1000 resampling) 으로 시점별 95% CI 산출.
- **검정**: χ² 정상성 검정 (H0: uniform)
- **실증 결과 (1차 분석, K∈{50,100,200,300}, 28개 시나리오, 5,200 주문)**: STAGE 1.5 산출 시점 — cook mean 17.2 min (Gamma shape 4.83 / scale 213.4), lead q05/q50/q95 = 36.1/51.0/74.2 min, VOL mean 27.4, pickup-drop mean 1.57 km.
- **K=50 stratum 해석**: 시나리오당 약 50건이 1시간 윈도우에 분포 → 시나리오당 평균 50 ord/h, 피크 약 100~150 ord/h. 500~1,000인 오피스 빌딩의 점심피크와 직접 부합.

#### 4.1.2 음식 준비 시간 F_prep
- COOK_TIME ([6]) 에 Lognormal / Weibull / Gamma 를 `floc=0` MLE 피팅, AIC/BIC 비교
- **실증 결과**: **Gamma (shape ≈ 4.70, scale ≈ 223.3 s)** 가 AIC 최우수. mean ≈ 17.5 min, median = 15 min, q90 ≈ 30 min. 원본 값이 5분 단위 이산화되어 KS 통계량이 연속 분포 가정 하에서 다소 높음 — 이산성 fit_report 에 명시

#### 4.1.3 외부 이동시간 분포
- DIST[i][K+i] / speed(rider_type) 의 경험분포 추정
- **선행 실증치**: pickup-drop mean ≈ 1.5 km, max ≈ 6.8 km
- BIKE 기준 mean travel ≈ 283 s, CAR 기준 mean travel ≈ 354 s, WALK 기준 mean travel ≈ 1,135 s
- **분포 적합**: Lognormal / Weibull / Gamma 의 AIC 비교 (이산성 없음)

#### 4.1.4 라이더 빌딩 도착 시각 결합 시계열
- `t_rider_arrival(i)` = ORD_TIME + COOK_TIME + travel_time + ε  (§2.5 정의식)
- 5-min bin piecewise-constant λ_rider,K(t) 산출, K∈{50,100,200,500,1000} 별 분리
- 부트스트랩 CI (B=1000) 으로 시점별 95% 신뢰구간

#### 4.1.5 라이더 시간단가 w_R 캘리브레이션
- 시간당 환산: w_R(type) = (fixed_cost / horizon_h) + (var_cost × throughput_per_h)
- **실증치 (RIDERS table)**: BIKE 5,000~9,000원/시나리오 + 60원/건; WALK 2,000~8,000 + 30; CAR 5,000~6,000 + 100
- **환산 결과** (처리량 50건/h 가정): BIKE w_R ≈ 9,500~12,000 KRW/h, WALK ≈ 5,500~9,000 KRW/h, CAR ≈ 11,000~14,000 KRW/h
- **baseline**: BIKE 기준 w_R = 10,500 KRW/h, sensitivity sweep [5,000, 20,000]

#### 4.1.6 주문 부피 VOL
- VOL ([7]) 분포 및 라이더 `capa` 대비 적재 제약
- **실증 결과**: 범위 [5, 100], mean ≈ 28, median = 24
- 활용: LockerAgent compartment V_max 결정, RobotAgent 적재 제약

#### 4.1.7 플랫폼 SLA 분포 — Lead time
- **정의**: lead time = `DLV_DEADLINE − ORD_TIME` = **배민 알고리즘이 고객에게 약속한 ETA 대기시간**. 배민 description 의 인용에 의하면 DLV_DEADLINE 은 (a) 식당 입력 COOK_TIME, (b) 식당의 과거 예측 정확도, (c) 고객-식당 거리 의 조합으로 산출되는 ETA 이며, 동시에 (d) 조리 완료 15분 전 배차 결정의 parameter 로 사용된다.
- **의미 — 정정 (referee 사전 대응)**: lead time 은 *플랫폼의 SLA 약속* 이지 *고객의 행동적 인내심* 이 아니다. 따라서 본 paper 는 이를 **L_sla_violation KPI** 의 비교 기준으로만 사용하며, 별도의 customer-abandonment 개념은 도입하지 않는다 (모델 단순화 선택; framework §6.2 CustomerAgent 정의 참조).
- **실증 (tier-1 cohort, 5,200 주문)**: q05 = 36.1 min (가장 빠른 ETA 약속) / q50 = 51.0 min / q95 = 74.2 min (가장 늦은 ETA 약속). 모든 주문이 ORD_TIME 후 일정 시간 이내 도착하도록 약속됨.
- **사용처**:
  - 각 주문의 `dlv_deadline_sec` 를 CustomerAgent 에 데이터 그대로 주입
  - KPI: `L_sla_violation = P(T_e2e > DLV_DEADLINE)` 산출
  - 핸드오프 큐잉 (H2) 의 허용폭 상한 — `current_time + queue_wait + travel < DLV_DEADLINE` 이어야 큐 수락

#### 4.1.8 K 스케일링 패턴
- K 값(50~2000) 별 주문 간격 CV, 부피 평균 등 구조 지표
- E2 실험(K-sweep) 의 입력

### 4.2 산출물

- `analysis/load_data.py` — 공식 스키마 기반 로더 (`load_orders()`, `load_riders()`, `load_dist()`)
- `analysis/run_analysis.py` — STAGE 1 전체 분석 파이프라인
- `analysis/demand_model.py`
  - `DemandModel.lambda_t(t_sec, scale=ρ) -> float`
  - `DemandModel.sample_interarrival(t_sec, scale=ρ) -> float` (thinning 호환)
  - `DemandModel.sample_cook_time() -> float`
  - `DemandModel.sample_volume() -> float`
  - `DemandModel.lead_time_q05_sec / lead_time_q50_sec`
- `analysis/scenario_loader.py` — K=50 시나리오 1건을 시뮬레이션 입력으로 변환. `load_replay(scenario_path, start_time_sec=11.5*3600, rng_seed=...) -> list[BuildingOrder]`. 각 BuildingOrder 는 `(arrival_time_sec, cook_time_sec, vol, lead_time_sec, floor, office_id)` 필드 보유
- **`analysis/rider_arrival_model.py`** — `sample_rider_arrivals()` API (§2.5 합성식 구현)
- `analysis/fitted_params.json` — 적합 파라미터 직렬화 + `arrivals_by_K`, `w_R_by_type`, `travel_time_params`
- `analysis/figures/` (STAGE 1 실행 후 9개 PNG):
  - `fig_lambda_pooled.png` — pooled NHPP λ — χ² evidence 용 (시뮬 입력 금지)
  - `fig_lambda_by_K.png` — tier-1 K-stratum λ_K(t)
  - `fig_k50_per_scenario_arrivals.png` — K=50 face validity
  - `fig_cook_time_fit.png` — Gamma fit + AIC 비교
  - `fig_vol_distribution.png` — VOL marginal
  - `fig_vol_by_rider_type.png` — capa-conditional VOL (BIKE/WALK/CAR)
  - `fig_lead_time.png` — Platform SLA 분포 (no-renege framing)
  - `fig_pickup_drop_distance.png` — 도로망 거리 (context)
  - `fig_rider_arrival_lambda_K.png` — §2.5 합성 + bootstrap CI
- `analysis/fit_report.md` — 적합도 리포트 (한국어, 자동 생성)

### 4.3 데이터 사용 모델 — Replay vs Generative + "pooled" 의 두 가지 사용처

본 절은 STAGE 1 실행 중에 *명확히 분리되어야 함이 드러난* 데이터 사용 규약을 정리한다. 두 가지 보강이 핵심:

#### (A) "pooled" 의 두 가지 사용처 (혼동 방지)

`pooled` 라는 단어가 두 가지로 쓰여 referee 혼동 가능 — 본 paper 에서는 다음과 같이 명확히 구분한다.

| 사용처 | "pooled" 의 의미 | 본 paper 적용 |
|---|---|---|
| **분포 적합 (Fitting)** | tier-1 cohort 28개 시나리오의 5,200 주문을 *통합* 해서 분포 추정 | Gamma cook fit, VOL empirical pool, lead time 분위수, χ² 비정상성 검정 |
| **Replay 모드 시뮬 입력** | **사용 안 함** — 각 주문의 *실제 데이터 값* per-order 직접 주입 | ORD_TIME, COOK_TIME, VOL, DIST 모두 per-order |
| **Generative 모드 시뮬 입력** | pooled fit 으로부터 *합성 샘플* | sample_cook_time, sample_volume, NHPP thinning |

→ **Replay 모드** (본 paper 주력) 에선 "pooled" 는 *fitting 단계의 통계 양식* 일 뿐, 시뮬 입력은 per-order 실데이터. **Generative 모드** 는 S4 stress test 전용.

#### (B) 외부 이동시간의 정확한 합성 구성

`travel_time(i) = DIST[i][K+i] / speed(rider_type(i))`  의 각 항이 *pooled* 인지 *per-order* 인지 명확화:

```
travel_time(i) = DIST[i][K+i]         / speed(rider_type(i))            (× ε)
                 └──── per-order ────┘ └────── 샘플링 결과 ──────┘     └─multiplicative
                 실 시나리오 데이터    capa-conditional + available_n     baseline σ=0.15
                 (pooled 아님)         (per-order 샘플)                    
```

- `DIST[i][K+i]`: **per-order 실 데이터** (pooled 아님). 거리는 각 주문의 실제 도로망 픽업-드롭 거리
- `rider_type(i)`: **per-order 샘플** — `{타입: capa ≥ VOL(i)}` 안에서 `RIDERS.available_number` 가중. *capa-conditional* 제약 필수 (실 데이터 1.9% 주문이 VOL > 70 → WALK 처리 불가)
- `speed(type)`: 타입 상수 (BIKE 5.29 / WALK 1.32 / CAR 4.23 m/s)
- `ε`: Lognormal(-σ²/2, σ²) multiplicative, baseline σ_ε = 0.15, E[ε]=1

→ "거리도 pooled 사용" 라는 표현은 오해 — pooled 거리 분포는 *시각화 figure 용* 이며, 시뮬 입력은 *각 주문의 실 거리*.

#### (C) Replay vs Generative 변수별 입력 출처 한눈 요약

| 변수 | **Replay 입력** (★ 본 paper) | Generative 입력 (S4 stress test) | Pooled fit 사용처 |
|---|---|---|---|
| 주문 도착 시각 | 시나리오 ORD_TIME 시퀀스 (per-order) | NHPP thinning from λ_K(t) | χ² 비정상성 검정 |
| 음식 준비시간 | 시나리오 COOK_TIME (per-order) | Gamma(4.83, 213.4) sampling | Gamma AIC fit |
| 주문 부피 VOL | 시나리오 VOL (per-order) | empirical pool bootstrap | 분포 figure |
| 라이더 타입 | **capa-conditional 샘플** (per-order) | 동일 | available_number 가중 |
| 외부 이동거리 DIST | 시나리오 DIST[i][K+i] (per-order) | (현재 미정의 — Replay 우선) | 거리 분포 figure |
| 이동시간 noise ε | Lognormal(0, σ²=0.15²) | 동일 | 민감도 sweep σ_ε ∈ [0, 0.30] |
| 빌딩 도착 시각 | t_rider = ORD_TIME + COOK_TIME + DIST/speed·ε | 동일 합성식 | bootstrap CI figure |
| 플랫폼 SLA target | 시나리오 DLV_DEADLINE (per-order) | (현재 미정의 — Replay 우선) | q05/q50/q95 분위수, fig_lead_time |
| 라이더 시간단가 w_R | per-type 상수 (RIDERS.fixed + var × 50) | 동일 | 캘리브레이션 표 |

#### (D) STAGE 1 핵심 정합성 검증

- ∫ λ_K(t) dt ≡ K (K=50/100/200/300 모두 정확) — DemandModel 수치 안정성 검증
- pooled mean = weighted average of K-stratum means (186 orders/h 양쪽 일치) — self-consistency
- capa-conditional 위반 = 0 / 26,000 events
- 모든 framework §4 expected 실증치 대비 ±5% 이내 부합

세부 결과·검증·산출물 전수 inventory 는 프로젝트 루트 `STAGE1_summary.md` 참조.

---

## 5. STAGE 2: 빌딩 환경 모델링

### 5.1 빌딩 구조

베이스라인을 5F 로 두고, 수직 이동 병목 효과를 보다 선명히 관찰하기 위해 **E3 typology 시나리오** 에서 10F 로 확장한다.

```
베이스라인 5F 오피스                  확장 10F (E3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 5F  [사무실]──복도──[사무실]           10F [사무실]──복도──[사무실]
 4F  [사무실]──복도──[사무실]            :       |          |
 3F  [사무실]──복도──[사무실]           EV1 EV2 EV3       EV4(공용)
 2F  [사무실]──복도──[사무실]            :       |          |
 1F  [로비 + 핸드오프 zone]             2F [사무실]──복도──[사무실]
B1F  [충전소][대기소]                   1F [로비 + 핸드오프 zone]
                                       B1F [충전소][대기소]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  EV1~3: 사람 전용                        EV1~3: 사람 전용
  EV4 : 사람+로봇 공용                    EV4 : 사람+로봇 공용
```

### 5.2 공간 모델링
- 층 = 노드, EV·복도·출입구·로비 zone = 간선인 **networkx 그래프** 로 구현
- 복도는 discrete position (1 m 단위) 으로 이산화하여 agent 간 혼잡 반영

### 5.3 공간 파라미터

| 파라미터 | 베이스라인 | 비고 |
|---------|-------|------|
| 층 구조 | B1F ~ 5F (6층) | 확장 시 10F |
| 층당 복도 길이 | 100 m (편도) | |
| 층고 | 4 m | EV 물리 모델 입력 |
| 사람 전용 EV | 3대 (EV1~3), 수용 10명 | |
| 공용 EV | 1대 (EV4); 수용 = (로봇 1대 → 사람 6명) / (로봇 없음 → 사람 10명) | |
| EV 물리 모델 | 가속도 1.0 m/s², 최고 속도 2.5 m/s, 도어 개폐 4초 | EV 대기시간 *내생화* |
| 충전소 / 대기소 | B1F | |
| 층별 상주 인원 | 50~100명/층 | 시간대별 변동 |

### 5.4 로비 핸드오프 zone (1F)

| 노드 | 종류 | 용량 | 비고 |
|------|------|------|------|
| `lobby_entry` | 라이더 진입 노드 | ∞ | 외부 ↔ 로비 경계 |
| `handoff_counter` | 동기 핸드오프 카운터 | 1명 | H1 전용; service time ~ N(60s, 15²) |
| `queue_zone` | 큐잉 대기존 | 최대 8명 | H2 전용; FCFS 가시 큐 |
| `locker_bank` | 자동 도킹 locker | M compartments | H3 전용; M ∈ {2,4,8,16} sweep |
| `direct_corridor` | 라이더 직접 EV 접근 | - | H0 전용; EV1~4 모두 가능 |
| `robot_pickup_zone` | 로봇 인계 대기 zone | 4대 | H1·H2·H3 공통; locker 옆 위치 |

### 5.5 LockerAgent 파라미터

| 파라미터 | baseline | sweep | 출처 / 근거 |
|---------|---------|-------|------|
| compartment 수 M | 8 | {2, 4, 8, 16} | sensitivity 대상 |
| compartment 부피 상한 V_max | 100 | {50, 70, 100, 200} | VOL 분포 q95 ≈ 70 → baseline 100 |
| 도킹 시간 (라이더 → locker) | N(20s, 5²) | μ ∈ [10, 40] | parcel locker 문헌 + vendor 사양 |
| 픽업 시간 (locker → 로봇) | N(15s, 4²) | μ ∈ [10, 30] | 인계 시 인증·도어 동작 |
| 보관 limit (최대 보관시간) | 30 min | {15, 30, 60} | 신선식품 품질 기준 |
| CAPEX (locker bank) | 8 M KRW | ±50% (sweep ±100%) | vendor 견적 — N/A 시 "N/A — vendor inquiry" |
| OPEX/year | CAPEX × 0.05 | - | 표준 유지보수율 |

### 5.6 Background agent (유동인구 모델)
EV 대기시간을 *상수가 아닌 내생 변수* 로 만들기 위해 background pedestrian agent 를 생성한다.
- 출근(08–10시) / 점심(11:30–13:30) / 퇴근(17:30–19:00) 피크 프로파일
- 각 보행자는 EV1~3 중 임의 선택 (공용 EV4 는 혼잡 회피 행동 α 반영, H1·H2 에서 라이더가 로비에 머무는 경우 α_lobby_extra = 0.10 추가)

### 5.7 이동 속도

| 주체 | 복도 속도 | EV 이용 | 비고 |
|------|----------|---------|------|
| 로봇 | 1.0 m/s | EV4 만 가능 | 혼잡 밀도 > θ 시 감속 |
| 외부 라이더 | 1.5 m/s | EV1~4 모두 가능 (H0 모드만) | |
| 일반 보행자 | 1.2 m/s | EV1~3 이용 | EV 혼잡 유발 |

---

## 6. STAGE 3: ABM 설계 & 구현

### 6.1 4가지 핸드오프 모드 process model

```
H0 (라이더 직접 배달, baseline reference)
─────────────────────────────────────────
ExternalRider arrives at lobby_entry
  → enters direct_corridor
  → selects EV(EV1~4, min wait heuristic)
  → ascends to target floor
  → traverses corridor to office
  → drops to customer (service_time = 120 s)
  → descends to lobby_entry → exits

H1 (동기 핸드오프, 라이더 ↔ 로봇 즉시 만남)
─────────────────────────────────────────
ExternalRider arrives at lobby_entry
  → walks to handoff_counter
  ControlSystem dispatches RobotAgent to handoff_counter
  → both meet at handoff_counter (one waits for the other)
  → service_time_handoff = N(60s, 15²)   // RIDERS.service_time 절반 가정
  → Rider exits ; Robot proceeds: EV4 → target floor → office → customer drop (30 s)

H2 (큐잉 핸드오프, 라이더 대기 허용)
─────────────────────────────────────────
ExternalRider arrives at lobby_entry
  → joins queue_zone (FCFS, max 8)
  ControlSystem assigns Robot when robot becomes available
  → Rider waits in queue_zone until Robot arrives
  → handoff service N(60s, 15²) at handoff_counter
  → Rider exits ; Robot proceeds as in H1
  // Rider may abandon if wait > τ_rider_patience (baseline 5 min)

H3 (자동 도킹 locker, 라이더 위탁 후 즉시 이탈)
─────────────────────────────────────────
ExternalRider arrives at lobby_entry
  → walks to locker_bank
  → if locker available with sufficient V_max:
       dock_time = N(20s, 5²) ; Rider exits immediately
       Locker holds order ; emits notify(robot_pickup_zone)
       Robot arrives, retrieves, pickup_time = N(15s, 4²)
       Robot proceeds as in H1
  → if no locker available:
       fallback to H2 (queue) or reject (configurable; baseline = fallback H2)
```

### 6.2 Agent 정의 (8-agent system)

#### CustomerAgent
- **속성**: 위치 (층·호실; uniform random 배정, 시드 고정), 외부 주문 시각 `ord_time_sec`, 주문 부피 VOL, 플랫폼 SLA target `dlv_deadline_sec` (시나리오 데이터 그대로 — 배민 알고리즘 산출 ETA 의 절대 시뮬레이션 시각), 만족도 민감도 β
- **행동**:
  1. 주문은 외부에서 발생; STAGE 1 합성 시계열의 도착 이벤트와 매칭
  2. 배달 완료 시 (a) `L_sla_violation` 플래그 = `T_e2e > dlv_deadline_sec` 기록, (b) 만족도 = `σ(−β · max(T_e2e − dlv_deadline_sec, 0))` 기록 — deadline 이내 도착이면 만족도 ~ σ(0) = 0.5, 초과 시 deadline 대비 초과 시간에 비례해 감소
  3. **고객 포기 (renege) 행동은 모델링하지 않음** — 식음료 배달의 현실 (선결제·취소수수료) 과 paper 단순화를 위해 모든 주문은 결국 인도되며, 고객 측 KPI 는 SLA 위반율과 만족도로 표현 (framework §4.1.7 의 reframing 결정)

#### ExternalRiderAgent (신규)
- **속성**: 빌딩 도착 시각, rider_type ∈ {BIKE, WALK, CAR}, 시간단가 w_R(type), 보유 VOL, 인내 임계 τ_rider_patience (baseline 5 min)
- **행동**:
  1. STAGE 1 합성 시계열의 t_rider_arrival 에 lobby_entry 등장
  2. active 핸드오프 모드 H ∈ {H0, H1, H2, H3} 에 따라 process 분기 (§6.1)
  3. H2·H3 큐잉/도킹 실패 시 대기시간 누적 → τ_rider_patience 초과 시 abandon
  4. 빌딩 잔류시간 T_lobby (= lobby_entry → exit 까지) 를 w_R × T_lobby 로 화폐화

#### RobotAgent
- **속성**: 위치, 배터리 잔량 SoC(%), 상태 (IDLE / MOVING / DELIVERING / CHARGING / RETURNING), 적재 용량 capa_robot (RIDERS 의 BIKE=100 ~ CAR=200 범위 참조, baseline 100), 현재 적재 부피 Σ VOL, 누적 주행거리
- **행동**:
  1. IDLE: B1F 대기소에서 주문 배정 대기
  2. 주문 배정 (제약: Σ VOL_carrying + VOL_new ≤ capa_robot) → 핸드오프 위치로 이동 (mode-dependent: H1=handoff_counter, H2=handoff_counter via queue release, H3=locker_bank)
  3. 픽업 처리 (service_time_pickup mode-dependent)
  4. EV4 호출 → 대기 (공유자원 경합) → 탑승 → 목적층
  5. 복도 이동 (혼잡 감속) → 고객 인도 (service_time_drop, baseline 30 s)
  6. SoC < SoC_low → 충전소, 그 외 → 대기소 or 다음 주문
- **비용 모델 (TCO)**:
  ```
  C_TCO(T) = C_acq + Σ_{t=1}^{T} (C_elec(t) + C_maint(t) + C_telecom(t)) · (1+r)^{-t} − C_salvage(T)
  ```
  - C_acq: Bear Robotics *Servi* (USD 25k–35k ≈ 3,300–4,600 만원), LG *CLOi ServeBot* (1,500–3,000 만원/대), 우아한형제들 *Dilly Drive* (B2B 리스/렌탈; 정확치는 vendor inquiry 또는 "N/A — vendor inquiry" 명시)
  - 내용연수 T = 5~7년 (제조사 기본 보증·내구 사양)
  - 할인율 r = 0.05 기본, 민감도 분석 대상 — 한국은행 기준금리 + 기업 WACC 평균
  - C_elec: 한국전력공사 산업용(을) 일반 요금 × 배터리 용량 × 일일 충전 횟수 × 365
  - C_maint, C_telecom: 벤더 유지보수 계약 + 5G IoT 회선 — 미확보 시 "N/A — vendor inquiry" 명시 후 sweep ±100%

#### LockerAgent (신규)
- **속성**: compartment 상태 배열 (EMPTY / OCCUPIED(order_id, since)), V_max, 보관 limit
- **행동**:
  1. `try_dock(order, vol)` → 빈 compartment 중 V_max ≥ vol 확인 후 점유
  2. `notify(robot_pickup_zone)` 호출
  3. `pickup(order)` → compartment 비움
  4. 보관시간 limit 초과 시 알림 + 빌딩 관리자 개입 이벤트 발생
- **KPI**: 시점별 점유율 U_locker, 평균 보관시간, 도킹 실패율

#### BuildingManagerAgent (신규)
- **속성**: 시뮬레이션 시작 시 정책 fix (H_mode, robot_count, locker_count M, charging_policy)
- **행동**:
  1. 매 step CAPEX 상각 + OPEX 누적
  2. 모드별 NPV 분기점 추적 (NPV_H3 vs NPV_H1)
  3. KPI 집계 (시뮬레이션 종료 시 5년 NPV 환산)
- **참고**: 본 연구는 규칙 기반 정책 비교. 적응형 정책 학습은 Future Work.

#### ControlSystemAgent
- **속성**: 주문 큐, 배정 정책 π (FCFS / Nearest / mode-specific dispatcher), 상태 모니터
- **행동**:
  1. 주문 수신 → 우선순위 (대기시간·거리) 계산 → 큐 삽입
  2. active 핸드오프 모드 H 에 따른 dispatch 분기:
     - H0: 라이더에게 직접 EV 안내
     - H1: 라이더 도착 시 즉시 가장 가까운 idle 로봇 호출
     - H2: 큐 도착 라이더는 다음 idle 로봇이 나올 때까지 대기
     - H3: locker dock 완료 시 idle 로봇에게 pickup notify
  3. 로봇 SoC 모니터링 → 선제 충전 스케줄
  4. KPI 실시간 집계 (DataCollector)

#### ElevatorAgent
- **속성**: 현재 층, 방향, 탑승자, 호출 큐
- **행동**:
  1. FCFS 또는 SCAN 알고리즘
  2. 물리 모델(가감속) 기반 층 이동
  3. EV4: 로봇 탑승 시 잔여 수용 감소 + 사회적 수용성 α (사람이 다음 EV 대기 확률)

#### PedestrianAgent (background)
- **속성**: 출발층·목적층, 속도, EV 선호 (혼잡 회피)
- 본 연구의 종속 변수가 아닌 *EV 혼잡 생성기* 역할

### 6.3 시뮬레이션 흐름

```
For each tick t:
  1. ExternalRider events queue 처리 (STAGE 1 합성 시계열에서 pop)
  2. CustomerAgent: 주문 상태 갱신, deadline / SLA 평가
  3. PedestrianAgent: 출퇴근/점심피크 EV 호출
  4. ControlSystemAgent: 핸드오프 mode H 에 따라 Robot 배정
  5. RobotAgent / LockerAgent / ElevatorAgent / ExternalRiderAgent: action step
  6. BuildingManagerAgent: NPV / CAPEX / OPEX 누적
  7. DataCollector: KPI snapshot
```

---

## 7. STAGE 4: 실험 설계

### 7.1 검증 (Validation) — 8-step Partial V&V

빌딩 내 로봇 배달 + 외부 라이더 핸드오프의 *실측 운영 데이터는 부재* 하므로 다음 복합 전략으로 모델 신뢰도를 확보한다.

1. **부분 캘리브레이션(partial calibration)**
   - 수요·서비스 타임·라이더 시간단가 → 배민 데이터로 calibrate
   - 로봇 하드웨어 파라미터 → 시판 모델 스펙 (Bear Servi, LG CLOi, Dilly Drive)
   - locker 파라미터 → parcel locker 문헌 + vendor 견적
2. **Face validity**: 빌딩 관리·F&B·로봇 벤더·**라이더 출입 동선** 도메인 전문가 인터뷰 (체크리스트 기반)
3. **Extreme-value test**: 주문 0건, 주문 폭주(λ→∞), 로봇 1대 / ∞대, locker M=0 / M=∞, 모든 라이더가 한 모드 선택 시 KPI 거동
4. **Sanity test**: locker 수↑ → H3 라이더 대기시간 단조 감소, EV 수↑ → EV 대기시간 단조 감소 등 인과 일관성
5. **G/G/c docking (Allen–Cunneen)**: 핸드오프 zone (H2 큐잉) 및 LockerBank 를 G/G/c 대기시스템으로 근사:
   ```
   Wq ≈ (ρ^√(2(c+1)) / (c · (1−ρ))) · ((Cs² + Ca²) / 2) · (1/μ)
   ```
   ABM 정상상태 평균 대기시간이 이 근사값과 ±20% 이내 부합하는지 확인
6. **Replay-driven docking**: Replay 모드로 주입된 K=50 시나리오 1건에 대해 **이상적 배달시간 lower bound**:
   ```
   lower_bound = ord_time + cook_time + travel_time_external 
               + service_time_handoff + travel_time_internal(픽업→고객)
   ```
   ABM 출력 평균 배달시간이 lower bound 를 *반드시* 상회하는지 시나리오·주문 단위로 검증. 위반 시 모델 버그
7. **Travel time decomposition**: 주문당 배달시간을 5성분으로 분해:
   ```
   actual_delivery_time = lower_bound + handoff_wait + EV_wait 
                        + handling_overhead + congestion_overhead
   ```
   - `handoff_wait` = 라이더↔로봇 매칭 대기 (mode-dependent)
   - `EV_wait` = 로봇이 EV4 호출 후 탑승까지 대기시간
   - `handling_overhead` = 픽업/드롭 처리시간이 lower bound 와 다른 경우
   - `congestion_overhead` = 복도 혼잡 감속 추가시간
   각 성분의 평균·95p 를 시나리오별 KPI 로 보고. SCIE 투고 figure 로 stacked bar 제시
8. **라이더 도착 시계열 face validity (handoff 특화)**: STAGE 1 의 `t_rider_arrival(i)` 합성 결과가 (a) 배민 시나리오의 ORD_TIME + COOK_TIME + 평균 travel 의 직관과 일치하는지 시점별 plot, (b) K stratum 별 도착률이 λ_K(t) 와 *시간 shift* 관계만 갖는지 cross-check. 산출물: `figures/rider_arrival_validity_K{50,100,200,500,1000}.png`

**Replication**: 시나리오당 시드 30개 이상, Welch 신뢰구간, **Common Random Numbers** 로 분산 감소. K stratum 별 (시나리오 수 × seed) 구성:
- K=50: 2 시나리오 × 30 seed = 60
- K=100: 9 × 30 = 270
- K=200: 9 × 30 = 270
- K=500: 5 × 30 = 150
- K=1000: 5 × 30 = 150
시나리오 수가 적은 stratum (K=50) 은 floor 배정 시드 다양화로 effective replication 확보.

### 7.2 실험 시나리오 (factorial design)

기본 factorial: **4 modes × 5 K × 2 typology × 30 seeds = 1,200 runs** (core baseline sweep)

| ID | 시나리오 | 독립변수 | 데이터 트랙 | 목적 |
|---|---|---|---|---|
| **E1: Mode comparison @ baseline** | K=50, 5F, baseline 파라미터 | H ∈ {H0,H1,H2,H3} | Replay K=50 시나리오 2건 × 30 seed | 모드 간 기본 KPI 비교 |
| **E2: K-sweep** | 5F, baseline | H × K ∈ {50,100,200,500,1000} | Replay K-stratum × seed | 수요 강도별 dominant mode 전환 |
| **E3: Typology** | K ∈ {200,500,1000} | H × typology {5F, 10F} | Replay K=200~1000 | 빌딩 규모/수직 병목 영향 |
| **E4: Locker sizing** | H=H3, K=200, 5F | M ∈ {2,4,8,16}, V_max ∈ {50,70,100,200} | Replay K=200 | H3 의 locker 자원 최적 sizing |
| **E5: Rider wage sensitivity** | H ∈ {H1,H2,H3} | w_R ∈ {5k, 10k, 15k, 20k} KRW/h | Replay K=50,100 | break-even w\* 도출 |
| **E6: Pareto frontier** | full factorial 후처리 | H × K × typology | E1–E3 통합 분석 | 3-stakeholder Pareto |

### 7.3 KPI 정의 (3-stakeholder 분리)

#### 라이더 KPI
- **T_lobby**: 라이더의 빌딩 잔류시간 (lobby_entry → exit) [s]
- **R_handoff**: 시간당 처리량 (라이더의 시간당 가능 처리 주문 수)
- **W_rider**: 시간당 실효 소득 = `(fixed_cost + var_cost × N_actual) / T_busy` [KRW/h]
- **L_rider_abandon**: 인내 임계 초과 abandon 비율

#### 고객 KPI
- **T_e2e**: 외부 ORD_TIME ~ 고객 인도까지 평균/95p 총 배달시간 [s]
- **L_sla_violation**: 플랫폼 SLA 위반율 = `P(T_e2e > DLV_DEADLINE)`. DLV_DEADLINE 은 시나리오 데이터의 배민 ETA (cook + 거리 + 식당 정확도 알고리즘 산출)
- **S_customer**: 만족도 = `σ(−β · max(T_e2e − DLV_DEADLINE, 0))` — deadline 이내 도착 시 σ(0)=0.5, 초과 시 deadline 대비 초과 시간에 비례 감소 (deadline-relative 정식화)

#### 빌딩 KPI
- **NPV_5y**: 5년 NPV (모드별 CAPEX/OPEX 차이 포함)
- **U_robot**: 로봇 가동률
- **U_locker**: locker 점유율 (H3 한정)
- **W_EV4**: EV4 평균 대기시간
- **Cost_per_order**: 모드별 주문당 비용

### 7.4 NPV 식 (3-stakeholder 분리)

```
RiderEarnings_H(λ, w_R) = Σ_t [ (fixed + var × N_t) − w_R × T_lobby_t ]
                          // 빌딩 잔류시간의 시간단가 손실 차감

CustomerSurplus_H(λ)    = Σ_t S_customer(T_e2e_t)
                          // SLA 만족도의 합; deadline 초과 시 음 가중 (renege 모델 없음, §6.2)

BuildingNPV_H(λ, T=5y)  = −C_acq_H + Σ_{t=1}^{T} [Revenue(λ,t) − C_OPEX_H(t)] / (1+r)^t
                          + C_salvage / (1+r)^T

C_acq_H0 = 0                                    // 라이더 직접; 빌딩 CAPEX 없음
C_acq_H1 = N_robot × C_robot                     // 동기; 로봇 CAPEX 만
C_acq_H2 = N_robot × C_robot + C_queue_zone      // 큐잉; 로비 큐 zone 마킹·관리비
C_acq_H3 = N_robot × C_robot + M × C_compartment + C_locker_install
                                                 // locker bank CAPEX 추가
```

### 7.5 Break-even 식 (RQ4)

**라이더 시간단가 break-even w\***:
```
w_R*  s.t.  BuildingNPV_H3(λ_baseline, w_R*) + α_R · ΔRiderEarnings_H3_vs_H1(w_R*) 
            = BuildingNPV_H1(λ_baseline, w_R*) + α_R · 0
```
α_R 은 빌딩 관리자가 라이더 후생을 NPV 결정에 반영하는 가중치 (정책 lever; baseline α_R = 0, sensitivity α_R ∈ [0, 1]).

**수요 break-even λ\* (mode dominance 전환)**:
```
λ_{H1→H3}*  s.t.  Pareto_dominance(H3, H1) | λ=λ*  changes sign
```
Hypervolume indicator 의 부호 전환 지점으로 정의.

λ\*, w\* 의 신뢰구간은 시나리오 반복 30회 기반 bootstrap (B=1000) 으로 산출.

### 7.6 Pareto frontier 분석 (RQ3 핵심)

- **3차원 objective**: maximize (W_rider, S_customer, BuildingNPV_5y)
- **Pareto front 계산**: 4 modes × 5 K × 2 typology = 40 점을 plot
- **지표**:
  - **Hypervolume indicator** (reference point 기준)
  - **ε-dominance counts** (모드별 비지배 빈도)
  - **C-metric** (set coverage; mode A 가 mode B 의 점 중 몇 % 를 지배하는가)
- **시각화**:
  - 3D scatter + 2D projection (라이더↔고객, 고객↔빌딩, 라이더↔빌딩)
  - K 별 색상, mode 별 마커
  - 산출물: `figures/pareto_3d.png`, `figures/pareto_projections.png`

### 7.7 민감도 분석

- **DoE**: Latin Hypercube Sampling 으로 주요 파라미터 공간 샘플링
- **Morris elementary effects** (스크리닝): 12 파라미터 × 10 trajectories
- **Sobol total-order index** (정량): 상위 6 파라미터
- **대상 파라미터** (12개): w_R, M, V_max, locker 도킹 시간 μ, 라이더 인내 τ, 로봇 수, K (수요 강도), α_lobby_extra, 할인율 r, 사회적 수용성 α, locker CAPEX, ε noise σ
- **층 분포 prior** (uniform vs 점심시간 중심층 가중) 도 별도 sweep 으로 강건성 검증
- **산출물 (Tornado plot)**: KPI (T_e2e 평균/95p, W_rider, NPV, hypervolume) 별 Sobol bar chart — `experiments/results/figures/tornado_handoff.png`. 논문 핵심 figure

---

## 8. 학술적 Contribution

1. **로비 핸드오프 design space 의 ABM 정식화** — H = {direct, sync, queued, locker} 4-mode taxonomy 와 각 모드의 process model 을 indoor robot delivery ABM 의 1급 분석 차원으로 격상. 기존 연구는 외부 라이더 ↔ 내부 로봇 인터페이스를 추상화하거나 무시.
2. **3-stakeholder Pareto trade-off 프레임워크** — 라이더(gig welfare) · 고객(SLA) · 빌딩(NPV) 의 KPI 를 *동일 시뮬레이션 내* 에서 산출하고 hypervolume · ε-dominance · C-metric 으로 평가하는 평가체계. 기존 indoor robot ABM 의 단일 stakeholder (운영자) 한계 보완.
3. **외부 라이더 도착 시계열의 결합 합성** — 배달 플랫폼 데이터의 ORD_TIME + COOK_TIME + DIST/speed 의 *결합 시계열* 을 빌딩 boundary condition 으로 합성하는 calibration 방법론. **Time–Space Decoupled Calibration** 의 도시-빌딩 인터페이스 적용 사례.
4. **자동 도킹 locker 의 break-even 분석** — locker CAPEX 와 라이더 회전율 향상 · EV 부하 감소를 NPV 식에 동시 반영, w\* (라이더 시간단가) 와 λ\* (수요 강도) 의 2단 break-even 정식화.
5. **8-step Partial V&V 템플릿** — 부분 캘리브레이션 + face validity + extreme-value + sanity + G/G/c docking + Replay-driven docking + Travel time decomposition + 라이더 도착 시계열 face validity. Sargent (2013) V&V 프레임워크에 *외부 입력 시계열 검증* 단계를 추가한 데이터-부재 신생 시스템용 확장.
6. **재현성** — 모든 코드 · 시드 · 설정 공개 (GitHub + Zenodo DOI), `pyproject.toml` lock 제공.

### 타겟 저널 (SCIE) — 1순위 확정

| 저널 | IF | Fit | 비고 |
|------|----|-----|------|
| **Simulation Modelling Practice and Theory** | ~4.0 | ★★★★★ | **1순위 (확정)** — ABM 방법론 + 4-mode design space 색채 최적합 |
| Transportation Research Part E | ~10.6 | ★★★★ | Gig-economy welfare + last-mile logistics 색채 강화 시 2순위 |
| European Journal of Operational Research | ~6.4 | ★★★★ | NPV · Pareto · break-even 의 OR 색채 강화 시 |
| Computers & Industrial Engineering | ~7.2 | ★★★★ | 운영 · 비용 · locker 시스템 색채 강화 시 |
| Robotics and Autonomous Systems | ~4.3 | ★★★ | 로봇 측 기여 강화 시 |
| JASSS | ~2.5 | ★★★ | 순수 ABM 커뮤니티 |

> *Automation in Construction* (IF 10.3) 은 건설·BIM 중심으로 본 주제와 미스핏 → 후보 제외.

---

## 9. 시뮬레이션 플랫폼 선정 근거

### 9.1 플랫폼 비교

| 플랫폼 | Python 친화 | 확장성 | 시각화 | 학술 인지도 | 추천도 |
|--------|:-----------:|:----:|:-----:|:---------:|:-----:|
| **Mesa** | ★★★★★ | ★★★★ | ★★★ → ★★★★ (Solara) | ★★★★ | **1순위** |
| GAMA | ★★ | ★★ | ★★★★★ | ★★★★ | 2순위 |
| NetLogo + pyNetLogo | ★★★ | ★★ | ★★★★ | ★★★★★ | 3순위 |
| Custom (SimPy) | ★★★★★ | ★★★★★ | ★★ | ★★★ | 특수용 |

### 9.2 선택: Mesa
- 순수 Python → 분석·논문 figure 파이프라인 일관
- `SolaraViz` 내장 + `matplotlib.animation` + `networkx` 로 GAMA 대비 시각화 약점 보완
- BatchRunner 로 시나리오 × 시드 병렬 실행 자동화
- 풍부한 학술 publication 이력

### 9.3 환경 — Python 3.13
- venv 는 `uv` 로 관리, 인터프리터 Python 3.13.x
- 모든 신규 에이전트 (ExternalRider, Locker, BuildingManager) 는 Mesa 기본 API 사용 → 추가 의존성 없음

### 9.4 핵심 패키지

| 분류 | 패키지 | 용도 |
|---|---|---|
| ABM 코어 | `mesa>=3.0` | Agent/Model/Scheduler/DataCollector |
| 시각화 | `solara`, `altair`, `matplotlib`, `seaborn` | SolaraViz + 정적 figure |
| 공간/그래프 | `networkx`, `shapely` | 층·복도 그래프, 경로 |
| 수치·데이터 | `numpy`, `pandas>=2.2`, `pyarrow` | 분석, parquet I/O |
| 통계/피팅 | `scipy>=1.13`, `statsmodels`, `scikit-learn` | NHPP·분포 피팅 |
| 민감도 분석 | `SALib` | Morris / Sobol |
| Pareto 분석 | `pymoo` 또는 자체 hypervolume 구현 | hypervolume / ε-dominance |
| 실험 관리 | `pyyaml`, `tqdm`, `joblib`, `hydra-core`(선택) | config, 병렬 |
| 노트북 | `jupyterlab`, `ipykernel` | EDA |
| 테스트/품질 | `pytest`, `ruff`, `mypy` | 회귀 테스트 |

---

## 10. 프로젝트 디렉토리 구조

```
abm_pa/
├── data/
│   ├── data1/                  # 배민 원본 (K=50~2000)
│   ├── data2/                  # STAGE3 테스트셋
│   └── data_ex.txt             # 공식 스키마
│
├── configs/
│   ├── baseline.yaml
│   ├── modes/
│   │   ├── h0_direct.yaml
│   │   ├── h1_sync.yaml
│   │   ├── h2_queued.yaml
│   │   └── h3_locker.yaml
│   ├── scenarios/              # E1 ~ E6
│   └── sensitivity.yaml
│
├── analysis/                   # STAGE 1
│   ├── load_data.py
│   ├── run_analysis.py
│   ├── demand_model.py         # NHPP λ(t), F_prep, VOL, lead_time
│   ├── scenario_loader.py      # Replay 인터페이스
│   ├── rider_arrival_model.py  # 라이더 도착 시계열 합성 (§2.5)
│   ├── fitted_params.json
│   ├── fit_report.md
│   └── figures/
│
├── simulation/                 # STAGE 2~3
│   ├── model.py                # BuildingHandoffModel (mode flag)
│   ├── space.py                # networkx 그래프 + 로비 zone
│   ├── costs.py                # 3-stakeholder NPV
│   ├── agents/
│   │   ├── customer.py
│   │   ├── external_rider.py   # 신규
│   │   ├── robot.py
│   │   ├── locker.py           # 신규
│   │   ├── building_manager.py # 신규
│   │   ├── control_system.py
│   │   ├── elevator.py
│   │   └── pedestrian.py
│   └── visualize.py            # SolaraViz + 로비 zone 패치
│
├── experiments/                # STAGE 4
│   ├── e1_mode_baseline.py
│   ├── e2_k_sweep.py
│   ├── e3_typology.py
│   ├── e4_locker_sizing.py
│   ├── e5_wage_sensitivity.py
│   ├── e6_pareto.py
│   ├── validation.py           # 8-step V&V
│   ├── sensitivity.py          # Morris / Sobol
│   └── results/
│       ├── figures/
│       └── tables/
│
├── tests/                      # pytest
│   ├── test_agents.py
│   ├── test_elevator_physics.py
│   ├── test_locker.py
│   └── test_cost_model.py
│
├── notebooks/                  # 탐색용
│
├── paper/                      # STAGE 5
│   ├── figures/
│   └── tables/
│
├── pyproject.toml
├── requirements.txt
├── .python-version             # 3.13
└── research_framework_handoff.md   # 본 문서
```

---

## 11. 윤리 · 데이터 거버넌스 · 재현성

- **데이터 라이선스**: 배민 라이더 배달 데이터의 출처(공모전/공개 배포/연구용 제공)와 재사용 범위를 논문 Data Availability 섹션에 명시. SHOP / DLV 좌표의 역식별 위험은 *시간적 합성에만 사용하고 공간 매핑은 하지 않는* 본 연구의 time–space decoupled 원칙으로 회피.
- **라이더 데이터 윤리**: 개별 라이더 ID 가 부재한 시나리오 단위 데이터를 사용하므로 개인 식별 위험 없음. 라이더 시간단가 w_R 은 RIDERS table 의 type 별 평균치만 사용.
- **IRB**: 인간 피험자 실험 부재 → 일반적으로 IRB 면제. 도메인 전문가 인터뷰 (face validity, §7.1 step 2) 수행 시 소속 기관 기준 확인.
- **vendor 견적 데이터**: locker / 로봇 CAPEX 는 vendor inquiry 결과 명시 또는 "N/A — vendor inquiry" + sweep ±100% 표기.
- **재현성**: 시드 · configs · 코드 · 로그 전부 공개 (GitHub + Zenodo DOI), `pyproject.toml` 의 의존성 lock 제공.
- **윤리(로봇-사람 공존)**: 사회적 수용성 α 와 α_lobby_extra 는 모델 파라미터이며, 실제 빌딩 도입 시 사용자 수용성 연구가 선행되어야 함을 논문 Discussion 에 기술.

---

## 12. 작업 일정

| 단계 | 작업 내용 | 예상 기간 |
|------|----------|----------|
| STAGE 1 | 외부 라이더 도착 시계열 합성 + K-stratum 분석 + w_R 캘리브레이션 | 2~3주 |
| STAGE 2 | 빌딩 공간 + 로비 zone + LockerBank networkx 모델링 | 1~2주 |
| STAGE 3 | 8-agent ABM 구현 (Mesa) + 4-mode dispatcher + 디버깅 | 5~7주 |
| STAGE 4 | 8-step V&V + E1~E6 실험 + 3-stakeholder Pareto + Morris/Sobol | 5~6주 |
| STAGE 5 | 논문 작성 & SMPT 투고 + 수정 사이클 | 4~6주 |
| **합계** | | **17~24주 (4.5~6 개월)** |

---

## 13. 참고 문헌 방향 (키워드 클러스터)

투고까지 최소 30~45편 정리 필요. 다음 클러스터를 중심으로 체계적 문헌 조사 수행.

1. **Indoor / last-50-meter robot delivery**: Savioke Relay(병원), Starship Technologies(대학), Bear Robotics Servi, Dilly Drive 운영 사례
2. **Shared vertical mobility (Robot-Elevator integration)**: 로봇-엘리베이터 스케줄링, human-robot shared EV 연구
3. **ABM in service operations**: Mesa 기반 logistics/service ABM
4. **Data-driven ABM calibration**: 어울링 PBSS, bike-sharing, ride-hailing calibration
5. **Simulation validation methodology**: Sargent (2013) "Verification and Validation of Simulation Models", Axelrod docking
6. **Sensitivity analysis**: Saltelli et al. global sensitivity, Morris/Sobol
7. **Techno-economic analysis of service robots**: TCO, break-even, NPV 기반 평가
8. **Parcel locker / smart locker systems**: Iwan et al. (2016), Rohmer & Gendron — 도시 last-mile locker 입지·크기·운영
9. **Human-robot handover (HRC)**: Cakmak et al., Strabala et al. — 로봇-사람 물체 인계의 안전·시간 모델
10. **Gig-economy welfare quantification**: Chen et al. (2019), Hall & Krueger — 플랫폼 라이더 idle time, earnings 분석
11. **Multi-stakeholder Pareto / hypervolume in service systems**: Zitzler & Thiele — hypervolume indicator, Deb — NSGA-II 평가 metric

### 주요 공식 문서
- Mesa: https://mesa.readthedocs.io/
- SALib: https://salib.readthedocs.io/
- pymoo: https://pymoo.org/

---

## 14. 즉시 다음 단계 (이 framework 승인 후)

1. **STAGE 1 즉시 착수**: `analysis/rider_arrival_model.py` 구현 + K-stratum λ_rider,K(t) figure 5장 산출 → face validity 1차 검증
2. **STAGE 3 코드 스켈레톤**: `simulation/agents/external_rider.py`, `locker.py`, `building_manager.py` 의 클래스 시그니처와 unit test 우선 작성
3. **E1 baseline run**: H0~H3 × K=50 × 30 seed 의 첫 실험 → 4-mode 의 KPI 격차가 통계적으로 유의한지 1차 확인 (negative result 시 framework 재검토 trigger)
4. **Pareto 1차 plot**: E1 결과로 3D Pareto frontier 초안 → contribution #2 (3-stakeholder) 의 가시성 확인
