# STAGE 1 데이터 분석 완료 보고서

> ABM 시뮬레이션의 외생 boundary condition (배민 데이터) 분석 단계 종료.
> 본 문서는 framework `research_framework_handoff.md` §4 의 *실행 결과* 와
> *분석 중에 내린 의미적 정정 결정* 을 함께 정리한 reference 문서이다.
> 코드 산출물은 `analysis/` 에, 본 문서의 *기술* 결과 요약은 `analysis/fit_report.md` 에 있다.

---

## 1. 분석 범위 (cohort) 결정

### Tier-1 cohort 채택
`data/data1/` 의 42개 시나리오 중 **K ∈ {50, 100, 200, 300}** 의 28개만 1차 분석에 사용.

| K | n 시나리오 | horizon | 정합 빌딩 규모 |
|---|---|---|---|
| 50 | 2 | 56–59 min | 500–1,000인 소형 오피스 |
| 100 | 9 | 58–60 min | 1,000–2,000인 중형 오피스 |
| 200 | 9 | 59–60 min | 2,000–4,000인 대형 오피스 |
| 300 | 8 | 60 min | 3,000–6,000인 복합 빌딩 |
| **합계** | **28** | **모두 ~1h** | 점심피크 1h 윈도우와 직접 정합 |

### Tier-2 (보류)
K=500/1000 은 stratum 내부에 horizon 1h/2h/4h 가 *혼재* — λ_K(t) 적합 시 60min 이후 cliff artifact 발생. 60min truncate 또는 horizon sub-stratify 후 별도 트랙으로 분석 예정.

---

## 2. STAGE 1 동안 내린 의미적 정정 (referee 사전 대응)

### (1) 풀링 NHPP λ(t) — corpus artifact 이므로 시뮬 입력 금지
- **이전 가정**: pooled λ(t) 가 빌딩 점심피크 수요 패턴
- **실측 발견**: K=50 horizon 1h / K=1000 horizon 4h 등이 *공존* → pooled 후반 bin 에서 분모는 시나리오 수 고정인데 분자는 longer-horizon scenarios 만 기여 → 60/120/240min 의 가짜 step-down
- **결정**: pooled λ(t) 는 **χ² 비정상성 evidence** 로만 사용 (paper supplementary). ABM 시뮬 입력은 **K-stratum λ_K(t) 또는 Replay 모드** 로 한정
- **commit**: `c5afc3f`

### (2) 라이더 타입 샘플링 — capa-conditional 필수
- **이전 가정**: `available_number` 만 가중치로 marginal 샘플
- **실측 발견**: 실 데이터 5,200 주문 중 **1.9%** 가 VOL > 70 (WALK capa). marginal 샘플에서 **0.40%** events 가 WALK 에 VOL > 70 할당 = 데이터 일관성 위반
- **결정**: 각 주문에 대해 `{타입: capa ≥ VOL(i)}` 안에서만 샘플. capa 위반 0 달성
- **영향**: BIKE 13.3% / WALK 20.5% (+0.5%p) / CAR 66.1% (-0.6%p) — 분포 변화 미미
- **commit**: `1bbf493`

### (3) DLV_DEADLINE 재해석 — 플랫폼 SLA target, 고객 인내심 ≠
- **이전 가정**: lead time = DLV_DEADLINE − ORD_TIME 을 CustomerAgent `τ_abandon` (포기 임계) anchor 로 사용
- **실측 발견** (배민 description): DLV_DEADLINE 은 *배민 알고리즘 산출 ETA* (cook + 거리 + 식당 정확도). 즉 **플랫폼이 고객에게 약속한 도착시각** 이지 *고객의 행동적 인내심* 이 아님
- **결정**: lead_time = **플랫폼 SLA target**. 고객 포기 (renege) 행동 자체를 모델링하지 않음 (식음료 배달은 선결제 구조). KPI 는 `L_sla_violation = P(T_e2e > DLV_DEADLINE)` 로 정식화
- **commit**: `5616319`

---

## 3. 분석 항목 (framework §4.1, 8개) — 실증 결과

