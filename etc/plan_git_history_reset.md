# 계획서 — git 이력 초기화 및 H0·H1 통합 스냅샷 커밋 (2026-08-11)

> **지위**: 실행 전 계획서. 사용자 승인 후 실행한다. §6의 결정 항목이 확정되어야
> Phase 1 이후를 실행할 수 있다. 실행 완료 후 이 문서는 실행 로그를 §8에 덧붙여 보존한다.

---

## §1. 배경과 목적

- 현재 이력 22커밋은 **전부 STAGE 1/2 시절**(마지막 `05628aa`, 미푸시 1건 포함)이며,
  사용자 판단으로 예전 작업이다.
- 그 이후의 실제 작업 — **H0 v2.1 완결 + H1 Phase A(A0~A5, 634 passed)** — 는
  워킹트리에만 존재한다(M 23 / D 6 / 미추적 81).
- 심각한 공백: **정본 문서 전체(`etc/` 24항목 — HANDOFF 3종, research_plan_scie.md,
  구현 로그 `scie_phase/`, 체크리스트)가 지금까지 한 번도 추적된 적이 없다.**
- 목적: 옛 이력을 안전하게 보존·격리한 뒤, **현재의 검증된 상태(634 passed)를 새 루트
  커밋으로 삼는 깨끗한 이력**을 만든다. 이 커밋이 곧 이후 리뷰 9건 수정의 기준점이 된다.

## §2. 현재 상태 실측 (2026-08-11 조사)

| 항목 | 값 |
|---|---|
| 레포 | `/home/sw/Research/abm_new`, 브랜치 `main` 단일 |
| 원격 | `origin = github.com:Koreasw/ABM_Research.git` (21커밋 푸시됨, 로컬 1커밋 미푸시) |
| 워킹트리 | 수정 23 · 삭제 6 · 미추적 81 |
| 삭제 6건 | STAGE 문서 2, 구 configs/baseline.yaml, 구 figure 2, research_framework_handoff.md — 전부 STAGE 산출물의 의도적 제거 |
| 전체 용량 | 2.3G — .venv 1.2G(ignore됨) · data 928M(ignore됨) · **archive 99M(미추적)** · **results 45M(미추적)** · .git 3.6M |
| `etc/` | 948K, 정본 문서 전체, **미추적** |
| 스위트 | 634 passed / 3 skipped (2026-08-11 확인) |

`.gitignore`는 이미 data/·.venv/·experiments/results/·캐시류를 제외하고 있어 골격은 양호.
미비점: `results/`, `archive/`, `cycle_charts/out/`가 ignore에 없다.

## §3. H0 / H1 커밋 분리 검토 — 결론: 파일 수준 분리는 불가능

H0와 H1은 **같은 코드베이스의 모드**다. `model.py`·`kpi.py`·`elevator.py`·`space.py`·
테스트 다수가 두 모드 공용이라, 현재 스냅샷을 "H0 커밋"과 "H1 커밋"으로 파일 단위로
쪼개면 **실존한 적 없는 중간 트리**가 생기고 그 커밋은 테스트 통과를 보장할 수 없다.

| 옵션 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A (권장)** | **단일 루트 커밋** — "H0 v2.1 + H1 Phase A(A0~A5) 통합 스냅샷, 634 passed". H0/H1 구분은 커밋 메시지 본문에 서술 | 커밋 = 검증된 상태 1:1. 거짓 중간 상태 없음. 이후 리뷰 수정 diff가 이 위에 깨끗이 쌓임 | 이력에서 H0/H1이 커밋 단위로 안 나뉨 |
| B | 3커밋 시퀀스 — ①공용 코어+H0 문서·분석 ②H1 로봇 확장(robot.py, verify_hr, HR 테스트, Phase A 문서) ③부속(도구 설정 등) | H0/H1 가독성 | ①·② 시점 트리는 실존한 적 없는 조합 — 중간 커밋 검증 불가. 공용 파일(kpi.py 등)의 귀속이 자의적 |

권장 A. 커밋 메시지 본문에 "H0 = …, H1 = …" 구획을 서술해 가독성을 보충한다.

## §4. 이력 초기화 방법 — orphan 브랜치 + 3중 백업

`.git` 삭제 후 재init은 **복구 불가라 배제**. orphan 브랜치로 새 루트를 만들고
옛 이력은 세 곳에 보존한다:

1. **로컬 브랜치** `legacy/stage-era` (옛 main HEAD를 가리킴 — 미푸시 커밋 포함)
2. **번들 파일** `~/Research/backups/abm_new_stage_era_20260811.bundle` (레포 밖, .git 전체)
3. **원격 브랜치** `origin/legacy/stage-era` (§6-2 승인 시 — 원격에도 보존)

이후 언제든 `git log legacy/stage-era`로 열람, 번들에서 완전 복원 가능.

## §5. 실행 절차

### Phase 0 — 사전 검증 (일부 완료)
- [x] `pytest -q` → 634 passed / 3 skipped (2026-08-11 확인)
- [ ] HR 골든패스 재확인: `python -m simulation.run --scenario data/data1/K50_1.json
  --floor-profile uniform --mode hr --out results/baseline_hr_K50_1_uniform_s42.json`
  → `python -m analysis.verify_hr …` → 10 passed 확인

