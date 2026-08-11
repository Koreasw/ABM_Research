# SCIE 논문 트랙 — Phase별 상세 실행 계획서 색인

> 상위 정본: `etc/research_plan_scie.md` (연구 전체 설계·확정 결정·일정).
> 본 폴더의 각 파일은 그 §6 로드맵의 Phase 하나를 **처음 보는 사람도 실행할 수 있는
> 수준으로 풀어 쓴** 상세 계획서다. 용어가 낯설면 먼저 `research_plan_scie.md` §0
> "용어와 약어 해설"을 읽을 것 — 각 Phase 문서에도 해당 Phase의 필수 용어만 요약해 두었다.

## 실행 순서와 상태

| 순서 | 파일 | 내용 | 기간(안) | 상태 |
|---|---|---|---|---|
| 1 | `phase_A_robot_h1.md` | 로봇 에이전트 + H1 동기 핸드오프 구현·검증 (B-게이트) | 주 1~3 | ⬜ |
| 2 | `phase_B_h2_queue.md` | H2 알림 기반 핸드오프(관리자 W_est 알림·비용 balk·무상한 큐) + C-게이트 + G/G/c 대조(H1 1차) | 주 4~6 | ⬜ |
| 3 | `phase_C_h3_locker.md` | H3 자동 도킹 락커 + D-게이트 + 락커 sizing 스윕 | 주 6~8 | ⬜ |
| 4 | `phase_D_experiments_economics.md` | 4-모드 통합 실험(CRN 페어드 **3,360 run**) + NPV·break-even 경제층 | 주 9~11 | ⬜ |
| 5 | `phase_E_sensitivity_pareto.md` | Morris→Sobol 민감도 + 3-stakeholder Pareto + 논문 figure 전량 | 주 11~13 | ⬜ |
| 6 | `phase_F_writing_submission.md` | 검증 리포트·논문 집필·수치 전수 대조·SMPT 투고 | 주 13~18 (+버퍼 2주) | ⬜ |

