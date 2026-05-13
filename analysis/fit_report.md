# STAGE 1 적합 리포트

전체 시나리오: **39개**, 총 주문: **13,450건**

## 1. NHPP λ(t)
- 풀링 적합: 39개 시나리오, horizon ≈ 4.0 h
- K-stratum 적합 (시나리오 수):
  - K=50: 2 시나리오, horizon ≈ 1.00 h
  - K=100: 9 시나리오, horizon ≈ 1.00 h
  - K=200: 9 시나리오, horizon ≈ 1.00 h
  - K=500: 5 시나리오, horizon ≈ 4.00 h
  - K=1000: 5 시나리오, horizon ≈ 4.00 h

## 2. 음식 준비시간 F_prep
- 최우수 분포 (AIC): **gamma** params = (4.681, 0, np.float64(223.417)), AIC = 202417.8
- AIC 비교:
  - gamma: AIC = 202417.8  ←
  - weibull: AIC = 202761.2
  - lognormal: AIC = 203224.4
- mean = 17.4 min, median = 15 min
- 주의: 데이터는 5분 단위 이산값 → 연속분포 가정 하에서 KS 통계량 과대평가

## 3. 주문 부피 VOL
- mean = 27.8, median = 24
- 활용: LockerAgent V_max baseline 100 결정 근거 (q95 ≈ 70)

## 4. 배달 리드타임 (DLV_DEADLINE − ORD_TIME)
- q05 = 36.2 min  (CustomerAgent τ_abandon 하한 anchor)
- q50 = 53.8 min
- q95 = 79.1 min

## 5. 도로망 픽업-드롭 거리 (context)
- mean = 1.54 km, max = 6.79 km
- 빌딩 내부 거리는 §5 networkx 그래프에서 별도 산출
- 본 페이퍼는 라이더 빌딩 도착 시각 합성식의 travel_time 항에 이 거리를 사용

## 6. 라이더 시간단가 w_R (KRW/h)  — throughput 50건/h 가정
- BIKE: 10,000
- WALK: 5,500
- CAR: 11,000

## 7. 산출 figure (analysis/figures/)
- fig_lambda_pooled.png — 풀링 NHPP λ(t)
- fig_lambda_by_K.png — K-stratum λ_K(t)
- fig_k50_per_scenario_arrivals.png — K=50 face validity
- fig_cook_time_fit.png — 분포 적합 + AIC 비교
- fig_vol_distribution.png
- fig_lead_time.png
- fig_pickup_drop_distance.png
- fig_rider_arrival_lambda_K.png — §2.5 합성 결과 + bootstrap CI

## 8. fitted_params.json 키 구조
- `pooled`, `by_K[K]`: DemandModel.to_dict() 직렬화
- `rider_arrivals_by_K[K]`: λ_rider,K(t) + 95% CI
- `w_R_by_type_krw_per_h`: 라이더 시간단가
- `summary`: 핵심 요약 통계