# 다음 세션 시작점 — Phase A (2026-08-11 저녁 기준)

> **이 문서의 지위: 정본이 아니다.** 세션을 다시 열었을 때 **첫 5분에 읽을 것**만 담은
> 포인터 문서다. 모든 상세의 정본은 §5의 지도가 가리키는 곳에 있고, 충돌하면
> **정본이 이긴다.** 작업이 진행되면 이 문서는 갱신하거나 지운다.

---

## §1. 지금 상태 (30초)

- **Phase A: A0~A7-a 완료.** 게이트 **17개**(B1~B5·B7~B18), 스위트 **666 passed / 3 skipped**.
  **남은 것 = A7-b(전수 실행) 하나** — 사용자 지시로 **아직 착수하지 않았다**(§2).
- 2026-08-11 하루에 진행된 것(상세는 각 정본):
  1. **git 이력 초기화** — STAGE 22커밋을 `legacy/stage-era`(로컬·원격·번들 3중 보존)로
     격리, 새 루트 `56ce0b8`. 무수정 추적 파일 40개 소실 사고 → 전량 복구(계획서 §9 정오).
  2. **Fable 1순위 리뷰 + 수정 완결** — kpi.py+robot.py 발견 9건(F1~F9) 전건 수정 +
     회귀 10건. **F2로 카별 EV 대기 수치 변경**(EV3 29.46→25.37 s, 로봇 혼입 제거).
  3. **A6 단조성 완료** — ①⑤ PASS, ② 1지표 1구간 반전(ped_decay 규명), ③ 경고대로
     FAIL(버그 아님, Phase D 이월), ④ TIE.
  4. **A7-a 설계(Fable) + 구현(오퍼스) 완료** — 신설 B12~B18, 음성 회귀 20건,
     4티어 전건 **17/17 PASS**. 설계 대비 정당한 정정 2건(B14-1 재차 항등식,
     B17-1 3중 부등식 — 구현 로그 §A7-a). B15-3은 사용자 결정으로 **이연**
     (`plan_b15_3_h1_upstream_replay.md`).

### 재개 직후 확인 명령

```bash
cd /home/sw/Research/abm_new
git log --oneline | head -3          # 9332d48(A7-a docs) 이후여야 함, working tree clean
.venv/bin/python -m pytest -q        # 666 passed / 3 skipped 이어야 함
.venv/bin/python -m simulation.run --scenario data/data1/K50_1.json \
    --floor-profile uniform --mode hr --out results/check_hr_K50_1_s42.json
.venv/bin/python -m analysis.verify_hr results/check_hr_K50_1_s42.json
                                     # 17 passed, 0 skipped, 0 failed
```

---

## §2. 남은 작업 — **A7-b부터 재개** (2026-08-11 사용자 지시: A7-a까지만 완료, 이하 미착수)

### ▶ A7-b 전수 실행 (소넷 / medium, ~1일) — 다음 세션의 첫 작업

1. K300_4를 43,200 s cap으로 1 run → 드레인 실측 → **여유 배수를 곱해**
   `max_overrun_sec_robot` 확정(계획 ×1.3, **사용자 지시: 필요하면 넉넉하게 상향** —
   캡 종료는 이제 B11이 "인용 불가"로 FAIL시키므로 캡이 인색하면 정상 런이 죽는다.
   현 32,400은 추정치. 참고: A6 극한 2케이스는 기본 cap으로 완주).
2. 28 시나리오 × 3 floor-profile = **84 run** 전수 → **17 게이트 전건 PASS**.

⚠️ **A7-b 착수 전 반드시 알 것 3가지** (구현 로그 §A7-a-⑤에서 이월):
- **B18 상한은 티어당 시나리오 1개로 캘리브레이션**됐다(K50_1·K100_1·K200_1·K300_4,
  동결 상한 28/66/126/151). 84 run에서 다른 파일이 FAIL하면 **상한을 넓히지 말고
  티어별 전 파일로 재캘리브레이션**할 것(설계서 B18 절의 명시 규칙).
- **B18 봉투**(로봇 5대·보행자 7.5/분·공용 카 2대·K∈{50,100,200,300}) 밖 조건은
  시끄러운 SKIP이 정상이다 — FAIL로 오독 금지.