> **변경 기록 (2026-07-23)**: 사용자 시나리오 재정의로 Phase B가 renege형(큐 용량 8 +
> τ_patience 포기) → **알림 balk형**(관리자 W_est 알림 + 유형별 단가 비용 임계 C_th)으로
> 전면 개정되었다(`research_plan_scie.md` §1 결정 #11~#15, 재론 금지). phase_A(§5)·
> C·D·E·F 문서도 연동 수정. Phase A의 실행 내용 자체는 무변경.
>
> **변경 기록 (2026-08-03)**: Phase A 착수 전 **H0 수요-거동 진단 트랙(S0~S3)** 을
> 수행하고(38 시나리오 × 3 seed 전수), 그 발견을 각 Phase 문서에 반영했다. 설계
> 결정이나 Step 구성의 변경은 없고, **기존 계획을 실행할 때 참조할 사전 기준선·
> 주의점의 추가**다. 반영 위치: phase_A §0(진단 기준선 표)·§2(A1 거부 테스트·A5 deny
> 상한·A6 저부하 경고·A7 관측 3항)·§4(리스크 4·5) / phase_B §2 B5(Ca² 실측 사용
> 규약·민감도 병기)·§4(리스크 4·5) / phase_C §2 C7(버스트 시나리오 선정)·§4(리스크 4)
> / phase_D §0(설계 제약 3건)·§2 D3(계단 손실 사전 정량화·층별 페어드 분석)·D7(K 구간
> 서사)·§4(리스크 1 상향) / phase_E §4(시나리오 축소의 대가).
> 정본: **`archive/h0_v1/analysis_outputs/h0_insights/note_h0_demand_insights.md`**
> (발견 + 체크리스트 11항), 수치는 같은 폴더 `tables/*.csv`. *2026-08-04 경로 정정 —
> 구 표기 `analysis/h0_insights/`는 R0 아카이브 때 이동했다(읽기 전용).*
> **진단 트랙은 3 seed — 논문 인용 수치의
> 정본은 어디까지나 Phase D(30 seed + CRN)이며, 위 반영분의 수치는 전부 참고치다.**
>
> ## 🔴 변경 기록 (2026-08-06) — **H0 v2.1(R8) 창·종료 재정의 완료**
>
> 시뮬레이션의 **초기 상태(워밍업)와 완료 조건**을 데이터 근거 위에 다시 세웠다.
> 리포 **440 passed / 3 skipped**(R8 종료 시점), V21 재검증 게이트 15건 = **PASS 14 /
> CAUTION 1 / PENDING 0**(육안 재서명 2026-08-07 완료). 새 확정 결정 **#23~#25**는 `research_plan_scie.md`
> §1에 등재됐다. 규약 요약 `etc/HANDOFF_v2.md` §3.8 · 재검증
> `etc/verification_report_h0v2.md` **§8** · 계획서 `etc/plan_h0v21_window.md`.
>
> **전 Phase가 반드시 들고 갈 것 4가지**:
> 1. **완료 정의가 바뀌었다.** H0 = 전 주문 배달 + **라이더 전원 건물 밖**(배경
>    보행자 배출을 더는 안 기다린다). **H1** = + 로봇 전원 1F 로비 IDLE 복귀 /
>    **H2** = **분기 불필요**(AND가 자동 처리) / **H3** = `delivered` 정의 **미결**
>    (사물함 투입 권장 — `phase_C_h3_locker.md` §1).
> 2. **게이트 A1~A12 → A1~A14.** 신설 A13(warm-up adequacy)·A14(termination reason),
>    기존 A1·A6·A8·A11은 **정책 분기**를 갖는다. B/C/D-게이트는 이 구조를 승계할 것.
> 3. **주 지표 = `utilization_delivery`.** 전 구간 `utilization`은 워밍업 머리를
>    분모에 넣어 4.6~7.5 %p 낮다(진단용으로 강등). 그리고 **시간가동률은 적재율이
>    아니다** — 재차 인원 4대 합 2.9~4.8명 / 정원 60석.
> 4. **"완료"가 아니라 "보존"을 단언하라.** 종료 시점에 보행자가 EV에 탄 채로 끝날
>    수 있으므로 `boardings == alights`는 정상 run을 FAIL시킨다. 옳은 형태는
>    `boardings − alights == 종료 시점 탑승 인원`이다.
>
> ⚠️ **v2에서 측정한 창 정규화 KPI(가동률·wall_span 계열)는 오라클에서 탈락한다.**
> 주문 단위 KPI(T_e2e·T_lobby·W_EV)는 30시드 CI에서 **구·신 15/15 겹침**으로 불변이
> 확인됐으므로 그대로 유효하다.
>
> ## 🔴 변경 기록 (2026-08-04) — **H0 v2 완료. 진단 기준선의 지위가 바뀌었다**
>
> **H0 v2 개정(R0~R7)·검증(W1~W8)·육안 서명이 전부 끝났다** — 게이트 13건 =
> **PASS 12 / CAUTION 1 / PENDING 0**, 리포 **437 passed / 3 skipped**(당시 값 — 현재 440).
> 정본: `etc/verification_report_h0v2.md`, 인계: `etc/HANDOFF_v2.md`.
> 새 확정 결정 **#16~#22**는 `research_plan_scie.md` §1에 등재됐다.
>
> **이것이 위 2026-08-03 진단 반영분에 미치는 영향**:
> 🚫 **위 진단 트랙(38 시나리오 × 3 seed)은 EV 2대 · 층당 800 ㎡ · 복도 27 m ·
> 지하 없음 · 상주 800명 · 보행자 6.0/분 빌딩에서 측정됐다.** v2가 그 조건을 전부
> 바꿨으므로 **각 Phase 문서에 심어 둔 진단 절대값은 테스트 오라클로 쓸 수 없다.**
> 남겨 둔 이유는 **"어떤 현상을 관찰해야 하는가"라는 정성 예측이 여전히 유효**하기
> 때문이며, 각 문서에 "v2 재판정" 표기를 달아 두었다. 정량 기준선이 필요하면
> 해당 Phase의 배터리에서 v2 실측으로 재산출한다.
>
> **전 Phase 공통으로 바뀐 것**: 코퍼스 39/38 → **28개**(K500·K750·K1000 보류) ·
> 배터리 38×3 → **28×3 = 84 run** · 본문 스윕 3,960 → **3,360 run** ·
> 공용 EV = **EV3·EV4**(EV1·EV2는 사람 전용) · A-게이트 A1~A9 → **A1~A12**(R8에서
> **A1~A14**) · 스위트 368 → **437**(R8 후 **440**) · **Fable 전면 미사용**(구 배정은 오퍼스 `max`).
>
> 반영 위치: README(본 표·관례 7) / phase_A(상단 배너·§0 표·§2 A1·A5·A6·A7·§3·§4) /
> phase_B(§1·§2 B5·B7·§3) / phase_C(§1·§2 C0-6·C7·§4) / phase_D(§0·§1·§2 D1·D2·D3·D7·
> §3 배정표·§4) / phase_E(§2 E5·§3·§4) / phase_F(§2) / plan_hr_extension(전면) /
> proposal_hr_extension(이력 배너).

## 공통 실행 관례 (전 Phase 적용, 레포 확립 관례)

1. **서브에이전트 위임**: 각 Step은 배정된 모델(오퍼스/소넷)·effort로 서브에이전트에 위임한다. 현재 세션 모델과 배정이 일치하면 세션이 직접 수행해도 된다.
2. **세션 독립 재검증**: 서브에이전트가 "완료"를 보고해도 그대로 믿지 않는다. 세션이 전체 pytest, 비트 동일성 게이트, 산출물 스팟 재현(CSV 수치 재계산 등)을 독립적으로 다시 실행해 확인한 뒤에만 완료 처리한다.
3. **단계 경계 게이트**: Step 경계마다 전체 테스트 스위트 green을 확인한다. 다음 Phase는 이전 Phase의 완료 기준(각 문서 §1)을 전부 충족한 뒤에만 착수한다.
4. **인플레이스 진행 로그**: 진행 상황은 각 Phase 문서 말미의 진행 로그 표에 기록한다(별도 파일 금지). Phase 완료 시 `research_plan_scie.md` §12.2와 본 README의 상태 열도 갱신.
5. **Escalation**: 같은 테스트가 2회 실패하면 모델 또는 effort를 1단계 상향한다(effort 사다리 `low<medium<high<max`). 설계 충돌·스펙 모호는 **세션(오퍼스)**이 직접 개입한다. — *2026-08-03 3차 정책: Fable 크레딧 소진으로 전 Phase에서 Fable 배정을 오퍼스로 이관하고, 구 Fable 담당 구간은 effort `max`를 쓴다.*
6. **코드가 진실**: 문서의 수치는 스크립트 자동 생성만 허용(수기 표 금지). 가능하면 파스-락 테스트로 문서↔코드 일치를 잠근다.
7. **절단 금지 3종**: 비트 동일성 게이트 · 모드별 골든패스 · 게이트 배터리(**28×3 = 84 run**) — 예산이 부족해도 생략할 수 없다(논문 방법론 기여의 본체).

## 관련 문서

- `etc/research_plan_scie.md` — 상위 정본(연구 설계·**확정 결정 #1~#22**·용어 해설)
- **`etc/verification_report_h0v2.md`** — **H0 검증 결과 정본(현행)**. 논문 §7.1 재료
- **`etc/HANDOFF_v2.md`** — 작업 인계 정본(현행). v2 규약 7가지
- `etc/plan_hr_extension.md` — Phase A의 원 실행 계획서(설계 동결 규칙 R0-1~7 정본).
  ⚠️ v1 빌딩 전제로 작성됐다 — 상단 "지위 갱신 2" 배너를 먼저 읽을 것
- `archive/h0_v1/docs/verification_report_h0.md` — **이력 아카이브**(H0 **v1**).
  실측 수치 인용 금지 — 계승 규약의 현행 지위는 `research_plan_scie.md` §1 표가 정본
- `archive/h0_v1/docs/extension_suggestion.md` — SCIE 발전 제안 원문(3대 Contribution의 출처)
- **`analysis/h0_insights/`** — ⚠️ **v1 조건 측정, 오라클 무효**(위 2026-08-04 변경 기록).
  **v1↔v2 대조 정본은 같은 폴더의 `note_v1_v2_comparison.md`**(W7 V2-CMP 신규)이다.
  H0 수요-거동 진단(2026-08-03, S0~S3): 38 시나리오
  전수 KPI·표 6종·figure 6종 + `note_h0_demand_insights.md`(Phase별 사전 고려사항
  체크리스트 11항). 러너 `experiments/h0_descriptive.py`, 분석
  `analysis/h0_baseline_stats.py`, 원본 run `results/h0_stats/runs/`. 진단 트랙(3 seed)
