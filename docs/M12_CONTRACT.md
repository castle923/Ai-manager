# M12 읽기 전용 발견·영속 승인·제어 조정기

상태: source-only CLI/API 구현. M11의 선언 검사와 별개인 **schema 2 제어 계약**이다. 실제 모델 실행 adapter, fresh 모델 시험 입력·변환·actual output receipt, 새 검수 UI는 구현하지 않는다. M13/M14 이후 범위다. 기존 Windows v0.10.0 ZIP·API·UI·home·worker·runtime은 변경하지 않는다.

## 명시적 입력과 읽기 범위

`validation_intake.observe_local`은 사용자가 지정한 절대 root 하나에서만 BFS 관찰한다. 기본 상한은 entry 4,096·depth 8·JSON 256KiB/개·JSON 본문 총 2MiB·시간 15초다. 더 작은 한도를 선택할 수 있다. 경로 escape/ADS/control 문자, symlink/junction/reparse, 비정규 파일을 거부한다. hidden·cache·output·venv 등은 정책상 제외하며 깊이 밖 폴더를 따라가지 않는다. metadata는 duplicate key·비유한 수·크기·깊이·노드 상한을 검사하는 비실행 JSON으로만 파싱한다. README 명령·pickle·torch.load·custom decoder·모델 Python import는 실행하지 않는다.

관찰에는 명시 root/alias·파일 stat identity·작은 config SHA·관찰 시각·읽은 bytes와 fingerprint를 비공개로 보존한다. 파일 open 전후 identity/size/mtime을 대조하고 승인·소비·dispatch 직전에 같은 범위를 재관찰한다. stat은 full weight hash가 아니며 같은 크기·mtime을 악의적으로 복원한 가중치 변경까지 증명하지 않는다. 실모델 dispatch가 구현되는 M13은 full hash가 필요하다. OS의 동시 경로 변조를 완전히 차단하는 handle sandbox를 구현했다고 주장하지 않는다.

최초 경로 검사에서 허용 root와 중간 부모의 device/file identity를 pin하고, fd를 연 뒤 실제 bytes를 읽기 전에 같은 identity인지 재확인한다. 디렉터리를 다른 regular 폴더로 교체해도 기존 검사 이후 새 root를 무조건 신뢰하지 않는다. 이 반례는 이번에 만든 임시 폴더에서만 검증했다.

`complete`는 **선택한 bounded 관찰에서 오류가 없었음**, `coverage_complete`는 정책 제외/깊이 밖/오류가 없었음을 뜻한다. `complete=true`여도 depth 밖·hidden 등이 있으면 전체 root 검사가 아니다. 관찰되지 않은 필수 파일은 `required_files_not_observed`이며 실제 누락·삭제 확정이 아니다. 부분/실패·권한 거절·한도 종료로 기존 참조나 proof를 지우지 않는다. 모든 관찰은 `absence_means_deleted=false`다.

로컬 root의 volume/device·inode/file identity로 `source_identity`를 만든다. 같은 물리 root의 논리/물리 alias는 같은 후보 ID를 사용하며 같은 store의 활성 중복 source 계획은 거부한다. config SHA가 같다는 이유로 다른 원본을 합치지 않는다. 서로 다른 scope/store·외부 앱의 중복 실행을 전역으로 통제하지 않는다.

## 지원 후보와 실제 무결성의 구분

고정 6프로필 catalogue·manifest hash는 M11을 재사용한다. hash 검증한 동일 manifest raw로 식별표를 만들며 재읽기에도 expected SHA를 확인한다. `config.json`/`model_index.json`의 정확한 작은 config SHA는 `supported_metadata`와 **기대 revision**을 고르는 근거다. 동일 config가 여러 프로필에 맞으면 ambiguous, 명시 revision과 충돌하면 conflicting, 알려지지 않은 model type이면 unsupported, 근거가 부족하면 unknown이다.

`supported_metadata`는 실제 전체 artifact/revision 검증·정상 작동을 뜻하지 않는다. 파일 관찰·크기·읽은 metadata hash와 읽지 않은 weight hash 축을 분리한다. TAPIR처럼 JSON anchor가 없는 checkpoint는 파일명·크기만 맞아도 unknown/weak hint이며 역직렬화하지 않는다. 모델 파일명·폴더 revision hint만으로 지원/무결성 PASS를 만들지 않는다. 실제 TAPIR checkpoint 읽기·실행은 이번 검증에 없다.

