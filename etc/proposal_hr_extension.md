# 연구 확장 제안: H0 검증 기반 SCIE 논문 발전 방향

> 2026-07-12 사용자 승인된 제안 원문. 실행 계획서(단계·배정표·설계 동결 규칙)는
> `etc/plan_hr_extension.md`가 정본이며, 이후 진행 로그도 그쪽에 기록된다.

> ## 🔴 지위 (2026-08-04, 문서 개정 ⓑ) — **이력 문서**
>
> 본 문서는 **제안 시점(2026-07-12)의 기록**이며, 그 이후 ①연구 스코프가 2-암 →
> **4-모드**로 확장됐고 ②**H0 v2 개정·검증**이 완료돼 빌딩·수요 전제가 전부 바뀌었다.
> **본문을 갱신하지 않는 이유는 이것이 "그때 무엇을 근거로 무엇을 제안했는가"의
> 기록이기 때문**이다 — 승인 근거를 사후에 고쳐 쓰면 기록으로서 가치를 잃는다.
>
> - **본문의 모든 실측 수치는 v1 조건**(EV 2대·800 ㎡·복도 27 m·지하 없음·38 시나리오)
>   이다 → **인용 금지.** v2 재산출값은 `etc/verification_report_h0v2.md`.
> - **"EV2" = 공용 엘리베이터**라는 표기는 v2에서 **틀리다**(공용은 **EV3·EV4**,
>   EV1·EV2는 사람 전용).
> - 제안 §3의 R3·R4(2-암 실험·경제층)는 **미실행 확정** — Phase D가 대체.
> - 현행 정본 3종: `etc/research_plan_scie.md`(계획) · `etc/HANDOFF_v2.md`(인계) ·
>   `etc/scie_phase/phase_A_robot_h1.md`(Phase A 풀이).

## Context

H0 검증 계획 V1~V8이 완료된 시점(`archive/h0_v1/docs/verification_report_h0.md`: PASS 16 / CAUTION 1 / PENDING 1)에서, 사용자가 검증 내용을 다각도로 분석해 SCIE 논문을 위한 연구 발전 방향을 요청. 제약(사용자 확정): **①로봇/핸드오프 서사 필수**(단 기존 H1/H2/H3 설계를 그대로 따를 필요 없음) **②신규 구현은 소규모**(항목당 며칠~1주, 총 2~3주) **③타겟 저널 SMPT 유지**.

코드 실태: H0만 완전 구현·검증. H1~H3는 전부 스텁(RobotAgent.step/LockerAgent `NotImplementedError`, control_system no-op, costs.py NPV 스텁, model.py 비-H0 모드 raise). 단 그래프 zone·config 키·`shared_with_robot` 플래그 등 확장 표면은 예비됨. 원래 STAGE 3(4-모드 전체)은 5~7주 — 예산 밖.

## 1. 검증 발견 → 연구 함의 (다각도 분석)

| 검증 발견 | 연구 함의 |
|---|---|
| **ev_wait이 K의 지배 성분**(V5a: 22.6→209s), EV util 92~98% 보행자 포화·윈도우 불변(V6-KPIWIN) | 병목은 핸드오프 시간이 아니라 **수직 수송 용량**. "어느 모드가 빠른가"보다 "**엘리베이터가 묶인 제약일 때 로봇 릴레이가 언제 이득인가**"가 진짜 질문 |
| **라이더는 2~5F를 계단 처리**(V5b: 2F 89.6%→5F 0.7%) | 로봇은 계단 불가 → 로봇 전환 시 저층 주문이 EV 수요로 편입되는 **계단 손실 효과**. 검증에서 도출된 비자명 역전 메커니즘(기존 문헌의 핸드오프-시간 중심 비교에 없음) |
| **SLA 판별력 없음**(V5b CAUTION: 위반 전부 K1000, 0.093%) | SLA·S_customer를 1차 KPI로 쓰는 기존 RQ1 설계는 사망. 고객축은 **p95 꼬리 + deadline 강화 counterfactual**(후처리)로 교체 |
| 분산의 보행자(EV 경합) 채널 지배(V5e), CRN 쌍대조 규약 확립 | 2-암 비교에 **페어드 CRN** 즉시 적용 가능 — 모드 간 차이 검정력 확보 설계가 이미 검증됨 |
| 층 프로파일 기계 검증 완료(P3: uniform/bottom/top, floor_seed CRN) | bottom_heavy(계단 손실 최대) vs top_heavy(중립)로 **역전 경계의 형태학 축** 확보 — 추가 구현 0 |
| 실행 예산 실측(V3: K1000 7.6s/run, 33×30 스윕 ≈ 50분) | 2-암 × 프로파일 × 로봇 대수 전체 스윕이 수 시간 — 계산은 제약이 아님 |
| A1~A9 게이트·골든패스·배터리·결정성 체계 | **검증 배터리 자체가 SMPT 방법론 기여**(Sargent 8-step + 입력 시계열 검증 + CRN/윈도우 규약, 영문 replication 초안 기존재) |