### 3.1 NHPP λ_K(t) (1차 + 풀링)
- **풀링 (28 시나리오, 5,200 주문)**: mean 186 / max 212 / min 163 orders/h. CV(λ̂) = 0.072 (1h horizon 안에서 *근사 stationary*)
- **χ² stationarity test**: χ² = 27.0, df=11, **p = 4.6 × 10⁻³** → H0 (균등) 기각 → NHPP 채택 정당화
- **K-stratum**: mean = K orders/h 정확히 일치 (∫λ_K dt = K 검증 통과)
  | K | mean | peak | peak/mean | CV |
  |---|---|---|---|---|
  | 50 | 50/h | 78/h @ 30–35min | 1.56 | 0.28 |
  | 100 | 100/h | 149/h @ 10–15min | 1.49 | 0.20 |
  | 200 | 200/h | 237/h @ 10–15min | 1.19 | 0.12 |
  | 300 | 300/h | 326/h @ 5–10min | 1.09 | 0.07 |
- **구조 관찰**: K↑ → CV↓, peak/mean↓ (averaging 효과). 작은 K 는 front-loaded, 큰 K 는 평탄에 가까워짐
- **산출물**: `fig_lambda_pooled.png`, `fig_lambda_by_K.png`

### 3.2 음식 준비시간 F_prep (pooled)
- **최우수 분포 (AIC)**: **Gamma(shape=4.83, scale=213.4 s)**, AIC = 77,969
- **AIC 비교**: Gamma 77,969 < Weibull 78,128 (Δ=159) < Lognormal 78,251 (Δ=282)
- **해석 (Burnham & Anderson 2002)**: ΔAIC ≥ 159 → Akaike weight w(Gamma) ≈ 1.0 (대안의 우주 원자 수 미만 확률)
- **moments**: mean 17.2 min, median 15 min, q90 ≈ 30 min
- **주의**: 원본 5분 이산화 → 연속분포 KS 통계량 다소 부풀려짐 (figure caption 명시)
- **산출물**: `fig_cook_time_fit.png`

### 3.3 외부 이동시간 분포 (pooled)
- per-type mean: BIKE 283 s / CAR 354 s / WALK 1,135 s
- 도로망 픽업-드롭 거리: mean 1.57 km, max 6.79 km
- **산출물**: `fig_pickup_drop_distance.png` (context only)

### 3.4 라이더 빌딩 도착 결합 시계열 (§2.5 합성)
- 합성식: `t_rider_arrival(i) = ORD_TIME + COOK_TIME + (DIST[i][K+i] / speed(type)) × ε`
- `ε ~ Lognormal(-σ²/2, σ²)` multiplicative, baseline σ=0.15, E[ε]=1
- **K-stratum 별 λ_rider,K(t) + 부트스트랩 95% CI** (B=500):
  | K | peak | peak time | mean | CI(peak) |
  |---|---|---|---|---|
  | 50 | 72/h | 72 min | 23/h | [60, 84] |
  | 100 | 103/h | 32 min | 44/h | [87, 117] |
  | 200 | 205/h | 58 min | 71/h | [177, 229] |
  | 300 | 328/h | 72 min | 129/h | [264, 392] |
- **시간 이동**: 주문 peak (10–15min) 가 cook(~17min) + travel(~5min) 만큼 뒤로 이동 → 빌딩 도착 peak 30–70min
- **산출물**: `fig_rider_arrival_lambda_K.png`

### 3.5 라이더 시간단가 w_R 캘리브레이션
- 식: `w_R(type) = fixed_cost + var_cost × throughput`, throughput baseline = 50 orders/h
- **K=50_1 RIDERS 기준**:
  - BIKE: 5,000 + 60 × 50 = **8,000 KRW/h**
  - WALK: 5,000 + 30 × 50 = **6,500 KRW/h**
  - CAR: 5,000 + 100 × 50 = **10,000 KRW/h**
- sensitivity sweep 범위: [5,000, 20,000] KRW/h (framework §4.1.5)

### 3.6 주문 부피 VOL (pooled marginal + capa-conditional 매핑)
- pooled marginal: mean 27.4, median 24, range [5, 100]
- **conditional by rider type** (capa-conditional 샘플링 후):
  - BIKE (capa 100): range [5, 100], mean 27.7
  - WALK (capa 70): range **[5, 70]** — capa 로 정확히 cutoff, mean 26.2
  - CAR (capa 200): range [5, 100], mean 27.6
- **활용**: LockerAgent V_max baseline 100 (q95 ≈ 70 기준 안전여유)
- **산출물**: `fig_vol_distribution.png`, `fig_vol_by_rider_type.png`