## Drive의 두 가지 입력

1. `observe_drive_inventory`는 명시된 기존 프로젝트 export의 **과거 관찰**을 읽는다. live 상태·현재 파일 존재를 보장하지 않고 dispatchable/current verified가 false다. 이 함수를 호출하는 것만으로 OAuth나 Drive API에 접근하지 않는다.
2. `LiveDriveIntake`는 기존 `AuthManager`/`Drive`의 `drive.readonly`·계정 일치·TLS·redirect 거부 경계를 재사용한다. 명시 account A/B와 기존 allowlist의 정확한 root만 받는다. 기본 depth 2·작은 JSON 32KiB/개·config 본문 총 128KiB·page 32·entry 4,096이며 metadata와 작은 config만 읽는다. shortcut·잘못된 parent·중복 ID/cycle·불완전 검색·권한/네트워크/size 한도는 부분/실패로 남긴다. weight body·Drive 쓰기·모델 다운로드는 하지 않는다.

Drive의 같은 parent/name(casefold 충돌 포함)에 다른 file ID가 있으면 열거 순서와 무관하게 ambiguous/partial로 종료하고 dispatch하지 않는다. 같은 ID·같은 metadata가 중복 열거된 것은 별도 duplicate observation으로 분리한다. 이름을 key로 한 dict의 마지막 값으로 지원 후보를 승격하지 않는다.

실제 transport wrapper는 호출당 timeout과 provider당 60초·64 GET·2MiB 수신 상한을 둔다. 기존 Drive retry도 이 전체 상한 안에서만 진행한다. OAuth 교환·검증/갱신은 별도의 기존 인증 경로이며 이 metadata 전송량 측정에 포함되지 않는다. token/URL/body를 로그에 쓰지 않는다. 성공 관찰도 선택한 bounded 범위의 시점별 metadata일 뿐 Drive 전체 검사 결과가 아니다. 재관찰 fingerprint가 같아도 partial 결과는 current verified false다.

새 인증은 명시한 별도 M12 auth home에 지정 client JSON/allowlist 원본으로 준비한다. 기존 토큰/home을 복사하지 않는다. 로그인·동의는 사용자가 직접 수행하고 새로운 OAuth scope를 요구하지 않는다. CLI의 로컬 `--confirm`은 Google OAuth 인증이나 원격 사용자를 인증하는 수단이 아니다.

## 영속 계획·승인·예산

SQLite store는 **명시 init 시 새 빈 target만** 초기화한다. 기존/이동/손상/누락 store를 자동 재초기화하지 않는다. 일반 연결은 URI `mode=rw`로 기존 DB만 열며 check 이후 파일이 사라져도 빈 DB를 만들지 않는다. 정상 SQLite journal 소멸은 허용하지만 sidecar reparse/비정규 파일은 거부한다. store UUID·절대 scope hash를 결속하며 각 연결에서 재확인한다.

immutable plan hash에는 catalogue·현재 제어 코드/정책·source 실제 관찰/stat proof·case 순서·의존성·action·limits가 포함된다. 저장 이후 caller가 clock이나 현재 관찰을 제출하는 M11 방식으로 승격시키지 않는다. 승인/소비는 store가 현재 local clock을 읽고 만료·영속 마지막 시각보다 뒤로 간 clock을 거부한다. 실제 OS 시계 자체나 local 관리자에 대한 보안 인증은 아니다.

승인은 `approve --plan ID --sha256 HASH --confirm`이라는 명시 local CLI 동작이다. 정상 OS 사용자 권한 아래 실행하며 별도 HTTP 승인 endpoint/actor 문자열을 제공하지 않는다. 따라서 새 CSRF/Origin 우회 표면을 추가하지 않으며 기존 웹 보호를 변경하지 않는다. plain SHA와 SQLite는 인증서명·사용자 인증·local 공격자에게 변조 불가능한 저장소가 아니다.

정확한 action은 `validate_control_plan` 또는 별도 opt-in `run_cpu_probe`다. download/install/model run 권한은 0이다. 알 수 없는 approval/다른 scope·action·expired 요청은 source I/O·예산 예약 전에 거부한다. `BEGIN IMMEDIATE`와 UNIQUE 제약으로 승인 소비와 batch 생성은 하나의 FULL synchronous 트랜잭션이다. 같은 승인 재요청은 원 batch를 반환하고 created=false이며 새 dispatch 권한을 주지 않는다.

