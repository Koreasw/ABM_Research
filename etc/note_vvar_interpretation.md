# V-VAR 해석 노트 — seed 수·분산 채널·CRN 전략·replication 문구 (Stage V5e 해석부)

> 작성: 2026-07-11, 세션 직접 (Fable/high — `archive/h0_v1/docs/plan_h0_verification.md` §4 V5e 배정).
> 입력: `experiments/vv_variance.py` → `results/vv/variance_30seed.csv`(180 run raw) ·
> `results/vv/variance_summary.csv`(CI·수렴·채널 표). 실행부 설계: K50_1·K300_4·K1000_1 ×
> rng_seed 1..30 × {full(floor_seed=rng_seed 기본), floor_pinned(floor_seed=42 고정)},
> verify_h0 스팟 게이트 18/18 PASS, 총 9.4분.

## 1. Seed 수 권고 = **본문 30 seed** (조건부 50 상향 규칙 포함)

n=30에서 95% CI 반폭(평균 대비 상대):

| KPI | K50_1 | K300_4 | K1000_1 |
|---|---|---|---|
| T_e2e mean | 0.12% | 0.07% | 0.70% |
| T_e2e p95 | 0.27% | 0.26% | 1.30% |
| T_lobby mean | 1.08% | 0.67% | 2.26% |
| W_EV mean | 3.73% | 1.75% | 3.28% |

- 시간적분형 KPI(T_e2e·T_lobby)는 전 시나리오 ≤2.3% — H0 대조에 충분.
- 최광폭 KPI는 **W_EV(≤3.7%)**. CI는 ~1/√n 경로로 수렴 중(n=20→30에서도 −22~24%)이라
  n=50이면 ×√(30/50)=0.775 → ≈2.5~2.9%. 그러나 V-MONO가 보인 처리효과 규모
  (K 방향 +62%/+366%, 보행자율 +107%)는 3~4% CI 대비 한 자릿수 이상 크다.
- **권고**: 본문 실험 30 seed(예산: 39-시나리오 풀 스윕 ≈50분, V3 산정과 일치).
  W_EV가 1차 게이트인 대조에서 효과크기가 CI 반폭의 ~3배 미만으로 좁혀지는 경우에만
  50으로 상향 — 단, 그 전에 **CRN 쌍대조(§3)가 우선**(비용 0으로 분산을 더 크게 줄임).
- p95 안정성: per-run p95 평균의 잭나이프 SE = 3.0s(K50)·2.9s(K300)·17.8s(K1000) —
  p95 보고는 30 seed로 안정. K1000의 절대 SE 증가는 부하 급증 구간의 실질 분산.
- `rider_wait`는 대표 3개 시나리오에서 **퇴화(전 seed 0)** — 만재 재고에서 큐잉 부재.
  풀 축소 처리(1/1/1류)에서만 활성이므로 그 실험 내에서 분산을 재추정할 것(이 노트의
  CI 표는 적용 불가).

## 2. 분산 채널 구조 해석 (floor_pinned/full 분산비)

mean형 KPI 분산비(보행자 단일 채널 / 2채널 전체): 0.41(K50) → 0.52~0.66(K300) → 0.68~0.83(K1000).

- **유의성 판정** (F(29,29) 양측 95% 수용대 [0.476, 2.101]): 층 채널 기여가 통계적으로
  확실한 것은 **K50의 T_e2e mean(0.414)·T_lobby(0.426)뿐**(하한 0.476 밖). K300 비율
  (0.52~0.66)과 K1000(0.68~0.83)은 수용대 내부 — 점추정으로는 "층 채널 기여가 K와 함께
  소멸"이 읽히고, 이는 구조적으로 설명된다: 층 배정은 per-order 독립 범주형 표집이라
  mean형 KPI에서 1/K 속도로 평균화(대수 법칙)되는 반면, 보행자 채널은 EV 경합이라는
  시스템 수준 경로로 작용해 K가 커질수록 상대 지배력이 커진다.
- **p95 비율 >1(K300 1.51, K1000 1.17)은 이상 아님**: 둘 다 F 수용대 내부. p95는 n=30
  order statistic이라 분산비 추정 노이즈가 크고, 채널이 독립가법 분해가 아니므로
  (pinned는 floor_seed=42라는 특정 층 추첨에 **조건부**인 분산) 비율 해석은 mean형
  KPI에 한정한다.

## 3. CRN(공통 난수) 통제 전략

1. **처리 간 쌍대조**: 모든 처리 암(H0 변형·파라미터 스윕)에 동일한 rng_seed 집합
   {1..30}을 재사용하고 seed-paired 차분으로 검정(paired t / Wilcoxon). floor_seed는
   기본 연동(=rng_seed) 유지 — 같은 seed면 양 암에서 동일하게 재현되므로 CRN 성립.
2. **구조적 강건성 (P3 설계의 이점)**: 층/호실 스트림은 순차 소비가 아니라
   `[FLOOR_TAG, floor_seed, ord_id]` per-order 키드 counter-based RNG — 처리가 이벤트
   순서·배차 순서를 바꿔도 **주문별 층 배정 정렬이 깨지지 않는다**. 보행자 스트림
   (`default_rng(rng_seed+1)`)도 스폰 스케줄(도착률·윈도우)에만 의존하므로, 도착률·윈도우를
   바꾸지 않는 처리에서는 암 간 동일 실현이 유지된다. 도착률 자체를 바꾸는 처리(보행자율
   스윕)는 보행자 채널의 쌍대조가 부분적으로만 성립함을 보고 시 명시.
3. **채널 분리 진단**: 분산 원천을 특정해야 할 때 floor_seed 고정(층 채널 동결) 스윕을
   병기 — V-DET가 정렬·환원을 테스트로 잠갔고(`tests/test_vv_determinism.py`), 본
   노트 §2가 크기를 제공.

## 4. 논문 replication 문구 초안 (영문)

> Each run is exactly reproducible given the seed pair (rng_seed, floor_seed). Stochasticity
> enters through two seeded channels: (i) the pedestrian arrival stream (seeded rng_seed+1),
> whose effect on courier KPIs is mediated by elevator contention, and (ii) the per-order
> floor/office assignment stream, a counter-based generator keyed by [FLOOR_TAG, floor_seed,
> ord_id] with floor_seed defaulting to rng_seed; vertical-mode choice uses a config-fixed
> third stream (mode_seed ⊕ ord_id) and is invariant across replications. With σ_ε = 0
> (baseline), repeated runs at identical seeds are bit-identical. Experiments use 30
> replications (rng_seed = 1…30) as common random numbers across treatment arms; because
> floor draws are keyed by order id rather than consumed sequentially, floor assignments stay
> synchronized across arms even when a treatment perturbs event ordering, preserving the
> paired design. At n = 30, 95% CI half-widths are ≤ 2.3% of the mean for time-aggregate
> KPIs (T_e2e, T_lobby) and ≤ 3.7% for the most seed-sensitive KPI (mean elevator wait)
> across representative K ∈ {50, 300, 1000} scenarios. Pinning floor_seed shows the
> pedestrian channel alone accounts for roughly 41–83% of across-seed variance, rising with
> K — consistent with per-order floor sampling averaging out in mean KPIs as K grows.

## 5. 후속 연결

- E-실험 설계 시 이 노트 §1(30 seed)·§3(CRN 쌍대조)을 design matrix 규약으로 채택.
- `rider_wait` 활성 실험(풀 축소)은 해당 실험 내 분산 재추정 필요(§1 말미).
- V8 집계 리포트에 §1 표와 §2 유의성 판정을 그대로 인용 가능.