### 3.7 Platform SLA 분포 (DLV_DEADLINE − ORD_TIME)
- **정의**: 배민 알고리즘 산출 ETA = cook + 거리 + 식당 정확도 → 고객에게 약속된 도착시각
- **분위수**: q05 = 36.1 min (가장 빠른 약속) / q50 = 51.0 min / q95 = 74.2 min (가장 늦은 약속)
- **사용처**: CustomerAgent.`dlv_deadline_sec` 로 데이터 그대로 주입 → KPI `L_sla_violation`
- **산출물**: `fig_lead_time.png` (title: "Platform SLA distribution")

### 3.8 K 스케일링 패턴
- 검증 항등식: `∫ λ_K(t) dt ≡ K` (K=50/100/200/300 모두 정확히 일치)
- pooled mean = weighted average of K-stratum means = 186 orders/h (cross-validation 통과)

---

## 4. 데이터 사용 모델 — Replay vs Generative

### Replay 모드 (★ 본 paper 주력)
시나리오의 **실제 per-order 데이터** 를 변환 없이 사용.

| 변수 | 입력 출처 |
|---|---|
| 주문 도착 시각 | 시나리오 ORDERS[1] (ORD_TIME) |
| 음식 준비시간 | 시나리오 ORDERS[6] (COOK_TIME) — 식당 입력값 |
| 주문 부피 VOL | 시나리오 ORDERS[7] |
| 픽업-드롭 거리 | 시나리오 DIST[i][K+i] |
| 플랫폼 SLA target | 시나리오 ORDERS[8] (DLV_DEADLINE) |
| 라이더 타입 (per-order) | **capa-conditional 샘플**: `{타입: capa ≥ VOL(i)}` 안에서 available_number 가중 |
| 라이더 속도 | 샘플된 타입의 RIDERS.speed |
| ε (도로 혼잡 noise) | Lognormal(-σ²/2, σ²), σ=0.15 |

→ 합성식 `t_rider_arrival(i) = start + ORD_TIME + COOK_TIME + (DIST/speed) × ε` 만 *모델* — 나머지는 모두 데이터 직접 사용.

### Generative 모드 (stress test 전용)
민감도 sweep ρ-scaling 을 위해 NHPP thinning + 분포 샘플링.

| 변수 | 샘플링 출처 |
|---|---|
| 주문 도착 시각 | `DemandModel.sample_interarrival(t, scale=ρ)` — Lewis-Shedler thinning over λ_K(t) |
| 음식 준비시간 | `DemandModel.sample_cook_time()` — Gamma(4.83, 213.4) |
| 주문 부피 VOL | `DemandModel.sample_volume()` — empirical bootstrap |
| 픽업-드롭 거리 | (Generative 정의 미완) — Replay 모드 우선 권장 |
| 라이더 타입 | capa-conditional 동일 |
| 플랫폼 SLA target | (TODO: per-order DLV_DEADLINE 합성식 필요) |

→ Generative 모드는 **stress test (S4) 전용** — 본 paper main result 는 Replay 모드.

### "pooled" 의 두 가지 사용처 (혼동 방지)

| 사용처 | "pooled" 의미 |
|---|---|
| **분포 적합 (Fitting)** | 28개 시나리오의 5,200 주문을 *통합* 해서 분포 추정 (cook Gamma, VOL pool, lead 분위수, χ² 검정) |
| **Replay 모드 시뮬 입력** | **사용 안 함** — 각 주문의 *실제 데이터 값* per-order |
| **Generative 모드 시뮬 입력** | pooled fit 으로부터 *샘플* |

---

## 5. 산출물 인벤토리

### 코드 (analysis/)
| 파일 | 기능 | 테스트 |
|---|---|---|
| `load_data.py` | JSON 파싱 + Order/Rider/Scenario dataclass | 9 ✓ |
| `scenario_loader.py` | Replay 입력 변환 (BuildingOrder) | 11 ✓ |
| `rider_arrival_model.py` | §2.5 합성 + λ_rider,K 부트스트랩 + capa-conditional | 13 ✓ |
| `demand_model.py` | NHPP fit + Gamma AIC + thinning sampler | 15 ✓ |
| `run_analysis.py` | 전체 파이프라인 오케스트레이션 | (smoke ok) |