- HR의 `per_order.delivered_at_sec`는 **전건 None**이 정상(택배원은 인계 시점 퇴장,
  A2 함정 2). 배달 스탬프는 robot leg에만 있다 — 분석 스크립트 작성 시 주의.

### ▶ Phase A 종료 (A7-b 후, 사용자 직접)

**`checklist_visual_h1.md` 15항목 육안 서명.** Solara 앱 기동 명령은 §5 하단.

### 이후 (결정 #30 순서)

`A → B(H2) → D1 → C(H3) → D2 → E → F`. **Phase B 착수 시 함께 처리할 것**:
B15-3 구현(`plan_b15_3_h1_upstream_replay.md` — 트리거 = Phase A 종료, 검증기
공용화 §A5-c-④ #6~8과 한 묶음 권고).

---

## §3. 사용자 액션 대기 — 1건

| # | 항목 | 시한 |
|---|---|---|
| 1 | **`T_building_order` 논문 인용본 선택** — ⓐ`t_building_order_sec`(입장→인도) vs ⓑ`t_order_post_handoff_sec`(인계→인도). 코드는 둘 다 산출. ⚠️ F6 수정으로 "H0 t_lobby와 동일 구간" 주석이 **오류였음이 확정**됐다(55~91 s 차이) — 선택 시 참고 | Phase F 집필 전 |

(해소됨: A7-a 설계 결정 4건 ✅ 2026-08-11 확정 — B17-2 종료 규약 통일·B13-2 0.35
재사용·B18 mean+4σ·B15-3 이연. `design_a7a_gates.md` §사용자 결정 참조)

---

## §4. Fable 투입 잔여 (결정 #22 개정)

1·2순위 완료(kpi/robot 리뷰 ✅ · A7-a 설계 ✅ · B15-3 계획서 ✅). **잔여 = 3순위**:
A5-c에서 중단된 앵글 2건(Efficiency·Conventions) — 이미 시작한 리뷰의 저렴한 완결.
급하지 않음. A7-b는 Fable 투입 대상이 아니다(실행·집계 — 소넷 유지).

---

## §5. 정본 지도 — 상세는 전부 여기

| 무엇을 알고 싶은가 | 정본 |
|---|---|
| Phase A 전체 상태·규약 8가지·남은 작업 | `etc/HANDOFF_phase_a.md` |
| 각 Step에서 계획이 왜 틀렸나·무엇을 발견했나 | `etc/scie_phase/phase_A_implementation_log.md` (§A0~§A7-a) |
| **B15-3 이연 구현 계획**(Phase B 시) | `etc/scie_phase/plan_b15_3_h1_upstream_replay.md` |
| 사용자 확정 결정 #1~#31 | `etc/research_plan_scie.md` §1 |
| **A7-a 신설 게이트 B12~B18 명세** | `etc/scie_phase/design_a7a_gates.md` |
| **F1~F9 리뷰 발견·수정 내역** | `etc/scie_phase/review_fable5_kpi_robot.md` |
| **git 이력 리셋 계획·실행 로그·정오** | `etc/plan_git_history_reset.md` (§8·§9) |
| A6 단조성 실측·원인 분석 | 구현 로그 §A6 + `experiments/vv_monotonicity_hr.py` |
| 측정 창 4개·외부성 지표 | `HANDOFF_phase_a.md` §3.7·§3.8 |
| H0 전체(건물·창·종료 규약) | `etc/HANDOFF_v2.md` |
| H1 육안 체크리스트(A7 후 서명) | `etc/checklist_visual_h1.md` |
| 옛 STAGE 이력 | `legacy/stage-era` 브랜치 · `~/Research/backups/abm_new_stage_era_20260811.bundle` |

**Solara 앱 기동** (반드시 `SOLARA_KERNEL_CULL_TIMEOUT` 포함 — 빼면 고아 커널이 24h 생존):

```bash
SOLARA_KERNEL_CULL_TIMEOUT=30s SOLARA_ASSETS_PROXY=True \
  .venv/bin/solara run simulation/app.py --host 0.0.0.0 --port 8765
```
