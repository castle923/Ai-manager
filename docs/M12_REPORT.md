# M12 실제 후보 관찰·영속 승인·제어 조정기 보고

기준 source는 `58550fee8c30d433d386696992449f534845bf38`이며 source-only 후속 구현이다. 기존 v0.10.0 tag `5a336cd0522fadda68f179ed4b8c5b0d4059aa5f`·Release·ZIP·기존 앱 설치본은 변경하지 않는다. M0–M11 당시 검증과 한계를 아래 결과로 덮어쓰지 않는다.

## 구현과 현재 범위

새 독립 module 6개로 local bounded intake, live read-only Drive provider와 과거 export 구분, fixed metadata/profile 판정, 영속 SQLite plan/approval/one-use ledger, bounded coordinator·고정 CPU probe·CLI를 구현했다. 기존 app/API/UI/task/history/runtime/worker는 수정하지 않았다. [M12 계약·실행 방법](M12_CONTRACT.md)을 따른다.

명시 root→새 관찰→현재 코드/정책/source 결속 plan→명시 local CLI confirm→현재 source 재관찰→승인 트랜잭션 소비→순차 CPU 제어 검증까지 연결했다. 이것은 실제 모델의 파일 full hash·실 revision 확인·환경 자원 검사·표준 입력·추론·출력 품질을 완료한 기능이 아니다. M13 모델 adapter는 not_implemented/deferred로 종료하며 model_test_performed는 항상 false다. 새 검수 화면은 M14 잔여다.

한 plan은 source 하나·후보 최대6개이며 서로 다른 local/Drive scope를 합치는 UI/보고는 후속이다. 같은 home의 협조 lock·기존 execution slot을 사용하며 다른 home/외부 GPU 프로세스의 독점은 보장하지 않는다. local OS 사용자와 파일 권한을 신뢰하는 CLI이며 원격 사용자 인증·서명·변조 불가능한 DB를 제공하지 않는다.

## 새 실관찰과 제어 검증

| 근거 | 실제 확인한 범위 | 해석 제한 |
|---|---|---|
| 지정 local TTS 원본2개 | 비재귀·JSON32KiB/개·총128KiB, 각12,624B 읽기, 새 관찰/재관찰 fingerprint 일치, 0.6B/1.7B supported_metadata | 하위 speech 구성요소 미관찰은 누락 확정이 아니며 required_files_not_observed. weight 본문/전체 hash·실행0 |
| 같은 원본의 논리/물리 alias | 허용된 두 경로의 device/file identity와 candidate ID 일치 | config SHA로 서로 다른 원본을 합친 것이 아님. 새 활성 중복 source plan 차단을 별도 반례로 확인 |
| 새 A/B OAuth·live Drive | 지정 입력으로 새 auth home, 사용자가 두 계정 직접 로그인/동의, 지정 계정·단일 drive.readonly 검사, allowlist4root의 새 bounded 조회/재관찰 | 기존 token/home 복사0. 현재 시점의 제한 범위 관찰이며 전체 Drive 검사 아님 |
| live Drive 관찰 결과 | 깊이1에서 image/Whisper/Llama 지원 metadata 후보를 관찰. 두 root는 정상 범위 조회, 두 root는 작은 config 읽기 한도에서 partial. 재관찰 fingerprint는 같음 | partial2는 current_drive_verified=false·dispatch불가. candidate0도 하위 모델 없음의 증거 아님. checkpoint 형태는 unknown/weak hint |
| 실제 원본→CLI 제어 E2E | 지정0.6B metadata→새 plan→CLI confirm→재관찰/소비→고정 CPU probe1회→status/ledger·replay created=false | 실제 원본은 read-only, probe는 모델과 무관한 CPU 제어 시험. 모델 worker/weight full hash0 |
| 새 synthetic CPU 제어 | 실제 child6개 순차, queued≤3/active1, 정상 종료·취소·timeout·owner 강제 종료 후 interrupted, 모든 소유 probe PID 종료, replay 새 dispatch0 | 생성한 가상 config만 사용. model_test=false, 실제 GPU 취소/추론·모델 시험 아님 |