### 데이터 산출물
- `analysis/fitted_params.json` — pooled + K-stratum DemandModel, λ_rider,K + CI, w_R
- `analysis/fit_report.md` — 한국어 기술 리포트 (자동 생성)

### Figures (analysis/figures/, 9개)
| 파일 | 내용 |
|---|---|
| `fig_lambda_pooled.png` | Pooled NHPP λ — χ² evidence 용 (시뮬 입력 금지) |
| `fig_lambda_by_K.png` | K-stratum λ_K(t), tier-1 cohort |
| `fig_k50_per_scenario_arrivals.png` | K=50 face validity |
| `fig_cook_time_fit.png` | Gamma fit + AIC 비교 |
| `fig_vol_distribution.png` | VOL marginal |
| `fig_vol_by_rider_type.png` | capa-conditional VOL (BIKE/WALK/CAR) |
| `fig_lead_time.png` | Platform SLA 분포 (no-renege framing) |
| `fig_pickup_drop_distance.png` | 도로망 거리 (context) |
| `fig_rider_arrival_lambda_K.png` | §2.5 합성 + bootstrap CI |

### Tests (48 passed, 5 skipped)
- 5 skipped = STAGE 2/3 stubs (cost_model, elevator_physics, locker, agents)
- 모든 STAGE 1 컴포넌트 unit + integration test 통과

---

## 6. 정합성 검증 요약

| 검증 | 결과 |
|---|---|
| ∫ λ_K(t) dt ≡ K | ✅ 정확히 일치 (K=50/100/200/300) |
| Pooled mean = weighted avg of K-stratum means | ✅ 186 orders/h 양쪽 일치 |
| Gamma cook synth recovery | ✅ shape=4.7 / scale=223.3 generated → recover 4.69 / 223.4 |
| capa-conditional 위반 | ✅ 0 / 26,000 events |
| Rider type distribution sanity | ✅ BIKE/WALK/CAR ≈ 10/15/50 weight |
| Zero-noise deterministic | ✅ same seed → identical events |
| Bootstrap CI envelope | ✅ ci_lo ≤ mean ≤ ci_hi 모두 만족 |
| Framework §4 expected 실증치 vs 실측 | ✅ cook mean 17.2 (예상 17.5), VOL 27.4 (예상 28), lead q05 36.1 (예상 38), pdd 1.57km (예상 1.5km) |

---

## 7. Git 히스토리 (STAGE 1 관련 commits)

| commit | 내용 |
|---|---|
| `329aa32` | initial commit: research framework |
| `c00bb77` | scaffold project skeleton + Python 3.13 venv (uv) |
| `e348a62` | STAGE 1.1: load_data with full scenario schema parsing |
| `46c2071` | STAGE 1.2: scenario_loader.load_replay |
| `131caa4` | STAGE 1.3: rider_arrival_model (core handoff calibration §2.5) |
| `62a5ca8` | STAGE 1.4: demand_model (NHPP + AIC cook fit + samplers) |
| `6ca90d7` | STAGE 1.5: run_analysis pipeline + initial fit artifacts |
| `c5afc3f` | restrict STAGE 1 to tier-1 cohort K in {50,100,200,300} |
| `1bbf493` | enforce capa-conditional rider type sampling |
| `5616319` | reframe DLV_DEADLINE as platform SLA target; drop customer renege |

---

## 8. STAGE 2 진입 조건 — 모두 충족

✅ 외생 입력 (라이더 도착 시계열, SLA target, VOL, cook time) 모두 산출
✅ Replay 모드 / Generative 모드 인터페이스 분리 완료
✅ Capa 제약, no-renege 등 framework 정합성 반영 완료
✅ 모든 단위 테스트 통과, 정합성 검증 통과
✅ Framework `research_framework_handoff.md` §2.4–§7.4 모두 데이터 분석과 일관

→ **STAGE 2 시작 (`simulation/space.py` 5F networkx + 로비 zone) 진행 가능**.

## 9. 잠재적 후속 보강 (선택사항, 페이퍼 revision 단계)

- Cook time QQ plot (Gamma fit visual validity)
- λ_K(t) 자체의 bootstrap CI overlay (현재 rider arrival 만)
- K-scaling 전용 figure (K → mean, K → CV 추세)
- Tier-2 cohort (K=500/1000) 60min truncate 트랙 분석
- Generative 모드의 DIST / DLV_DEADLINE 합성식 정의 (현재 Replay 만 정의됨)
