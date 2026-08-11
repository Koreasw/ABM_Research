# 다음 세션 시작점 — Phase A (2026-08-11 저녁 기준)

> **이 문서의 지위: 정본이 아니다.** 세션을 다시 열었을 때 **첫 5분에 읽을 것**만 담은
> 포인터 문서다. 모든 상세의 정본은 §5의 지도가 가리키는 곳에 있고, 충돌하면
> **정본이 이긴다.** 작업이 진행되면 이 문서는 갱신하거나 지운다.

---

## §1. 지금 상태 (30초)

- **Phase A: A0~A6 완료.** 스위트 **646 passed / 3 skipped**. **A7-a 설계 완료(승인 대기)·A7-b 남음.**
- 오늘(2026-08-11) 있었던 큰 일 4가지:
  1. **git 이력 초기화** — STAGE 시절 22커밋을 `legacy/stage-era`(로컬·원격·번들 3중 보존)로
     격리하고, 새 루트 커밋 `56ce0b8`(H0 v2.1 + H1 A0~A5 통합 스냅샷)로 재출발.
     정본 문서(etc/)가 **처음으로 이력에 들어갔다**. 도중 무수정 추적 파일 40개 소실
     사고가 있었고 전량 복구·검증됨(계획서 §9 정오 참조).
  2. **Fable 1순위 리뷰 + 수정 완결** — `kpi.py`+`robot.py` 독립 리뷰(Fable/max)가
     발견 9건(F1~F9)을 냈고, 전건 수정 + 회귀 10건 추가. **F2로 카별 EV 대기 수치가
     바뀌었다**(EV3 29.46→25.37 s — 로봇 혼입 제거, 커밋 메시지에 명세).
  3. **A6 단조성 완료** — ①⑤ PASS, ② 1지표 1구간 반전(ped_decay 침투 차이로 규명,
     게이트 정의 유지), ③ 계획서 경고대로 FAIL(버그 아님 — Phase D 이월), ④ TIE.
     극한 2케이스 모두 verify_hr 10/10.
  4. **A7-a 게이트 보강 설계 완료(Fable)** — 신설 게이트 **B12~B18** 명세.
     `etc/scie_phase/design_a7a_gates.md`가 정본. **사용자 결정 4건 대기**(§3).

### 재개 직후 확인 명령

```bash
cd /home/sw/Research/abm_new
git log --oneline | head -3          # c56ac1a(A6) 이후여야 함, working tree clean
.venv/bin/python -m pytest -q        # 646 passed / 3 skipped 이어야 함
.venv/bin/python -m simulation.run --scenario data/data1/K50_1.json \
    --floor-profile uniform --mode hr --out results/check_hr_K50_1_s42.json
.venv/bin/python -m analysis.verify_hr results/check_hr_K50_1_s42.json
                                     # 10 passed, 0 skipped, 0 failed
```

---

## §2. 남은 작업 — 실행 순서

### ▶ A7-a 게이트 보강 **구현** (오퍼스 / high — 설계 결정 4건 ✅ 확정 2026-08-11)

정본 = `etc/scie_phase/design_a7a_gates.md`(결정 반영판). 신설 B12~B18(**B15-3 제외** —
이연, `plan_b15_3_h1_upstream_replay.md` 참조):
B12 주문 결과 정합·하한 🔴 · B13 워밍업 적정성(H1판 A13, 임계 0.35 재사용) ·
B14 카별 보존+선언 정합 · B15-1/2 상류 체인 · B16 floor 범위 ·
B17 종료 규약 통일(캡 종료 런 = FAIL, **kpi 정의 변경 없음**) · B18 deny 상한(mean+4σ).
각 게이트는 조작-음성 회귀 테스트 필수(~13건).

### ▶ A7-b 전수 실행 (소넷 / medium) — **B17-2 확정·구현 후에만**

K300_4를 43,200 s cap으로 1 run → 드레인 실측 → ×1.3으로 `max_overrun_sec_robot` 확정
(현 32,400은 추정치; A6 극한 2케이스는 기본 cap으로 완주했다). 그 뒤 28×3 = **84 run**
전수 B1~B18 PASS. ⚠️ B17-2(ops 창 경계)가 나중에 바뀌면 84 run을 재실행하게 된다 —
순서를 지킬 것.

### 이후

`A → B(H2) → D1 → C(H3) → D2 → E → F` (결정 #30). Phase A 종료 조건은
**`checklist_visual_h1.md` 15항목 육안 서명**(A7 완료 후).

---

## §3. 사용자 액션 대기 — 1건

| # | 항목 | 시한 |
|---|---|---|
| 1 | **`T_building_order` 논문 인용본 선택** — ⓐ`t_building_order_sec`(입장→인도) vs ⓑ`t_order_post_handoff_sec`(인계→인도). 코드는 둘 다 산출. ⚠️ F6 수정으로 "H0 t_lobby와 동일 구간" 주석이 **오류였음이 확정**됐다(55~91 s 차이) — 선택 시 참고 | Phase F 집필 전 |

(해소됨: A7-a 설계 결정 4건 ✅ 2026-08-11 확정 — B17-2 종료 규약 통일·B13-2 0.35
재사용·B18 mean+4σ·B15-3 이연. `design_a7a_gates.md` §사용자 결정 참조)

---

## §4. Fable 투입 잔여 (결정 #22 개정)

1·2순위 완료(kpi/robot 리뷰 ✅ · A7-a 설계 ✅). **잔여 = 3순위**: A5-c에서 중단된
앵글 2건(Efficiency·Conventions) — 이미 시작한 리뷰의 저렴한 완결. 급하지 않음.

---

## §5. 정본 지도 — 상세는 전부 여기

| 무엇을 알고 싶은가 | 정본 |
|---|---|
| Phase A 전체 상태·규약 8가지·남은 작업 | `etc/HANDOFF_phase_a.md` |
| 각 Step에서 계획이 왜 틀렸나·무엇을 발견했나 | `etc/scie_phase/phase_A_implementation_log.md` (§A0~§A6) |
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