### Phase 1 — 백업 (파괴적 단계 진입 전 필수)
```bash
mkdir -p ~/Research/backups
git branch legacy/stage-era                                   # 옛 HEAD 보존
git bundle create ~/Research/backups/abm_new_stage_era_20260811.bundle --all
git bundle verify ~/Research/backups/abm_new_stage_era_20260811.bundle
git push origin legacy/stage-era                              # §6-2 승인 시
```

### Phase 2 — .gitignore 정비 + 추적 대상 확정
`.gitignore`에 추가: `results/` · `archive/` · `cycle_charts/out/` (§6-3·4 결정에 따름).
**추적 대상에 새로 포함**: `etc/` 전체(정본 문서 — 필수), `uv.lock`, `skills-lock.json`,
`.claude/`, `.agents/`, `cycle_charts/`(코드만), 미추적 tests/analysis/simulation/
experiments/configs 신규 파일 전부.
**새 이력에서 제외 확정**: 삭제 6건(STAGE 문서 등 — legacy 브랜치에서만 열람).

### Phase 3 — 새 루트 커밋 생성
```bash
git switch --orphan fresh-main
git add -A
git status          # 스테이징 검토: 예상 추적 용량 ~10M, 대용량 유입 없는지 육안 확인
git commit          # §3 결정된 구조로 (A: 1커밋)
```
커밋 메시지(옵션 A 기준):
```
baseline: H0 v2.1 + H1 Phase A (A0-A5) unified snapshot

- H0: v2.1 frozen (visual re-sign 2026-08-07, gates 14 PASS / 1 CAUTION)
- H1: Phase A steps A0-A5 complete (+A5-b, +A5-c gate review)
- Suite: 634 passed / 3 skipped; B-gates 10/10 on 4 demand tiers
- Canonical docs tracked for the first time: etc/ (HANDOFF_phase_a,
  research_plan_scie, scie_phase/ implementation log, checklists)
- Prior STAGE 1/2 history preserved at branch legacy/stage-era
```

### Phase 4 — 브랜치 교체 + 원격 반영
```bash
git branch -M fresh-main main        # 옛 main은 legacy/stage-era로 이미 보존됨
git push --force-with-lease origin main
```

### Phase 5 — 사후 검증
```bash
git status                            # clean 확인
git log --oneline                     # 새 루트 1커밋 확인
.venv/bin/python -m pytest -q         # 634 passed 재확인 (파일 불변이나 안전 확인)
git ls-files | wc -l                  # 추적 파일 수 기록
```
(선택) 임시 폴더에 `git clone`하여 data/ 없이 구조가 온전한지 확인.

### 롤백 절차 (실행 후 되돌리기)
```bash
git branch -f main legacy/stage-era && git switch main
git push --force-with-lease origin main
```
번들이 있으므로 최악의 경우에도 `git clone ~/Research/backups/….bundle`로 완전 복원.

## §6. 사용자 결정 필요 항목

| # | 항목 | 권고 | 대안 |
|---|---|---|---|
| 1 | 커밋 구조 (§3) | **A: 단일 통합 스냅샷** | B: 3커밋 분할 |
| 2 | 옛 이력 원격 보존 | **origin에 `legacy/stage-era` push** (GitHub에서도 열람 가능) | 로컬+번들만 보존, 원격에서는 이력 소멸* |
| 3 | `archive/` 99M (h0_v1·h0_v2_frozen 동결 스냅샷) | **ignore + 현행대로 디스크 보관** (동결본은 불변이므로 이력 추적 이득 없음) | git 추적 (레포 +99M) |
| 4 | `results/` 45M (시뮬 산출물 118개) | **ignore** (전부 run으로 재생성 가능) | 일부 기준 JSON만 추적 |
| 5 | 이 레포를 다른 머신에서 clone한 사본이 있는가? | 없다고 가정 중 — **있다면 알려줄 것** (force-push 후 그 사본은 재클론 필요) | — |

\* 주의: 대안 선택 시에도 GitHub 서버에는 이전 커밋 객체가 당분간 남는다(도달 불가
상태). 완전 삭제가 필요하면 GitHub support 절차가 별도로 필요하다 — 이 레포에 비밀
정보는 없으므로 통상 불필요.

## §7. 리뷰 9건 수정과의 관계

이 계획의 새 루트 커밋이 곧 **"수정 전 기준점 커밋"** 역할을 한다. 실행 순서:

```
이력 초기화 (본 계획) → 루트 커밋 = 634 passed 기준점
    → kpi.py/robot.py 리뷰 9건 수정 + 회귀 테스트 = 그 위의 독립 커밋(들)
    → A6 이후 Step별 커밋
```

즉 본 계획이 승인·실행되면, 앞서 논의한 "수정 전 커밋" 요건은 자동으로 충족된다.

## §8. 실행 로그 (실행 후 기입)

_(비어 있음 — 실행 시 각 Phase의 실제 출력·커밋 해시·추적 파일 수를 기록한다)_
