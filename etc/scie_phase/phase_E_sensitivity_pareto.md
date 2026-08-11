# Phase E — Morris→Sobol 민감도 + 3-stakeholder Pareto + 논문 figure 전량 (주 11~13)

> 상위 정본: `etc/research_plan_scie.md` §6 Phase E·§4 RQ3·§9.2 figure 목록.
> 선행 조건: Phase D 완료(`results/scie/` 데이터 + RQ1/RQ2 판정 메모).
>
> **변경 기록 (2026-07-23)**: H2 개정(renege → 알림 balk)에 따라 Morris 파라미터
> τ_patience → C_th(balk 비용 임계)로 교체, E5 robustness 각주에서 "포기 규칙 대안"
> 삭제. §9.2 figure ⑮(balk율 곡선)가 E4 목록에 추가됨. 그 외 무변경.
>
> **변경 기록 (2026-08-04, 문서 개정 ⓑ)**: H0 v2 완료 반영 — ①**Fable 배정 → 오퍼스**
> (결정 #22; E5·해석 구간은 **세션 오퍼스/max**) ②figure ⑦의 "EV1/EV2 분리" →
> **전용(EV1·EV2)/공용(EV3·EV4) 분리**(EV 4대) ③§4 리스크 1의 진단 인용 경로·수치
> 정정 ④**CRN 이득 전제 철회**(아래 §4 리스크 4 신설). 상세는
> `scie_phase/README.md` 2026-08-04 항목.

---

## §0. 이 Phase를 처음 보는 사람을 위한 배경

Phase D가 "기본 파라미터에서 모드들이 어떻게 다른가"를 답했다면, 이 Phase는 남은
두 질문을 답하고 논문의 시각 자료를 완성한다:

1. **결과가 파라미터 선택에 얼마나 민감한가?** — 우리 모델에는 데이터로 캘리브레이션한
   값(수요·조리 시간 등)도 있지만, 가정으로 정한 값(balk 비용 임계 C_th, 락커 도킹
   20초, 할인율 5% 등)도 있다. 리뷰어는 반드시 "그 가정을 바꾸면 결론이 뒤집히는가"를 묻는다.
   **전역 민감도 분석**이 그 답이다: Morris 기법으로 12개 파라미터를 저비용
   스크리닝(어느 것이 중요한지 1차 선별)한 뒤, 상위 6개에 Sobol 지수(각 파라미터가
   결과 분산의 몇 %를 설명하는지)를 정밀 산출한다. 파이썬 SALib 패키지 사용.
2. **세 이해관계자의 이해가 어떻게 상충하는가?** — 모드마다 라이더·고객·빌딩 지표가
   다른 방향으로 움직인다(예: H3는 라이더 최상이지만 빌딩 CAPEX 최대). 이를 3차원
   목적 공간의 **Pareto frontier**(어느 한쪽을 희생하지 않고는 개선 불가능한 해들의
   경계)로 정리하고, hypervolume(경계가 덮는 부피)·ε-dominance(비지배 빈도)·
   C-metric(모드 간 지배 커버리지)으로 정량화한다 — RQ3의 답.

그리고 논문에 들어갈 **figure 12~14장·table 6~8개 전량**을 여기서 스크립트로 생산한다
(수기 수치 금지 — 레포 관례).

**이 Phase의 필수 용어** (상세: research_plan_scie.md §0.6): Morris / Sobol / LHS /
Pareto frontier / hypervolume / ε-dominance / C-metric / tornado plot(파라미터 영향
순위를 가로 막대로 보여주는 표준 그림).

---

## §1. 목표와 완료 기준

**완료 기준**:
1. Morris 스크리닝 12 파라미터 완료 + 상위 6개 Sobol total-order 지수 산출(`results/scie/sensitivity/`).
2. Pareto 분석 완료: frontier 좌표 + hypervolume·ε-dominance·C-metric 표.
3. §9.2 figure·table 전량이 스크립트 재실행으로 재생산 가능한 상태(`paper/figures/`·`paper/tables/`).
4. 층 프로파일 sweep의 강건성 결론(uniform 기준 결론이 bottom/top에서 유지·역전되는지) 정리.
5. 전체 스위트 green, 진행 로그 기록.

---

## §2. Step별 상세

### Step E1 — Morris 스크리닝 (배정: 소넷 / medium 구현 + 세션 해석, ~1.5일)

**무엇을**:
1. `experiments/sensitivity_morris.py` — SALib Morris 표준 패턴: 12 파라미터 × 10 궤적.
   대상 파라미터(범위는 구 framework §7.7 기준 + Phase B·C 동결값): w_R [5k, 20k],
   락커 M {2,4,8}, V_max [50, 200], 도킹 시간 μ [10, 40]s, C_th [5, 15]분 BIKE
   등가(원화 환산 — 2026-07-23 τ_patience 대체),
   로봇 대수 {1,2,3}, 수요 배수, 할인율 r [0.03, 0.08], 사회적 수용성 α, 락커 CAPEX
   ±100%, 인계 시간 μ [30, 90]s, 노이즈 σ_ε [0, 0.30].
2. 반응 KPI: T_e2e 평균/p95, T_lobby, W_EV, NPV, (모드별 실행 — 로봇 모드 3종 중심).
3. 산출: 파라미터별 μ\*(평균 영향)·σ(상호작용 지표) 표 → 상위 6개 선별.
4. **해석은 세션(오퍼스/max)**: 선별 결과가 도메인 직관과 부합하는지(예: 로봇 대수·w_R가
   상위권이어야 정상), 이상 신호 시 범위 재점검.

### Step E2 — Sobol 정밀 분석 (배정: 소넷 / medium 구현 + 세션 해석, ~1일)

**무엇을**: Morris 상위 6개 파라미터에 Saltelli 표본 → Sobol total-order 지수.
KPI별(T_e2e, W_rider, NPV, hypervolume) tornado plot 데이터 산출. 실행 규모가 커지면
(N × (2k+2) run) K 대표 시나리오 축소를 먼저 적용(절단 순서 §4).

### Step E3 — Pareto 지표 구현·분석 (배정: 오퍼스 / medium, ~1~1.5일)

**왜**: hypervolume 계산은 기준점 선택·정규화·지배 판정의 수치 함정이 있어 검증 가능한
구현이 필요하다(pymoo 사용하되 소규모 수기 예제로 대조).

**무엇을**:
1. `analysis/pareto_analysis.py` — 3차원 목적(W_rider ↑, 고객 지표 ↑(−T_e2e p95),
   BuildingNPV ↑) 공간에서 4모드 × 5 K = 20점(각 점은 30 seed 평균 + CI):
   - 비지배 정렬 → frontier 추출
   - hypervolume(기준점 = 각 축 최악값 − 여유; 기준점 민감도 1회 병기)
   - ε-dominance 빈도, C-metric 쌍별 행렬
2. 수기 대조 테스트: 손으로 지배 관계를 판정할 수 있는 4~5점 소예제로 구현 검증.
3. **RQ4 연결**: hypervolume 부호 전환으로 λ\*(모드 지배 전환 수요) 판정 + bootstrap CI.

### Step E4 — 논문 figure·table 전량 생산 (배정: 소넷 / medium, ~2일)

**무엇을**: `analysis/paper_figures.py`(단일 진입점, 전 figure 재생산 가능)로 §9.2 목록
전량 — ①빌딩·로비 존 도해 ②4-모드 프로세스 상태도 ③라이더 도착 합성 검증(STAGE 1
재인용) ④배달 시간 분해 stacked-bar(모드×K) ⑤T_lobby 페어드 CI ⑥T_e2e p95 모드×K
⑦W_EV **전용(EV1·EV2)/공용(EV3·EV4) 분리**(양면 외부성 — EV 4대) ⑧계단 손실 메커니즘 ⑨경계 히트맵(K×프로파일 우세
모드) ⑩Pareto 3D+2D 투영 ⑪break-even w\* 곡선 ⑫tornado(Sobol) ⑬deadline
counterfactual ⑭G/G/c 대조. Table: 데이터 요약/파라미터/design matrix/게이트 요약/주
결과/가이드라인/NPV·break-even/민감도 순위.
스타일: dataviz 관례 준수(색·범례·라벨 일관), 전부 `paper/figures/`·`paper/tables/`에
스크립트 출력으로만 존재.

### Step E5 — 가이드라인 표·경계 히트맵 확정 (배정: **세션 오퍼스/max 직접**, ~1일)

**왜**: Contribution 3(실무 의사결정 가이드라인)의 최종 형태 — "이 표를 보고 빌딩
설계자가 무엇을 결정할 수 있는가"는 서사 판단이라 세션 몫.

**무엇을**: ①K(6~63%/h) × 프로파일 격자별 추천 모드 + 근거 KPI + 유보 조건(예: "EV
용량 확충 없이는 로봇 모드 비권장" 류) 확정 ②경계 히트맵의 경계선 판정 규칙(paired CI가
0을 걸치는 셀은 "동률" 표기) ③robustness 각주(프로파일·로봇 대수·C_th 스윕) 문안
(구 "포기 규칙 대안"은 renege 폐지로 삭제 — 2026-07-23).
산출: `etc/note_guideline_table.md`(논문 Discussion 절 초안 재료).

---

## §3. 배정표 요약

| Step | 내용 | 모델 | effort | 기간 | 배정 근거 |
|---|---|---|---|---|---|
| E1 | Morris 스크리닝 | 소넷 | medium (+세션 해석) | 1.5일 | SALib 표준 패턴, 해석은 세션 |
| E2 | Sobol 상위 6 | 소넷 | medium (+세션 해석) | 1일 | 표준 패턴 |
| E3 | Pareto 지표 구현·분석 | 오퍼스 | medium | 1~1.5일 | hypervolume 수치 함정 — 수기 대조 필수 |
| E4 | figure·table 전량 | 소넷 | medium | 2일 | 스크립트 생산, dataviz 관례 |
| E5 | 가이드라인 표 확정 | 세션(오퍼스) | — | 1일 | 실무 서사 판단 |

합계 ~6.5~7일 (주 11~13).

## §4. 리스크·주의점 / 절단

1. **Sobol 실행 규모**: Saltelli 표본이 커지면 대표 시나리오(각 K 1개)로 축소 — Morris는 유지(절단 순서: research_plan_scie.md §10.2의 ③). **단, 이 축소는 대가가 있음을 명시할 것**(2026-08-03 H0 진단, 정본 **`archive/h0_v1/analysis_outputs/h0_insights/note_h0_demand_insights.md`** §6 — *2026-08-04 경로 정정, R0 아카이브 때 이동*): T_e2e는 분산의 76%, 도착 c_a²는 68%가 **within-K 시나리오(패턴) 분산**이라, 각 K를 시나리오 1개로 대표시키면 민감도 지수가 그 시나리오의 특성에 좌우된다. 축소가 불가피하면 ①대표 시나리오를 c_a²·peak10 기준 **중앙값 시나리오**로 선정하고(무작위·첫 파일 금지) ②선정 근거와 이 한계를 Sobol 결과 해석에 각주로 남긴다. **seed를 줄이는 절단이 시나리오를 줄이는 절단보다 싸다** — v2 재측정에서도 seed 분산은 여전히 작다(30 seed CI95 반폭: T_e2e 평균 ≤0.102% · p95 ≤0.300% · T_lobby ≤0.944%; 최광폭은 **W_EV ≤4.54%**로 저부하일수록 넓다). 선정 입력 CSV는 **`results/h0_stats/scenario_traits.csv`**(v2)의 `ia_cv2`·`peak10_over_mean`을 쓴다 — v1 `tables/`가 아니다.

2. **Pareto 20점의 빈약함**: 점이 적어 frontier가 성기면 로봇 대수·락커 M 변형점을 추가해 조밀화(Phase D D4 데이터 재사용 — 추가 실행 없음).
3. **figure의 자동 재생산성**: 단일 진입점 스크립트가 깨지면 Phase F 수치 대조가 불가능해진다 — E4 완료 기준에 "클린 체크아웃에서 전량 재생산" 포함.
4. **🔴 CRN 이득을 전제로 설계하지 말 것 (2026-08-04, 구판 주장 철회)**: 구 계획은
   "`floor_seed` 고정 CRN이 평균계 분산의 30~65%를 제거한다"를 전제했으나, R7 재배치
   후 재측정에서 **철회**됐다. 채널비가 평균계 **0.394~1.217**, p95 **0.995~1.779**로
   흩어져 **대부분 1.0과 통계적으로 구별되지 않는다**(n=30에서 분산비는 F(29,29),
   95% 범위 ≈ [0.48, 2.09]). 명확한 감소는 K300_4 하나뿐이다.
   → Phase E는 **"CRN이 이득을 준다"가 아니라 "이득 여부를 시나리오별로 먼저
   확인한다"**를 전제로 설계한다. Sobol/Morris 표본 예산을 CRN 분산 감소에 기대어
   깎는 계획이 있으면 **그 근거가 사라진 것**이므로 재산정할 것.
5. **로봇 이득의 천장이 민감도 해석을 좌우한다**: T_e2e 단축 상한이 **11.6~13.0%**
   (조리·street가 건물 무관)이므로, **T_e2e를 출력으로 둔 Sobol 지수는 전 파라미터가
   작게 나올 수밖에 없다** — 이를 "민감도 없음"으로 읽으면 오독이다. 1차 출력은
   **T_lobby·W_EV·NPV**로 두고 T_e2e는 보조로 보고한다(Phase D §0 ①과 동일 원칙).

## §5. Phase F로 물려주는 것

figure·table 전량(자동 재생산 가능), 민감도·Pareto 결과, 가이드라인 표 문안,
RQ1~RQ4의 판정 완결 상태 — Phase F는 새 분석 없이 집필·검증·투고만 한다.

## §6. 진행 로그 (인플레이스 기록)

| Step | 배정 | 산출물·핵심 수치 | 세션 독립 재검증 | 상태 |
|---|---|---|---|---|
| E1 | 소넷/medium | — | — | ⬜ |
| E2 | 소넷/medium | — | — | ⬜ |
| E3 | 오퍼스/medium | — | — | ⬜ |
| E4 | 소넷/medium | — | — | ⬜ |
| E5 | 세션(오퍼스) | — | — | ⬜ |