초기 진단 관찰의 artifact 이름과 후속 수정된 required_files_not_observed 관찰은 비공개에서 시점을 분리해 보존했다. 오래된 관찰을 새 코드 성공 증거로 바꾸지 않았다. metadata config SHA 일치는 기대 recipe/revision 후보 근거이며 같은 config·다른 weight 반례에서도 무결성/정상 실행 PASS로 승격하지 않는다. 실제 TAPIR 원본은 새로 읽지 않았다.

## CPU 반례·회귀 검증

전체 회귀 **340개 중333 PASS/7 skip**을 확인했다. M12 신규34개는 모두 PASS이며 기존 M11 포함 validation 검사60개 중59 PASS/기존 symlink 권한제약1 skip이다. 기존 6 skip을 임의 성공으로 바꾸지 않았다. 새 반례는 bounded 비실행 JSON·duplicate/비유한 수·scope/path/reparse·TOCTOU·같은 이름 다른 내용·모호/약한 identity·source stale·unknown approval의 I/O/예산 부작용0·멀티프로세스 동시 consume1·재오픈 idempotency·시계 rollback/expiry·누적 예산·source alias 중복·terminal 원 reason 보존·미구현 model child0·실제 probe 순차/취소/timeout을 포함한다.

독립 검토에서 manifest hash 확인 후 재읽기 불일치, 무권한 consume의 read 예약, coordinator lock target, 복구 시 terminal 덮어쓰기, metadata network와 model download 예산 혼동을 수정했다. 전체 회귀 중 SQLite 정상 journal 소멸 경쟁을 별도 수리했고, 주 DB가 connect 직전에 사라져도 mode=rw로 빈 DB를 재생성하지 않는 반례를 추가했다. 실제 기존 DB는 삭제하지 않았으며 모두 이번에 만든 임시 store에서 검증했다.

## 남은 작업량 재산정

현재 source surface에 근거한 **사람 8시간 기준 참고 인일**이며 AI turn/경과시간·실제 소진 인일·달력 납기 약속이 아니다. M11 후속 26–43인일과 최초28–46인일은 기준 이력으로 보존한다.

| 잔여 개발 묶음 | 참고 인일 |
|---|---:|
| 실증거 profile 연결 | 0.5–1 |
| 발견/식별 후속 | 0.5–1 |
| 실 env/resource·모델 plan/approval 연결 | 1–2 |
| fresh 시험 생성·변환·actual receipt | 3–5 |
| 실 model dispatcher bridge·job/취소 | 1.5–3 |
| 실 output 검증·보고/export | 1.5–2.5 |
| 검수 UI | 3–4 |
| 부분 재개·배포 | 1–2 |
| 개발 소계 | 12.5–20.5 (대략13–21) |

통합·실환경 검증7–12와 후속 독립 검증3–5를 더해 **약23–38인일**이다. 실제 intake/live API·영속 승인·CPU 조정기만 진척으로 반영했다. fullweight identity·실환경/모델 시험·fresh fixtures/receipt·UI의 완료분을 가정하지 않았다. OAuth 사용자 참여·다운로드/설치·GPU 자원 확보 대기는 별도이며 동시개발 충돌·AI 배율을 가정하지 않는다. M13 실환경 반례와 model bridge 확정 시 다시 산정한다.

## 보존·다음 gate

기존 home·설치 앱·인증·개인 DB·runtime·모델/출력을 수정하지 않았다. 새 인증·SQLite·관찰·CPU 시험 자료는 새 M12 전용 범위에만 저장했다. Drive 쓰기·원본 삭제·모델 다운로드·GPU/cloud·보안 전역 변경은 수행하지 않았다. 공개 자료는 소스·합성 tests·비식별 문서만 선택한다.

M13은 각 승인된 프로필의 full manifest hash·실환경/자원 gate·새 시험/24k→16k 변환·실 worker와 actual receipt를 연결해야 한다. 현재 partial/unknown·환경/자원 미준비를 모델 고장으로 판정하지 않으며 6모델 모두 정상이라 발표하지 않는다. M15 부분 재개는 원 terminal attempt·누적 예산을 보존하고 필요한 새 관찰·승인을 거쳐야 한다. 새 모델/유료 원격 자원·범위 밖 쓰기나 보안 변경이 필요하면 해당 대상·영향을 먼저 알린다.
