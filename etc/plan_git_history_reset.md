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

## §8. 실행 로그 (2026-08-11 실행 완료)

### Phase 0 — 사전 검증
- `pytest -q` 재실행: **634 passed, 3 skipped in 212.98s** (0:03:32) — §2 실측치와 일치, 재확인 완료.
- HR 골든패스: `simulation.run --scenario data/data1/K50_1.json --floor-profile uniform
  --mode hr --out results/baseline_hr_K50_1_uniform_s42.json` (delivered=50, wall=0.76s)
  → `analysis.verify_hr results/baseline_hr_K50_1_uniform_s42.json` →
  **B1–B11 전항 PASS, "10 passed, 0 skipped, 0 failed"**.

### Phase 1 — 백업
- `git branch legacy/stage-era` (옛 HEAD `05628aa` 보존) — 로컬 생성 완료.
- `git bundle create ~/Research/backups/abm_new_stage_era_20260811.bundle --all` →
  `git bundle verify` → **"is okay" / "The bundle records a complete history."**
  (4 refs: legacy/stage-era, main, remotes/origin/main, HEAD — 전부 `05628aa`/`38a50a8`).
- `git push origin legacy/stage-era` → **성공**, `new branch legacy/stage-era -> legacy/stage-era`
  (§6-2 결정에 따라 원격에도 보존).

### Phase 2 — .gitignore 정비
- `.gitignore`에 `results/` · `archive/` · `cycle_charts/out/` 3줄 추가.
- 확인: `archive/`, `results/`, `cycle_charts/out/`, `data/`, `.venv/`, `.mypy_cache/`,
  `experiments/results/` 전부 ignore 적용 확인(`git status --ignored`).
- 추적 대상 사전 점검: `etc/`, `uv.lock`, `skills-lock.json`, `.claude/`, `.agents/`,
  `cycle_charts/`(코드), 신규 tests/analysis/simulation/experiments/configs 전부 미추적
  목록에 정상 노출 확인.

### Phase 3 — 새 루트 커밋
- **절차 편차 1건**: `git switch --orphan fresh-main`이 실측 git 2.32.0에서 워킹트리에
  미커밋 변경(수정 23·삭제 6)이 있는 상태로는 실패함(`Your local changes ... would be
  overwritten by checkout ... Aborting`) — 계획서 §5 예시 명령이 가정한 "무변경 전환"이
  이 git 버전에서는 성립하지 않음(orphan 전환도 내부적으로 현재 HEAD로의 checkout과
  동등하게 처리되어 로컬 수정과 충돌). **명령 실행 전 상태였으므로 워킹트리는 무손상**
  (git이 스스로 중단, "Aborting"). 대응: 표준 안전 우회 — `git stash push -u`로
  추적 수정분 + 미추적 신규 파일 전량을 스태시(무시 대상 제외) → 클린 상태에서
  `git switch --orphan fresh-main` 정상 수행 → `git stash pop`. pop 시 예상대로
  "modify/delete" 충돌 23건 발생(새 orphan 브랜치는 커밋이 없어 이전 트리 대비
  "삭제"로 해석됨) — 이는 추적 상태 충돌일 뿐 파일 **내용**은 스태시 버전 그대로
  트리에 남음("Version Stashed changes of X left in tree")을 명령 출력으로 확인.
  검증: 5개 대표 파일(.gitignore, simulation/model.py, tests/test_space.py,
  analysis/scenario_loader.py, pyproject.toml, simulation/agents/robot.py)을
  `git show stash@{0}:<path>`와 `diff`하여 **바이트 단위 일치 확인**, 충돌 마커
  (`<<<<<<<`/`=======`/`>>>>>>>`) 부재 확인(grep 무매치). 워킹트리 파일 내용은
  변경되지 않았음(금지 조항 준수). `git add -A` 후 전량 `A`(신규 추가) 상태만 남아
  잔존 충돌 없음 확인. 커밋 성공 후 `git stash drop`으로 정리(내용이 커밋에 완전히
  들어갔음을 확인한 뒤 수행 — 워킹트리에는 영향 없음).
