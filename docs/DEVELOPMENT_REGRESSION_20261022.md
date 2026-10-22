# 새 개발 환경 회귀와 SQLite 연결 수명 수정

검증일: 2026-10-22. 사용자 지정 범위는 **회귀 검증 후 발견된 결함 수정**이다. 기준 소스는 `83cb90f8f3c3a761f93ae0830ab51ba6a740330d`, 제품 버전은 `0.19.0`이다. 새 clone·개발 branch와 저장소 밖의 고유 evidence·격리 venv·합성 임시 자료를 사용했다. GPT-6.1 sol / medium 실무와 별도 독립 검토·회귀로 진행했다.

## 수정한 제품 결함

- `History._records()`의 읽기 전용 SQLite 연결은 transaction context가 끝나도 닫히지 않았다. `closing`을 적용해 조회 성공·SQL 오류 모두 연결을 닫는다. 조회 내용과 읽기 전용 모드는 유지한다.
- `ValidationStore.connection()`의 PRAGMA 초기화가 `try/finally` 앞에 있어 손상 DB에서 초기화가 실패하면 연결이 남았다. 연결 생성 이후 설정을 `try/finally` 안으로 옮겼다. 손상 바이트 보존·자동 초기화 거절·기존 오류 계약은 유지한다.

두 신규 회귀는 실제 SQLite 연결을 강한 참조로 보존해 GC와 독립적으로 close를 확인한다. 각각 수정 전 FAIL을 재현하고 수정 후 PASS를 확인했다.

## 회귀 테스트의 이식성과 격리

- runtime timeout 테스트가 이전 `subprocess.run`만 mock해 실제 `run_external` 경계를 가로채지 못했다. 현재 경계에 timeout을 주입하고 호출 1회·대상·120초 한도를 검사한다. 실제 프로세스 생성을 거절하는 audit 조건에서 수정 전 ERROR, 수정 후 PASS를 확인했다.
- UTF-8 JSON 읽기와 Node 왕복 파이프의 encoding을 명시했다. 한국어 Windows의 기본 cp949 때문에 합성 provenance를 못 읽거나 브라우저 왕복 metadata가 손상되던 테스트를 수정했다. 정수 정밀도·서버 fingerprint 보존 검사는 유지한다.
- SQLite fixture는 연결을 명시적으로 닫고 쓰기 transaction의 commit/rollback을 유지한다. 작업실 HTTP fixture의 home은 `tempfile`이 관리하는 루트 대신 새 하위 디렉터리로 분리했다. 새 하위 home의 실제 보호 ACL 통과를 확인했으며 제품 보안 검사는 변경하거나 mock하지 않았다.

## 이번 실행 결과

환경은 Windows의 새 venv Python `3.12.14`, Node `24.19.0`이다. `requirements.lock`과 `requirements-desktop.lock`의 고정 의존성을 새 venv에 설치했고 잠금 파일은 변경하지 않았다. 출처 commit·lock SHA-256·설치 목록·새 로그는 저장소 밖의 고유 evidence에 기록했다.

| 검사 | 새 결과 |
|---|---|
| 최종 독립 Python 전체 회귀 | **477개 중 470개 통과·7개 skip·실패/오류 0**, 64.328초 |
| 동결 검증 | 전체 회귀 전후 추적 소스 파일 SHA-256 동일, 변경 0 |
| 기존 Node 다운로드 검증 helper | **6개 통과**, 63.3963ms; fake invoke와 메모리 ledger만 사용 |
| sandbox 밖 DPAPI·Claude 합성 타깃 | 2개 통과, 0.045초; 실제 사용자 키·API transport 사용 없음 |

7개 skip은 tracking CPU 의존성 미설치 4개, tracking 영상 decode 의존성 미설치 2개, OS의 비관리자 symlink 생성 제한 1개다. 이번 수정에서 검사를 새로 skip하거나 guard를 완화하지 않았다.

초기 전체 실행은 잘못된 timeout mock에서 멈춰 중단했으므로 PASS 근거가 아니다. 첫 독립 회귀는 476개 중 실패 1·오류 4·skip 7이었고 해당 결과를 보존했다. 여기에는 추가 발견한 손상 DB 연결 누수·Node encoding·temp home ACL 문제와 외부 회귀 harness의 multiprocessing main guard 누락 1건이 포함됐다. harness import 경로·main guard 결함은 제품 결함으로 분류하지 않았으며 최종 회귀 전에 바로잡았다.

sandbox에서는 DPAPI 보호 실패와 일부 ACL 검증 실패가 있었다. 새 합성 자료만 정상 사용자 컨텍스트에서 다시 검증해 환경 원인을 구분했다. 기존 사용자 저장소를 열거나 평문 대체를 하지 않았다. 최종 harness의 해당 Python 프로세스에서 loopback 이외 연결 차단 건수는 0이었다. 이 audit는 하위 프로세스나 OS 전체 외부 통신을 계측·차단했다는 뜻은 아니다.

## 보존한 범위와 미검증 사항

개인 home·token·API key·DB·모델·인벤토리와 과거 실행 결과를 입력으로 쓰거나 자동 탐색·복사하지 않았다. 전역 Python·PATH·다른 프로젝트 환경과 기존 인증·DB·모델·보안 설정을 변경하지 않았다. 제품 변경은 SQLite 연결 수명 두 곳이며 새 기능이나 의존성 버전 변경은 없다.

실제 Claude API 전송은 무료 count를 포함해 **0회**다. Drive 수집·다운로드·쓰기, OAuth, 실제 모델 추론, 새 Release·설치 자산 게시를 수행하지 않았다. Node 검사는 실제 브라우저 다운로드가 아니다.

이 결과는 오프라인 단위·합성 HTTP·DPAPI 계약의 범위다. 실제 Windows 창·frozen 패키지·모델별 Python 3.10 런타임·GPU·실제 추론·새 PC 실계정 인증을 Python 3.12에서 검증한 결과로 확대하지 않는다. 프런트엔드 소스·번들은 변경하지 않았으며 이번에 npm build는 실행하지 않았다.
