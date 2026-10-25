# Llama 무료 Colab 파일 실행

앱에서 검토한 요청 JSON을 내보내고, 준비된 무료 Colab T4에서 사용자가 직접 한 번 실행한 결과 JSON을 가져오는 기능이다. 로컬 모델 등록과 Drive 로그인 없이 새 local-only 작업실에서 열 수 있다. 결과는 파일 결합을 검사한 **외부 실행 보고**이며 로컬 `execution_verified`나 등록 모델의 verified 상태를 올리지 않는다.

## 사용 순서

1. 앱의 작업 실행 화면에서 **Llama · 무료 Colab 파일 실행**을 연다. 비밀 없는 짧은 입력을 작성하고 **입력·요청 미리보기**로 정확한 텍스트·모델 revision·INT8 조건·전체 JSON을 검토한다. 미리보기만으로 요청을 저장하지 않는다.
2. **요청 저장·JSON 다운로드**를 눌러 요청을 작업실 sidecar에 저장한다. 요청 JSON과 **공개 실행 notebook 다운로드**를 사용한다. notebook의 코드 셀 두 개를 현재 준비된 Colab notebook 끝에 추가하고 요청 파일은 Colab Files로 직접 올린다.
3. 기존 모델 cache와 정확한 실행 환경이 있는 무료 T4에서 요청·경로·조건을 검토한 뒤 실행 승인 값을 직접 바꾼다. 새 UUID 전용 context에서 생성 한 번만 허용한다. 기존 ROOT·WORK·marker·결과를 보존한다. 준비가 없거나 source/runtime/model이 다르면 중단한다. 새 패키지·모델 다운로드, 자동 Drive 연결, API 서버, 자동 재시도는 없다.
4. Colab Files에서 새 결과 JSON을 내려받아 앱의 **결과 JSON 가져오기**로 선택한다. 저장된 요청의 UUID·request digest·입력 hash·model/runtime/source 조건과 결합된 결과만 표시한다. 같은 결과를 다시 가져오면 기존 기록을 반환하고, 다른 digest의 결과는 기존 기록을 보존하며 충돌로 거절한다.

페이지를 새로 열면 결과 선택 화면의 상태는 초기화된다. 저장된 같은 결과 JSON을 다시 가져오면 sidecar의 요청과 연결하여 표시할 수 있다. 요청·결과 목록의 자동 복원 기능은 없다.

## 제한과 표시

입력은 비공백 UTF-8 최대 2,048 bytes이며 NUL·잘못된 Unicode를 허용하지 않는다. Colab tokenizer가 chat template를 포함한 1~64 입력 토큰을 확인한다. greedy·seed 0·batch 1·최대 새 출력 32토큰을 고정하며 EOS와 길이 상한을 구분한다. 요청 파일은 16 KiB, 결과는 64 KiB까지다.

고정 모델은 `llama-3.1-8b-instruct`, revision `0e9e39f249a16976918f6564b8830bc894c89659`다. 외부 실행 profile은 `llama-colab-int8-handoff-v1`이며 기존 로컬 FP16/BF16 profile과 별도다. Python 3.12.13, Torch 2.11.0+cu128, NumPy 2.0.2, Transformers 4.57.3, Accelerate 1.12.0, Safetensors 0.8.0, bitsandbytes 0.50.2 계약을 검사한다. 상속 환경 전체 `pip check` 통과를 의미하지 않는다.

성공 보고는 생성 호출·토큰·INT8/GPU 수치·offload·모델/실행 환경 검증·phase·guard 완료를 함께 요구한다. 중단/실패는 사유와 단계로 표시하고 생성문을 받지 않는다. 한국어·combining 문자·HTML 같은 문자열은 정규화하지 않고 텍스트로 표시한다. SHA-256 결합은 파일 일관성 검사이며 원격 VM 상태에 대한 독립 증명이 아니다.

새 home의 정상 앱 초기화는 빈 inventory·registry·task DB를 만들 수 있다. 이 기능의 요청·결과는 해당 home의 `colab-handoff` sidecar에만 저장한다. 기존 home·인증·키·DB·모델을 탐색하거나 복사하지 않는다. 무료 Colab의 대화형 자원과 가용성 제한에 따라 실제 실행이 불가능할 수 있다. 일반 대화 품질과 서비스 가용성은 검증 범위 밖이다.

## 2026-10-25 검증 상태