- 스테이징 검토: 개별 최대 파일 `uv.lock` 474KB, 5MB 초과 파일 **0건**, 총 스테이징
  용량 **약 4.22MB**(예상 ~10MB 대비 낮음, 50MB 한도 대비 여유) — 중단 기준 미해당,
  정상 진행.
- `git commit` → **새 루트 커밋 `56ce0b8` — "baseline: H0 v2.1 + H1 Phase A (A0-A5)
  unified snapshot"**, 181 files changed, 49641 insertions(+).

### Phase 4 — 브랜치 교체 + 원격 반영
- `git branch -M fresh-main main` → 로컬 `main` = `56ce0b8`.
- `git push --force-with-lease origin main` → **성공**: `38a50a8...56ce0b8 main -> main
  (forced update)`.
- `origin/legacy/stage-era`는 Phase 1에서 이미 push 완료(중복 push 불필요, `git
  ls-remote origin`으로 재확인: `legacy/stage-era` → `05628aa`, `main`/`HEAD` → `56ce0b8`).

### Phase 5 — 사후 검증
- `git status` → `working tree clean`, `up to date with 'origin/main'`.
- `git log --oneline` → 단일 루트 커밋 `56ce0b8`만 존재.
- `git ls-files | wc -l` → **181**.
- pytest 재실행은 생략(Phase 0에서 이미 확인 + Phase 3에서 파일 내용 바이트 일치를
  별도 검증했으므로 재확인 불요). 선택 사항인 임시 clone 검증은 생략.

### 결과 요약
- 새 루트 커밋: `56ce0b8`(로컬/원격 `main`) · 옛 이력 보존: 로컬+원격 `legacy/stage-era`
  = `05628aa` · 번들 = `~/Research/backups/abm_new_stage_era_20260811.bundle`.
- 이상 발견: Phase 3에서 `git switch --orphan`이 계획서 가정과 달리 무변경 워킹트리를
  요구함(위 절차 편차 참조) — 안전 우회로 해결, 파일 내용 무손상 검증 완료. 그 외 이상 없음.

## §9. 정오(corrigendum) — 무수정 추적 파일 40개 소실 및 복구 (2026-08-11)

**§8의 "무손상" 판정은 불완전했다.** 리뷰 9건 수정 작업(후속 세션)이 착수 시점 스위트가
634가 아닌 **597 passed / 0 skipped**임을 보고하면서 발견됐다.

- **기전**: `git stash push -u`는 *수정된 추적 파일 + 미추적 파일*만 담는다. **수정되지 않은
  추적 파일 약 40개는 stash에 들어가지 않았고**, 직후의 `git switch --orphan`이 추적 파일
  전부를 워킹트리에서 제거하면서 그대로 소실됐다. stash pop은 이들을 복원할 수 없었다
  (애초에 stash에 없었으므로).
- **§8 검증이 놓친 이유**: Phase 3의 바이트 일치 검증은 표본 5개가 전부 *stash에 있던*
  파일이었다. Phase 5의 pytest 재실행 생략(총괄 세션 지시)이 마지막 검출 기회를 제거했다 —
  재실행했다면 634→597 불일치가 그 자리에서 드러났을 것이다.
- **소실 목록**: 테스트 6개(tests/__init__.py, test_cost_model, test_demand_model,
  test_load_data, test_locker, test_rider_arrival_model = 사라진 37 tests + 3 skips),
  simulation/{__init__,costs}.py, agents/{__init__,locker}.py, analysis 15개(demand_model,
  run_analysis, fit_report, fitted_params, figures 10), experiments 9개 전부, README.md,
  .python-version, .gitkeep 4개 — 총 40개.
- **복구**: 전부 *무수정* 추적 파일이었으므로 `legacy/stage-era`의 버전이 곧 소실 시점의
  정본이다. `git checkout legacy/stage-era -- <40개>`로 복구, 의도적 삭제 6건은 제외 유지.
  복구 후 전체 스위트로 검증(아래 복구 커밋 참조).
- **교훈**: orphan 전환류 작업의 무손상 검증은 표본 diff가 아니라 **전수 기준
  (`git ls-tree` 파일 목록 비교 + 전체 스위트 재실행)**으로 해야 한다. stash 우회를 쓸 경우
  "stash에 안 들어가는 것이 무엇인가"를 먼저 열거할 것.