시간은 plan 저장부터 만료까지 최대 1,800초이며 재개/재오픈으로 reset하지 않는다. config 읽기 예산과 **metadata network bytes/requests**, model download bytes를 구분한다. live provider를 새로 만들 때마다 상한을 무한 reset하지 않도록 재관찰 전 store에 read scope·metadata 2MiB/64요청의 보수 예약을 영속 반영하고 실패에도 환급하지 않는다. plan 상한은 read 32MiB·metadata network 최대32MiB/1,024요청이며 local plan의 network는 0이다. `status.budget`은 이 예약 ledger이고 정확한 실전송량은 관찰의 측정치와 구분한다. 예산/상태 불명은 dispatch하지 않는다.

## bounded 조정기와 중단

한 plan은 source scope 하나의 후보 최대 6개를 포함한다. 여러 scope는 별도 plan이며 전체 scope 합산 보고 UI는 후속 범위다. `pending`을 한꺼번에 6개 enqueue하지 않고 queued 최대3/active1로 진행한다. 기존 `execution_slot.acquire`의 동일 home 협조 lock과 M12 owner lock을 실제 사용한다. 기존 TTS/typed queue 각각의 queued≤3은 별도 큐의 한도이며 전체 home 합계3이라는 뜻은 아니다. 외부 프로세스·다른 home의 GPU 독점을 보장하지 않는다.

기본 action은 source·의존성·권한을 확인한 뒤 모델 adapter를 `model_executor_not_implemented`로 deferred한다. `run_cpu_probe`만 검토된 고정 stdlib CPU subprocess를 매 case 새로 기동하며 arbitrary command·모델 code·입력을 받지 않는다. 격리 nonce/PID 시작·종료 메시지를 검사하고 Windows suspended-start/kill-on-close Job 소유권, POSIX session/부모 사망 확인을 사용한다. **모든 probe 결과는 model_test_performed=false**다. probe_succeeded/control_validated를 모델 검수 PASS로 표시하지 않는다.

M13에서 기존 TaskInference와 연결할 때 조정기와 worker가 같은 slot을 중첩 획득하지 않도록 소유권을 단일화하거나 기존 job의 enqueue/poll/cancel 인계를 별도 검증해야 한다. 현재 CPU probe의 slot 검증을 실모델 bridge의 증거로 대체하지 않는다.

취소·timeout·실패는 현재 소유 child를 기다려 정리하고 다음 dispatch를 중단한다. terminal case와 원 reason은 불변이다. owner가 사라진 running batch는 남은 비종료 case만 interrupted로 표시하며 자동 재실행하지 않는다. 기존 완료/실패 attempt·누적 ledger를 보존한다. 필요한 재검증·재승인 후 새 attempt의 부분 재개는 M15 잔여이며 현재 같은 batch를 reset하는 API는 없다.

## CLI 사용 순서

기존 프로젝트 의존성 `requests`를 포함한 Python 3.10 이상 환경에서, 현재 shell의 `PYTHONPATH`를 `src`로 지정한다. 전역 환경 설정을 바꾸지 않는다.

```text
python -B -m ai_manager.validation_cli --home <새M12제어home> init
python -B -m ai_manager.validation_cli --home <새M12제어home> scan-local --root <명시모델root> --depth 0 --json-bytes 32768 --read-bytes 131072
python -B -m ai_manager.validation_cli --home <새M12제어home> --auth-home <새M12인증home> scan-drive --account A --root-id <허용rootID> --depth 1
python -B -m ai_manager.validation_cli --home <새M12제어home> plan --observation <관찰ID>
python -B -m ai_manager.validation_cli --home <새M12제어home> approve --plan <계획ID> --sha256 <표시한정확SHA> --confirm
python -B -m ai_manager.validation_cli --home <새M12제어home> dispatch --plan <계획ID> --approval <승인ID>
python -B -m ai_manager.validation_cli --home <새M12제어home> run --batch <batchID>
python -B -m ai_manager.validation_cli --home <새M12제어home> status --batch <batchID>
python -B -m ai_manager.validation_cli --home <새M12제어home> cancel --batch <batchID>
```

Drive plan 승인/dispatch/run에도 같은 새 `--auth-home`이 필요하다. CPU 제어 시험은 **plan 생성 시에만** `--cpu-probe`를 명시한다. 그 권한을 모델 실행 권한으로 변경할 수 없다. 개인 root/계정/Drive ID·raw 관찰·DB·자격은 공개 저장소에 올리지 않는다.