공개 소스의 계약·worker·guard·manifest·builder 원본 바이트를 최종 커밋과 새 공개 bundle에 대조했다. 고정 SHA가 일치하고 기존 로컬 profile 소스는 유지됐다. 새 프런트엔드 production build는 통과했으며 정적 index/CSS/JS는 커밋 산출물과 동일했다.

공개 테스트의 임시 경로 이식성 수정 전 통제된 최종 전체 오프라인 회귀는 **588개, 580개 통과·실패 0·오류 0·skip 8**로 75.398초에 완료됐다. skip은 새 store 및 기존 validation의 운영체제 symlink 권한 제한 2개와 별도 tracking CPU/decode 의존성이 필요한 6개다. 새 handoff 계약·bridge·HTTP·store는 40개 중 39개 통과·symlink skip 1개였다. 테스트 전후 tracked 소스 바이트는 같았다.

첫 하네스 실행의 580개·실패 12·오류 8·skip 8도 보존했다. Windows 긴 TEMP 경로와 저장소 import 경로, multiprocessing main guard 문제를 보정하고 제품 소스 변경 없이 전체를 한 번 재검증했다. import가 복원되어 실제 테스트 8개가 추가됐다. 최초 HTTP 연결 중단은 재발하지 않았으며 그 원인은 확정하지 않는다. Python 테스트 프로세스에 외부 DNS/connect 거절 audit hook을 적용했으며 차단 시도는 0이었다. OS 전체나 독립 격리 child interpreter의 네트워크 차단을 보장하지 않는다.

최종 검토에서 HTTP·store 테스트 두 파일이 비공개 과거 증거 폴더를 임시 경로로 요구하는 결함을 찾아, 표준 `TemporaryDirectory`가 실행기의 TEMP/TMP를 따르도록 수정했다. 새 OS 임시 디렉터리에 로컬 Git HEAD의 공개 소스만 풀고 과거 증거 폴더가 없는 상태에서 수정 전 대상 15개 모두 fixture 생성 오류를 재현했다. 두 테스트 파일만 반영한 뒤 같은 체크아웃에서 **15개 중 14개 통과·symlink 권한 skip 1개·실패 0·오류 0**을 확인했다. 제품 소스는 바뀌지 않았으며 전체 588개 회귀를 다시 실행한 결과는 아니다.

프런트엔드 빌드에 앞서 별도 승인된 잠금 파일의 정확한 개발 의존성 23개를 `ignore-scripts`·audit/fund 비활성 조건으로 설치했다. 전역 환경과 `package.json`·잠금 파일은 변경하지 않았으며 모델·런타임 다운로드는 없었다. 이후 빌드는 이 설치본을 재사용했다.

새 빈 home과 별도 loopback 서버의 실제 브라우저 UI에서 독립 패널 접근, 정확한 미리보기·편집 후 무효화·명시적 다운로드, 파일 선택 가져오기, 한국어·combining 문자·HTML 형태 문자열의 텍스트 표시를 확인했다. 동일 결과 재가져오기·충돌 시 기존 결과 보존·잘못된 JSON 거절·과대 파일의 client 제한, 새 페이지에서 동일 결과 재가져오기, 중단/실패/32토큰 상한 구분도 확인했다. 사후 registry와 로컬 실행 검증은 모두 빈 상태였다. 이 UI 결과는 새 합성 fixture를 사용했고 모델 실행을 의미하지 않는다.

새 paired-request 실제 Colab 실행은 **미검증·보류**다. 기존 Colab 화면은 자연 재연결 후 T4 활성 세션으로 관찰됐지만, 컴퓨터 사용 안전검사가 현재 브라우저 URL을 확인하지 못해 화면 조작을 중단했다. 모델 cache와 정확한 runtime/source 조건은 아직 검사하지 않았다. 연결 불가나 모델 실패로 판정한 것은 아니다.

기존 notebook에 빈 셀 하나만 추가됐으며 실행 소스 붙여넣기와 모델 생성은 수행하지 않았다. 기존 VM·모델·별도 새 요청을 보존했고, 다른 UI나 숨은 API로 우회하거나 모델을 재시도하지 않았다. 다음 사용자 대화에서 UI 연결이 복구되면 source/runtime/model 검사를 먼저 이어갈 수 있다. 설치나 다운로드가 필요하면 대상·용량을 사전 안내하고 멈춘다. 실제 생성·guard 완료·앱 결과 가져오기까지 새 요청으로 확인하기 전 성공으로 보고하지 않으며, 이전 고정 prompt smoke를 이번 앱 요청의 근거로 사용하지 않는다.
