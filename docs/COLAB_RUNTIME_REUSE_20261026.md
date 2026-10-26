# Colab 설치 재사용과 전체 사전 검사 분리

2026-10-26. 이번 변경은 노트북 코드와 로컬 오프라인 검증이다. Colab 연결·설치·다운로드·모델 실행·과금은 수행하지 않았으며 실제 RAM 감소나 새 GPU 성공을 측정하지 않았다.

## 변경과 보존 범위

기존 준비 셀은 클릭할 때마다 새 ROOT와 venv를 생성하고 공개 wheel을 받아 설치한 뒤 전체 사전 검사를 실행했다. 이제 설치 성공 시 ROOT/Python/metadata 경로, 정리된 자식 환경, 공개 payload SHA, 정확한 활성 패키지 버전과 base 모듈 경로를 별도의 `PREPARED_CONTEXT`로 확정한다. 같은 커널에서 준비를 다시 누르면 디스크의 공개 파일과 실제 격리 자식의 Torch/NumPy 버전·distribution 버전·모듈 경로를 재검사하고 모두 일치할 때만 설치를 건너뛴다. 부모 notebook 프로세스는 Torch/NumPy를 import하지 않는다. 정상 venv Python의 파일 symlink는 허용하며 lexical sibling 경로와 부모 경로 결합을 검사한다.

불완전한 설치, 변경된 ROOT/Python/환경/source/버전, probe 오류는 중단한다. 자동 새 ROOT 생성, pip 수리, 기존 파일 삭제나 덮어쓰기는 하지 않는다. 이 재사용은 현재 커널에서 성공적으로 준비한 동일 ROOT에 한정한다. 다른 ROOT나 커널 재시작 뒤 환경을 자동 탐색·재사용하지 않는다. 중복 설치·venv·공개 캐시의 추가 생성을 예방하는 변경이며 기존 캐시 청소나 RAM 절감량을 보장하지 않는다.

전체 사전 검사는 별도 `ALLOW_FULL_PREFLIGHT=False` gate로 분리했다. 원래 full probe의 tiny INT8/GPU·메타모델·cgroup namespace·메모리 조건을 그대로 실행한다. proof와 stdout/stderr는 `ROOT/preflight-UUID`의 새 디렉터리에 쓰므로 이전 proof를 보존한다. 실패 시 부분 생성된 freshness와 다운로드 context를 폐기하되 검증된 설치는 유지한다. 정상 준비 셀 재클릭만으로 유효한 결과 표시 context를 지우지는 않는다.

기존 600초 freshness TTL, 마스킹 토큰 대기를 포함하는 최대 1,800초 다운로드 deadline, once 기록, 고정 모델 revision, 원래 worker/guard의 2 GiB OS floor·8 GiB hard RSS cap 및 다른 guard 조건은 유지했다. getpass의 대기를 강제로 중단하지 못하는 기존 제한도 같다. 토큰 입력과 다운로드는 기존 `ALLOW_MODEL_DOWNLOAD=False` gate가 열릴 때만 가능하다. 사용자 대기로 freshness가 만료되면 설치를 반복하지 않고 허용된 전체 사전 검사부터 확인한다. 재검사는 이전 다운로드 context를 자동 재결합하지 않으며 이미 소모된 다운로드/실행 once의 재시도나 새 batch 재사용은 이번 범위가 아니다.

## 새 산출물과 바이트 결합

새 이름은 `Llama_Free_T4_INT8_Reusable_Runtime.ipynb`이며 89,949 bytes, SHA-256은 `0d44c5e2c13eaf972e680ee507f4d6e6425e2cf3602324264daeab23af861913`이다. 원본 `Llama_Free_T4_INT8_Exit_Confirmation.ipynb`의 SHA-256 `5796fff3f78ad7fd915da99c7750d488c4ef82457dc877528658f26751a6e5c1`을 보존했다. 새 packet은 지정 원본 input SHA와 frozen r02 세 공개 source pin을 확인한 기존 builder에서 새 출력 경로로 생성했다. provenance에 원본·builder·payload·새 notebook SHA와 직렬화 크기를 기록했다.

실제 두 packet을 읽어 새 notebook에 내장된 9개 payload가 원본과 모두 바이트 단위로 동일함을 확인했다. downloader/meta/worker/guard/model manifest payload와 앱 handoff contract·bridge·source pins는 변경하지 않았다. 전체 사전 검사 호출 wrapper의 출력 디렉터리만 달라졌으며 worker가 받는 원래 metadata 파일은 그대로다. 기존 결과 확인 helper의 context tuple와 고정 SHA도 유지했다. 원본 packet이나 이전 proof를 현재 성공 근거로 재사용하지 않는다.

## 새 오프라인 검증

새 회귀의 최초 실행은 미구현 진입점 때문에 4개 오류였고 구현 후 통과했다. 독립 검토에서 metadata만 맞고 실제 NumPy 모듈 버전이 다른 경우를 추가해 수정 전 실패를 재현한 뒤, 격리 자식의 실제 모듈 검사를 보강해 통과했다. 새 회귀는 8개이며 재클릭 무설치, 불완전 준비 무재시도, ROOT/Python/환경/payload/활성 버전 변조, 실제 모듈 버전 불일치, namespace 위반, probe timeout/부분 실패, 이전 proof 보존과 UUID별 성공 proof, 기본 OFF를 확인한다. subprocess/GPU는 합성 자료·mock으로 검증했으며 모델은 로드하지 않았다.

최종 관련 `test_colab*.py` 회귀는 **122개 중 121개 통과·실패 0·오류 0·Windows symlink 권한 skip 1개**, 12.047초였다. 실행 Python에 외부 DNS/connect 거절 audit hook을 적용했고 차단 시도는 0이었다. 정상 로컬 HTTP 테스트의 loopback만 허용했다. 이 hook은 OS 전체나 별도 child interpreter의 네트워크 방화를 의미하지 않는다. 전체 제품 회귀를 새로 수행한 결과는 아니다.

생성된 실물 notebook의 기본 Run all을 별도로 실행했다. 파일 읽기/쓰기와 subprocess·인증·네트워크·heavy module import를 거절한 상태에서 stdlib 검증, 네 실단계 SKIP, 결과 확인 `not_ready`가 통과했다. 코드 셀은 실행 결과가 없는 상태이며 모든 원격 gate는 False다. C 드라이브의 사전 여유 검사와 새 출력 경로의 배타 생성 규칙을 유지했다.

실제 무료 T4의 현재 가용성, cache/runtime 준비 상태, 준비 재사용의 원격 동작과 RAM/GPU 개선 효과, 새 앱 요청부터 결과 가져오기까지 E2E 및 새 Windows 설치 프로그램은 미검증이다. 직전 2026-10-26 읽기 전용 관측에서는 무료 T4가 연결됐으나 일일 무료 리소스 소진·종료 임박 경고가 표시됐다. 이는 2026-10-25의 GPU 사용량 제한에 따른 재연결 거절 이력과 구분한다. 이번 오프라인 작업에서는 새 재연결을 수행하지 않았으며 현재 연결 상태도 검증하지 않았다.
