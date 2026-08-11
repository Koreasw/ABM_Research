# Fable 5 독립 리뷰 — kpi.py + agents/robot.py (2026-08-11)

> **지위**: 리뷰 보고서 정본. Fable 투입 계획(결정 #22 개정, NEXT_SESSION §4) 1순위 수행 결과.
> 리뷰어 = Fable 5 / max effort, 10개 앵글 + 실행 재현 검증. 대상 = `simulation/kpi.py`(790줄),
> `simulation/agents/robot.py`(440줄). 리뷰 시점 스위트 = 634 passed / 3 skipped (전건 통과 —
> 즉 아래 발견은 전부 기존 테스트에 핀 되지 않은 공백에 있다).
>
> **상태: 전건 수정 완료(2026-08-11).** 9건 모두 수정 + 회귀 **10건** 신설
> (F1 1 · F2 3 · F3 2 · F4 1 · F5 1 · F8 2; F6·F7은 서술 수정이라 회귀 불성립,
> F9는 동작 불변 리팩터링이라 기존 스위트 green이 증거).
> 스위트 597 → **607 passed / 0 skipped**, `analysis.verify_hr` **10 passed / 0 failed** 유지
> (재검증 산출물 = `results/verify_after_fix_hr_K50_1_s42.json`).
> 이월 1건 = F3의 `_ops_span` 경계 수축(정의 변경 사안 → **A7 게이트 설계**에서 처리).
> ⚠️ 리뷰 본문의 "634 passed / 3 skipped"는 이 환경에서 재현되지 않는다: 현재 레포는
> 597건을 수집하고 skip은 0이다(`test_plot_baseline.py`의 skipif는 `results/`가 있으면
> 실행된다). 수정 착수 전 기준선도 597 passed였다.

## 수정 작업 지침 (A5-c 전례)

각 발견에 대해 **적발 → 수정 → 회귀 테스트 추가**를 한 세트로 완결한다.
- 수정은 발견이 지적한 결함에 국한한다 — 주변 리팩터링·기능 추가 금지 (F9 예외: 중복 제거 자체가 내용).
- 회귀 테스트는 "이 결함이 재발하면 FAIL"을 보장해야 한다. F7(주석)·F9(중복)는 회귀 테스트가
  성립하지 않으므로 수정 + 기존 스위트 green으로 갈음.
- 완료 기준: 전체 스위트 634+α passed, `analysis.verify_hr` 10/10 유지.
- kpi.py 수정으로 **기존 결과 JSON과 수치가 달라지는 항목(F2 등)은 어떤 필드가 어떻게
  달라지는지 수정 커밋 메시지에 명시**한다 (논문 수치 추적성).

## 발견 목록 (심각도 순)

### F1 — robot.py:329 · 1층 배송이 배정은 되지만 영원히 미배달 [정확성 · 실행 재현 확정]
`assign()`의 가드(`floor < 1`)는 1층 주문을 허용하지만 `_register_call`이 동일층 상행 구간에
direction=-1을 계산해, 로봇이 DROP 상태 없이 TO_HOME으로 귀환한다.
**재현**: floor=1 주문 assign → handoff → to_ev_up → RIDING(direction=-1) → to_home → idle.
`delivered_at_sec`는 None인데 `trips_completed`는 증가, 상행 대기가 `ev_wait_down_sec`/`ev_id_down`에
기록됨(`ev_wait_up_sec`는 None). 전체 런에서는 `_delivery_complete()`가 영원히 불성립 →
max_overrun 안전 캡까지 소진. 현재는 space.py가 사무실을 2층 이상에 두어 잠복 상태.
**수정 방향**: 동일층(=1층) 배송의 FSM 경로를 정의하거나 assign 가드를 `floor < 2`로 올려
명시적으로 거부 — 어느 쪽이든 가드와 FSM이 일치해야 함. | 수정: **a68345b** — 가드를 `floor < 2`로 상향(명시적 거부 + 사유 주석). 1층 배송 요구는 계획서·HANDOFF 어디에도 없고 사무실은 2..n층에만 존재(`space.py` `office_floor_ints`, `floor_demand.py`)하므로 동일층 FSM 경로는 만들지 않았다. 회귀 1건.

### F2 — kpi.py:464 · H1 카별 전창 필드의 로봇 처리 비일관 [정확성 · 실측 확정]
`w_ev_mean_sec`/`w_ev_p95_sec`(432행)는 로봇 탑승을 사람 대기에 평균으로 섞는 반면,
`n_boardings_by_kind`/`w_ev_*_by_kind_sec`는 주석("H1 adds it when robots exist")과 달리 로봇
탑승을 누락한다.
**실측(H1 K50_1 seed 42)**: EV3 n_boardings=221 vs by_kind 합 167(로봇 54건 비가시);
w_ev_mean_sec=29.46s vs 사람만 25.37s — 16% 오염. kpi.py 자신이 `building.w_ev_mean_all_sec`
(533행)에 강제하는 인적(personhood) 규칙과 모순.
**수정 방향**: 카별 필드도 인적 규칙으로 통일(w_ev_*는 사람만) + 로봇은 `robot` kind로 by_kind에
정식 편입. 동결 필드명 유지 여부는 HANDOFF §3.7 규약 확인 후 결정. | 수정: **beba836** — 인적 규칙으로 통일. `w_ev_mean_sec`/`w_ev_p95_sec`는 사람만, 전창 by_kind는 로봇 모드에서만 `robot` 키 추가(H0 스키마 불변). 수치 변화(K50_1 s42): EV3 `w_ev_mean_sec` 29.4615→25.3653 · `w_ev_p95_sec` 69.0→62.8 · EV4 24.3527→23.3596 · 64.85→65.15, 그 외 변경 없음. HANDOFF §2.4 동시 갱신. 회귀 3건.

### F3 — kpi.py:300 · 캡 종료 런에서 진행 중 로봇 트립 전량 소실 [정확성]
캡(`max_overrun_sec_robot`) 종료 시 미완결 leg는 `robot_leg_records`에 없고(_finish_trip만 기록),
`n_requests_unserved_at_end`는 큐 대기만 세며, `_ops_span` 우측 경계가 마지막 완결 이벤트로
수축한다. Phase D 소형 함대 스윕에서 utilization_ops가 가장 바쁜 마지막 구간을 제외하고 계산되어
과대 안정 평가 — 검열(censoring)을 알리는 필드도 없음.
**수정 방향**: 최소 요건 = 캡 종료 시 `n_trips_inflight_at_cap`(가칭) 필드 신설 + 배정-미완결
주문을 unserved 집계에 포함. _ops_span 경계 처리는 정의 변경이므로 HANDOFF §3.7과 정합 확인. | 수정: **de0f645** — `n_trips_inflight_at_end`·`n_requests_queued_at_end` 신설, `n_requests_unserved_at_end` = 큐 + 배정-미완결(정상 종료 런에서는 값 불변 0). 회귀 2건. 🔴 **이월**: `_ops_span` 우측 경계가 마지막 **완결** 이벤트로 수축하는 문제는 창 **정의 변경**이라 손대지 않았다 — **A7 게이트 설계에서 처리**(캡 종료 런의 `utilization_ops` 분모를 어디로 둘지와 함께 결정).

### F4 — kpi.py:789 · summary_to_csv 산출물이 매 런 구조적으로 손상 [정확성 · 재현 확정]
값을 인용/이스케이프 없이 내보내는데 실제 summary에는 항상 쉼표 포함 값이 있다.
**재현**: `Simulation,ped_window_sec,[41400.0, 72000.0]`(4열), `Building,shared_ev_ids,['EV3', 'EV4']`(4열),
windows.* 문자열 행(5열), meta 행 등. **수정 방향**: `csv` 모듈로 교체(수동 join 제거). 회귀 =
산출 CSV를 csv.reader로 파싱해 전 행 3열 확인. | 수정: **9005e50** — `csv.writer`로 교체(수동 join 제거). 회귀 1건(전 행 3열 + 쉼표 값 왕복).

### F5 — kpi.py:612 · drain_span_sec 음수 가능 [정확성]
`max(deliveries) - fixed_window_end`에 하한·미배달 가드가 없어 캡 런에서 음수 가능
(예: drain_span_sec=-212.0, drain_deliveries=0). **수정 방향**: max(0, …) 하한 + 배달 0건 시
None(또는 0) 규약 확정. | 수정: **de0f645** — `max(0.0, …)` 하한. 규약 확정: None=배달 0건 / 0.0=고정창 이후 배달 없음 / >0=실제 길이. 회귀 1건.

### F6 — kpi.py:356 · T_building_order 주석의 H0 t_lobby 동치 주장 오류 [정확성/문서]
주석이 H0의 t_lobby와 동일 구간이라 단언하나, H0는 SERVICE 완료 시점에 delivered_at_sec를 찍고
t_lobby는 출구까지 이어져 라이더 하강·퇴장 보행만큼 다르다(kpi.py 자체 R8-b 노트가 그 꼬리를
55~91초로 실측). **§3 사용자 대기 결정(T_building_order 인용본 ⓐ/ⓑ 선택)에 직접 영향.**
**수정 방향**: 주석을 실제 구간 차이를 명시하는 서술로 교체. 논문 인용 시 주의 문구 포함. | 수정: **1a96792** — 주석을 실제 구간 차이(끝나는 사건이 `delivered_at_sec` vs `exited_at_sec`, 차이는 하강·퇴장 55~91 s)로 교체 + 논문 인용 주의 문구. 회귀 불성립(서술).

### F7 — robot.py:246 · handoff 1틱 지연 docstring이 실제 틱 순서와 반대 [문서]
docstring은 "라이더가 로봇보다 먼저 스텝"이라 설명하나 model.py(733-741행)가 문서화·의존하는
실제 순서는 로봇→라이더다(A4 골든패스: 틱 순서를 뒤집으면 5건 FAIL). **수정 방향**: docstring을
model.py 서술과 일치시킴. | 수정: **1a96792** — docstring을 실제 틱 순서(로봇→라이더)로 정정. 회귀 불성립(서술).

### F8 — kpi.py:736 · _fmt 소수 2자리가 셋째 자리 가동률 대비를 소거 [보고서 품질]
모듈 docstring이 존재 이유로 명시한 K200 0.735 vs K300 0.738 대비가 Markdown/CSV 보고서에서
반올림으로 구분 불능. **수정 방향**: 비율(utilization 등) 필드는 소수 3자리 렌더링. 회귀 =
보고서 문자열에 0.735/0.738이 구분되어 나타나는지 확인. | 수정: **200705e** — 비율 필드(`util`·`bucket_share`·`_ratio`·`_rate`)만 소수 3자리, 나머지는 2자리 유지. 회귀 2건.

### F9 — kpi.py:117 · 창(window) 인덱스 규약이 5곳에 중복 [단순화]
`_ops_span`이 `_delivery_span`의 exit 수집을 재구현하고, summarize가 span→틱 인덱스 블록을
4회(j/d/f/p) 반복. **수정 방향**: 공용 헬퍼로 합성(동작 불변 리팩터링). 회귀 테스트 불요 —
기존 스위트 + verify_hr green이 동작 불변의 증거. | 수정: **66abb01** — `_ops_span`이 `_delivery_span`을 호출하도록, span→틱 인덱스 4중복은 `_span_ticks()` 헬퍼로. 동일 커맨드 산출 JSON 전 필드 비교에서 변경 0건.

## 참고

- 리뷰에서 **반증된 후보 1건**: 로봇 `capa` 미강제 — config 자체 주석("informational, corpus-max")
  으로 의도된 동작임이 확인되어 발견에서 제외.
- Fable 투입 잔여: 2순위 A7-a 게이트 설계, 3순위 A5-c 중단 앵글 2건(Efficiency·Conventions).