검토 후 기각한 대안: H0 단독 용량 한계 논문(로봇 필수 제약 위배), 배차 정책 단독 논문(V5c에서 휴리스틱 Δ 6.4s — 헤드룸 작음, 레버 하나로 흡수), 방법론 단독 논문(단일 사례라 얇음 — 기여 절로 흡수).

## 2. 추천 논문: "H0 vs HR — 용량 매개 로봇 핸드오프 평가"

**HR = 구 H1의 최소화**(enum `H1_SYNC` 재사용, "H1-minimal"로 기술): 라이더가 `lobby_handoff_counter`에서 로봇에 인계(N(60,15²) 절단, 신규 RNG 스트림 태그) 후 즉시 퇴장 → 로봇이 EV2로 상행·인도(30s)·복귀. **제외(집필 시 future work)**: H2 큐/포기, H3 락커, 충전 사이클(SoC 카운터만), 동일층 배칭.

**핵심 가설**: 로봇 릴레이는 라이더 체류(T_lobby)를 줄이지만 ①계단 손실 ②EV2 정원 잠식(15→11) ③주문당 EV2 호출 2회로 수직 용량을 소모 → **저부하·저층중심에서도 이득이 유지되는지, 고부하에서 어디서 역전되는지**의 경계를 매핑. 양면 외부성: EV1 보행자 대기는 개선(라이더 수요 이탈), EV2는 악화 — per-EV KPI로 분리 보고.

**RQ (재편)**:
- RQ1: K×층 프로파일 평면에서 HR의 라이더 후생(T_lobby)·고객 꼬리(p95 T_e2e)·입주자 외부성(보행자 EV 대기) 개선/역전 경계는?
- RQ2: 역전의 메커니즘 분해 — 계단 손실 / slot 점유 / 호출 배증 각각의 기여(검증된 A5 분해 확장)
- RQ3: 로봇 대수·라이더 시간단가 w_R의 break-even(폐형식, costs.py 구현)
- 방법론 기여: H0 검증 배터리 + HR B-게이트 확장 = 재사용 가능한 replay-ABM V&V 템플릿

**SMPT 적합성**: 검증 방법론 전면 배치 + 4-모드 design space는 서론/향후연구로 유지(framework §8 기여 1·5·6 보존, 2·3·4는 축소 재기술).

## 3. 실행 계획 (STAGE R0~R5, 총 14.5~17일)

관례 유지: 단계별 서브에이전트 위임 + 세션 독립 재검증 + `etc/plan_hr_extension.md` 인플레이스 로그.

**R0 설계 동결(0.5일)**: `etc/plan_hr_extension.md` 신설 — 로봇 1대/카 상한, 사람 정원 11 규칙, 핸드오프 분포·스트림 태그(`0x686F6666`), 1주문/트립, 충전 비활성, 연간 환산 규약 명문화.

