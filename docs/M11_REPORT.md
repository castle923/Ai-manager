# M11 설계 정렬·원형 계약 구현 보고

기준 소스: `00703812babb04a07efae8e21c5d067e47419121`. 기존 v0.10.0 tag/패키지 소스 `5a336cd0522fadda68f179ed4b8c5b0d4059aa5f`와 별개인 source-only 후속 작업이다. 기존 M0–M10 실검증·한계·Release 이력을 변경하지 않는다.

## 구현 범위

새로운 독립 module 3개로 6개 pinned manifest catalogue, immutable canonical snapshot/plan, 다축 상태·전이, dry_run/validate_plan 전용 approval/ledger 대조, 미래 입력 recipe/DAG 선언과 stdlib CLI를 구현했다. 기존 server/API/UI/worker/runtime 파일은 수정하지 않았다. 상세 필드와 제한은 [M11_CONTRACT](M11_CONTRACT.md), 전체 후속 목표는 [AUTO_VALIDATION_PLAN](AUTO_VALIDATION_PLAN.md)을 따른다.

catalogue는 기존 공개 6개 manifest의 bytes SHA·ID/revision·필수 파일 수·bytes·license를 일치시킨다. fingerprint는 `79bdc5cdf2c1f975ab352c5216a7f841bafc3b2c8ff794d29b4275e1ae73ca50`다. 이것은 실제 모델 폴더·파일의 일치를 새로 검증한 결과가 아니다.

원형의 결과 판정 출력은 `execution_authority=false`, `model_test_performed=false`를 포함한다. `example`은 검사 입력 schema에 맞는 합성 선언 bundle만 출력한다. 승인 actor는 인증된 사용자, canonical hash는 서명을 뜻하지 않는다. caller-supplied clock/현재 snapshot/ledger를 대조하는 순수 검사다. 동일 bundle의 반복 검사도 수용되며 실제 승인 소비·durable ledger·replay 차단·실자산 재관측·동시성 락은 M12/M15에 남는다.

계획은 미래 output/fresh input hash를 `null`로 고정하고, 같은 batch TTS output 참조와 24k→16k mono PCM16 변환 recipe·30초 이내 상한을 연결한다. 실제 생성·변환·receipt·SHA는 M13에서 별도 수집·대조해야 한다. 현재 예제의 가상 상태나 digest 선언을 과거/현재 추론 성공 증거로 사용하지 않는다.

## 검증과 한계

새 CPU 계약 tests 26개 중 25개 PASS, 실제 symlink 생성 1개는 해당 Windows 프로세스 권한으로 생성할 수 없어 skip했다. reparse 검출 분기는 별도 모의 stat fixture로 확인했다. 첫 전체 회귀는 기존 280개와 당시 신규 19개를 포함한 299개 중 292 PASS/7 skip이다. CLI/reparse/반복 선언·snapshot 독립성·안전 I/O 반례를 추가한 **최종 전체 회귀는 306개 중 299 PASS/7 skip**이다. 기존 6 skip과 신규 실제 symlink 1 skip을 구분하며 권한을 바꾸어 우회하지 않았다. frontend·실모델·GPU 검증은 수행하지 않았다.

반례는 duplicate JSON key·NaN/Infinity/float·깊이/bytes/nodes 초과·bool-as-int·unknown fields·schema/revision/catalog drift·교차 artifact ID alias·미래 fake SHA·순방향/순환 DAG·다른 batch 계보·잘못된 변환·만료 경계·snapshot/plan stale·미래 실행 권한·unknown/rollback/초과 ledger·경로 escape/reparse·terminal 수정·실증거로 위장한 상태를 포함한다. CLI는 새 임시 JSON 문서에서 실제 validate 성공과 안전한 거부 출력을 확인했다.

기존 앱/home/인증/DB/모델/runtime, 브라우저/OS 보안, GPU·클라우드·Drive에는 접근·변경하지 않았다. 모델 검색·설치·다운로드·loading·추론·실산출물 품질 평가는 수행하지 않았다. 이 범위는 프로그램 전체 자동 검수 workflow 완료 또는 6프로필 실제 추론 PASS가 아니다.

## M11 이후 참고 공수 재산정

아래는 실제 source surface와 계약 원형에 근거한 **사람 8시간 기준 참고 개발 인일**이다. 에이전트 turn·AI 실행 시간·달력 납기를 뜻하지 않는다. 구현한 인일을 역산하거나 실제 소진 시간을 측정한 값도 아니다. 원형이 줄인 것은 schema/계약 불확실성 일부이며 실 scanner·dispatcher·모델 시험·UI 완료분은 없다.

| 남은 개발 작업 묶음 | 참고 인일 |
|---|---:|
| 프로필/schema의 실증거 연결·계약 후속 | 0.5–1 |
| 지정 local/Drive discovery·identity | 2–4 |
| 실제 preflight/snapshot/승인 저장/TOCTOU | 1.5–2.5 |
| 새 fixtures·변환·actual receipt | 3–5 |
| 순차 dispatcher/slot/job/취소 | 3–5 |
| 실 output 검증/집계/export | 1.5–2.5 |
| 계획/승인/진행/결과 UI | 3–4 |
| durable resume/replay/restart/문서·패키징 | 1–2 |
| 개발 소계 | 15.5–26 (대략 16–26) |

통합·실환경 검증 7–12, 후속 독립 검증 3–5인일을 더하면 **대략 26–43인일**이다. 최초 28–46인일 추정은 역사로 보존한다. 6개 고정 프로필·기존 worker 재사용·프로필당 최소 표준 case 1개·Windows local 범위라는 가정과 품질 우열 자동점수 미포함을 유지한다. OAuth 사용자 참여·다운로드/설치/GPU 확보·현재 image/LLM 운영 자원 차단 대기는 제외한다. 병렬개발 충돌·AI 배율을 가정하지 않았다. M12 발견/실snapshot/락, M13 실환경 반례 확인 때 다시 산정한다.

## 다음 gate

M12는 실제 read-only intake·metadata 식별·server-owned snapshot/clock/approval/ledger·bounded dispatcher·중복 job 잠금·현자산 stale 차단을 구현하고 독립 negative tests로 확인해야 한다. M13에서 fresh 시험 생성/변환·worker/receipt를 연결한다. 설치·네트워크 준비는 승인된 plan opt-in 경계를 유지하며 Drive 쓰기·삭제·유료 클라우드 프로비저닝은 이 M11 승인에 포함하지 않는다.