**R1 구현(5~6일)**:
- R1a 로봇 승객화 + EV 이종 정원 — `robot.py`(GraphWalker 믹스인 재사용, `walker.py:51-133`), `elevator.py:139-170` 보딩 루프 이종 규칙, `model.py:526-529` audit assert 동기 갱신
- R1b `HandoffRiderAgent`(별도 클래스, `external_rider.py` FSM 원본) + control FCFS 디스패치(`control_system.py:50-52` 예비 훅) + model 배선 — **함정 대응: `rider_cls` 도입 후 `agents_of` 8개소 치환**(Mesa `agents_by_type` 정확 클래스 키잉), 모드 게이트 해제(`model.py:109-112`), `robot_leg_records` 신설 + per_order를 ord_id 조인으로 조립(라이더 조기 퇴장으로 기존 rider_records 단독 체인 파손)
- R1c KPI additive — 보행자 EV 대기 p95·EV별 분리·orderspan(기존 `ped_done_log`·`_order_span` 재사용), 로봇 가동률(`_ev_busy_cum` 패턴), `w_ev_mean_all_sec`은 사람 전용 필터 유지
- 게이트: 기존 368 테스트 green + V5d 결정성·골든패스 5케이스 **비트 동일**(H0 무교란) + HR K50_1 audit 스모크

**R2 검증(4~4.5일)**: HR 골든패스 2케이스(0-tick 기준, `test_vv_golden_path.py` 인프라 재사용) / `analysis/verify_hr.py` B1~B9(`verify_h0.py`의 CheckResult·헬퍼 import — B3 로봇 보존: EV1 로봇 보딩 0·boards==alights·종료 시 전원 IDLE) / 단조성 3방향·극한 2케이스 / 38×3 배터리.

**R3 실험(2.5~3일)**: CRN 페어드 2암 × 33 × 30 seed(uniform 전량, bottom/top은 K∈{100,300,500}) → 경계 매핑 + 부록 K750/K1000 / 로봇 대수 {2,3} 스윕 / deadline counterfactual(후처리). 산출 `results/hr/`.

**R4 경제층+집필 재료(2~2.5일)**: costs.py NPV·break-even 폐형식(w_R 선형 — 근찾기 불요) + 분해 figure·경계 히트맵 + `etc/verification_report_hr.md` + framework §6/§7 정합.

**R5 버퍼(1~2일)**: 초과 시 절단 순서 — 프로파일 K 3점 축소(기반영) → 로봇 대수 스윕 폐지 → 단조성 2방향 → counterfactual 단일값 → 부록 HR 생략. **절단 금지**: H0 비트 동일성 게이트·HR 골든패스·B-게이트 배터리(SMPT 기여의 본체).

## 4. 리스크

1. **HR 전패 가능성**(EV2 이미 92~98% 포화): 양면 외부성(EV1 개선)이 서사 구제 + 저K·top_heavy 미우위 시 로봇 대수·핸드오프 60s를 민감도로. 역전이 빨라도 "경계 매핑" 기여는 성립.
2. **탑승 거부 루프**(하행 로봇 vs 만원 카): 버그 아닌 측정 대상 — deny 카운터·report-only 상한으로 계측.
3. **CRN 부분 파손**(동적 풀 내생성): 채널 분해 보고 + 풍부한 풀 robustness 1세트, "실효 함대 확대"로 서사화.
4. 배칭 부재(capa 100 vs VOL~27): 한계 절 명시, future work.

## 5. 승인 후 즉시 실행 범위

1. `etc/plan_hr_extension.md` 작성 — 본 제안의 §2~4를 정식 계획서로(R0 설계 동결 항목 포함, 단계별 모델/effort 배정표: R1 오퍼스/high·R2 오퍼스/medium+오퍼스/max 리뷰(구 Fable 리뷰, 2026-08-03 3차 이관)·R3 소넷/medium·R4 소넷/medium, escalation 규칙 기존 관례).
2. 메모리 갱신(다음 트랙 = HR 확장).
3. 이후 R0→R1 착수는 기존 관례대로 사용자 지시 단위로 진행.

## 검증 방법

- 계획서 자체: 사용자 검토(특히 R0 동결 항목의 규칙 6건).
- 이후 각 STAGE: 인용된 게이트(R1 비트 동일성, R2 B1~B9, R3 페어드 CRN assert)를 작성 세션과 독립된 재실행으로 판정 — `plan_h0_verification.md` 관례 동일.
