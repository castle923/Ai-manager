# Ai-manager

## Windows v0.10.0 배포 패키지

[v0.10.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.10.0)의 소스는 `5a336cd0522fadda68f179ed4b8c5b0d4059aa5f`다. `AiManager-0.10.0-windows.zip`은 **113,228,585 bytes**, SHA-256 `a05e47f512b728a3241df5b504014f716a759962707093b5f5d972bb5f2ce730`이며 별도 `SHA256SUMS.txt`로 확인할 수 있다.

새 ZIP의 별도 설치·8,327개 payload 해시·독립 창 진입, 새 0.6B TTS 한 번과 재생, 정상 재시작 후 기록 31개 및 새 결과 유지, 선정 기존 파일 190개·DB·runtime 상태 보존을 확인했다. 동일 PC·기존 home/runtime 재참조와 process PATH의 전역 Python 제외 범위이며 Python 미설치 별도 PC 검증은 아니다. EXE는 **NotSigned**다.

ZIP 전체를 기존 설치를 덮어쓰지 않는 새 폴더에 푼다. Python 기반은 동봉하지만 모델·모델별 라이브러리 환경·인증·DB·출력은 포함하지 않는다. 기존 환경을 쓰면 원래 Python 기반과 venv를 보존한다. 새 인증 UI는 “연결 정보 없음”이며 표시 원인·회귀 여부와 새 OAuth 연결·갱신은 미검증이다. 이번 native 저장 대화상자·다종 모델 전체 행렬도 다시 검증하지 않았다.

이전 candidate6의 TTS 취소/저장·Whisper·합성 TAPIR·A/B 검증과 이번 새 패키지의 선별 TTS 검증을 구분한다. 이전 C6의 LLM 자원 gate 실패·Whisper 전사 차이·합성 TAPIR 표본, 로컬 이미지 미준비·앱 원격 provider 통합 미완과 품질·미검증 변형의 제한은 유지한다. 상세는 [M10 설치 안내](docs/M10_INSTALL.md)와 [M10 보고서](docs/M10_REPORT.md)를 따른다. 후속 docs commit은 ZIP·태그 소스를 바꾸지 않으며 아래 v0.7.0/candidate6 설명은 당시 기록이다.


> C6 후속 결과: 동일 새 조건의 TTS A/B 양쪽 생성·재생과 새 8개 기록의 정상 재시작 후 유지까지 확인했다. 상세 선택은 재선택 검증이며 자동 복원 판정이 아니다. 기존 22개 이력 전체 UI ID·모든 필터 검증은 하지 않았다. 최종 전체 완료나 이미지 로컬 성공으로 확대하지 않는다.

> 현재 candidate6 실제 사용 갱신: 이번 새 TTS 생성·running 취소·소유 자식 정리, 사용자 수동 native 저장/취소와 저장본 SHA 일치, 새 Whisper 전사 및 16프레임 합성 TAPIR 추적을 확인했다. Whisper는 원문 차이가 있어 정확도 PASS가 아니며, TAPIR는 실물 영상 검증이 아니다. LLM은 RAM/GPU/disk 공통 자원 gate에서 실패해 출력이 없었다. 새 TTS A/B 양쪽 cold 생성·native 재생 완료와 정상 종료·재시작 후 새 8개 기록 유지까지 확인했다. 기존 DB 행 fingerprint·환경 보존과 대표 STT JSON의 사용자 수동 native 저장·해시 일치도 확인했다. 추가 TAPIR PNG·A/B 저장 변형은 미검증으로 남긴다. 아래 남은 검증/초기 상태와 최신 항목별 결과를 [M10 보고서](docs/M10_REPORT.md)에서 구분한다.


## 현재 공개 버전과 M10 후보

공개 프로그램 다운로드는 [v0.7.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.7.0)다. 로컬 **0.10.0 candidate6**는 M10 다종 작업·런타임 통합 검증 후보이며 새 Release/설치 자산을 공개한 상태가 아니다. source 게시와 실제 설치본 기능 검증을 구분한다. 현재 후보의 새 설치·실제 앱 창 진입은 확인했고 명시한 새 실행·취소·저장·기록·재시작 표본을 확인했지만 M10 전체 PASS가 아니다. Windows 로컬 이미지 생성·앱 원격 GPU 연동 완료도 주장하지 않는다.

[M10 계획](docs/M10_PLAN.md) · [통합 진행 보고](docs/M10_REPORT.md) · [후보 설치 및 source→UI→wheel/native 빌드 순서](docs/M10_INSTALL.md) · [별도 Linux 원격 GPU 이력](docs/M10_RUNPOD_REPORT.md)

소스 재현은 아래 기본 개발 절차와 M10 안내를 함께 따른다. 생성 static을 저장소에서 가져오는 방식이 아니므로 `frontend`의 고정 npm lock으로 `npm.cmd ci --ignore-scripts`와 `npm.cmd run build`를 **wheel/native 빌드 전에** 실행한다. 기존 환경을 재참조하는 설치에서는 원래 candidate3 Python 기반과 library runtime을 삭제·이동하지 않는다. 기존 TTS·STT·TAPIR·Llama 환경을 재설치하거나 인증·DB·출력을 새로 복사할 필요가 없다.

아래 기존 버전별 설명은 해당 단계의 기록이다. 후보 기능·시험 결과·공개 다운로드의 범위를 위 안내와 구분한다.


두 Google Drive 계정에 보관한 AI 모델을 한곳에서 찾고, 필요한 파일을 확인하고, 새 테스트 결과를 비교하는 개인용 대시보드입니다.

**전체 구상은 아직 진행 중입니다.** M0–M7의 TTS 중심 단계·독립 앱, M8의 모델 등록·통합 상태에 이어 **M9 통합 작업 기록·보기 설정·성능 차트**를 확인한 Windows 환경에서 검증했습니다. 후보 3의 새 A/B·차트/원천 표·재생·정상 WAV 저장·설정 유지·정상 재시작을 확인했으며 이번 변경에는 검증된 M9 구현 소스와 문서를 함께 반영합니다. 로컬 0.9.0 후보와 공개 다운로드 v0.7.0은 구분합니다. M10 다종 모델 실행과 향후 자동화는 아직 완료되지 않았습니다. [M9 검증과 제한](docs/M9_REPORT.md) · [M9 사용 안내](docs/M9_INSTALL.md) · [전체 후속 계획](docs/M8_PLAN.md)

처음 사용한다면 **[쉬운 실행·기능 사용 가이드](docs/USER_GUIDE.md)**에서 ZIP 실행부터 로그인·모델 준비·음성 생성·저장 순서를 확인하세요.

> **현재 상태: v0.7.0 Python 포함 Windows 독립 앱 출시 완료(확인한 로컬·0.6B 범위).** 새 설치·두 계정 인증·번들 추론 환경·CUDA·새 TTS·재생·native WAV 저장·취소·종료/재시작을 검증했습니다. [v0.7.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.7.0) · [v0.7.0 독립 앱 시작 안내](https://github.com/castle923/Ai-manager/blob/066e62d286cb50fee1755bd0146c3ddbd3188526/docs/M7_INSTALL.md) · [M7 검증 보고서](docs/M7_REPORT.md)

앱과 추론용 Python 기반을 포함합니다. WebView2 Runtime은 시스템 전제이며 첫 Torch 의존성 준비에는 인터넷과 수 GB의 공간이 필요합니다. 모델·개인 인증 자료는 배포물에 포함하지 않습니다. v0.7.0 출시 당시 실제 TTS 검증은 0.6B 한 모델 범위였으며 당시 1.7B 새 추론·Python 미설치 별도 PC·전면 접근성은 미검증이었습니다. 이후 0.7.1 및 M9의 두 모델 새 검증은 각 후속 보고서와 구분합니다.

[v0.7.0 Windows 독립 앱 ZIP 받기](https://github.com/castle923/Ai-manager/releases/download/v0.7.0/AiManager-0.7.0-windows.zip) · 58,405,026 bytes · SHA-256 `661d8bd5b58edfa4e2ba811338fce787fb1744149c98caacd7deac4489eae4d0`. 공개 Release의 uploaded asset 크기·GitHub SHA-256 digest를 검증된 로컬 ZIP과 대조했습니다. 태그는 소스 커밋 `066e62d286cb50fee1755bd0146c3ddbd3188526`에 고정하며 이후 main의 문서 갱신은 앱·ZIP 변경이 아닙니다.

기존 Python 3.10이 필요한 v0.6.0 launcher 배포와 검증 이력은 [v0.6.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.6.0) · [M6 보고서](docs/M6_REPORT.md)에 보존합니다.

**후속 0.7.1 후보의 새 Windows A/B 검증을 완료했습니다.** 모델 원본 경로 확인과 실패 정보 표시를 보완하고, 같은 새 한국어 입력의 0.6B/1.7B 실제 실행·앱 재생·두 native 저장본 무결성을 확인했습니다. 결과와 미확정 원인은 [새 A/B 보고서](docs/M7_AB_REPORT.md)를 따릅니다. 이 후보의 소스 반영과 공개 배포를 구분하며 다운로드용 Release는 위 v0.7.0을 유지합니다.

[이전 v0.6.0 배포 ZIP](https://github.com/castle923/Ai-manager/raw/899cf8a5b9616d3773caf2fb7ebf47db99544002/releases/v0.6.0/ai-manager-0.6.0-windows.zip) · 157,240 bytes · SHA-256 `b1626bc374196984033b56d5eeaf89f2cfc30b0e6baa762dd32744f0cd865133`. [v0.6.0 설치 안내](docs/INSTALL.md)를 따릅니다. 해당 태그는 소스·ZIP 커밋 `899cf8a5…`에 고정해 보존합니다.

## 현재 조회 기능과 후속 계획

현재 대시보드는 실제 인벤토리의 후보 묶음과 파일을 검색하고 필터링하며, 메타데이터·수집 출처·관찰 항목을 상세에서 확인합니다. 후보 묶음은 계정과 실제 부모 폴더 ID로 구분한 관찰 그룹입니다. 용도 분류는 파일 경로에 근거한 추정입니다. 인벤토리 메타데이터만으로 구성·무결성·환경·실행을 판정하지 않으며, 지원하는 첫 모델의 실제 준비 결과는 별도 준비 화면에서 확인합니다.

첫 모델 다운로드·환경 준비는 M3에서 구현·검증했으며, 새 테스트 실행·오디오 재생은 승인된 M4에서 구현·실제 검증을 완료했으며, 같은 조건의 새 결과 비교는 M5에서 실제 GPU 실행·재생·부분 취소를 검증했습니다. 정상 지원 Edge의 A/B 저장 무결성까지 확인했으며 이전 Chrome 차단 원인은 미확정 제한으로 보존합니다. 현재 화면의 모델 발견을 실행 성공으로 해석하지 않습니다.

## 소스에서 로컬 실행

Windows Python 3.10 이상과 Node.js가 필요합니다. Vite 7의 Node 요구 버전은 20.19 이상 또는 22.12 이상이며, 이번 빌드는 Node 24.21.0 / npm 11.19.0에서 확인했습니다. React 19.2.0·TypeScript 5.9.3·Vite 7.3.7 및 전이 의존성은 `frontend/package-lock.json`으로 고정합니다. Python 직접 런타임 의존성은 `requests==2.32.5`, 빌드 의존성은 `setuptools>=68`입니다.

생성된 화면 번들은 Git에 포함하지 않습니다. 새 소스 설치에서는 먼저 아래처럼 UI를 빌드해야 `serve`로 화면을 열 수 있습니다. `npm.cmd run build`는 TypeScript 검사 후 `src/ai_manager/static`에 HTML·JavaScript·CSS를 생성합니다. Python wheel을 만들 때도 UI 빌드를 먼저 수행하며, 생성 번들은 package-data로 wheel에 포함됩니다. 기존 앱 설정이 있다면 `init`·`connect`·`scan`을 반복할 필요 없이 빌드·설치 후 `serve`를 실행합니다.

아래 명령은 저장소 루트의 PowerShell에서 시작합니다.

```powershell
Set-Location frontend
npm.cmd ci --ignore-scripts
npm.cmd run build
Set-Location ..
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m ai_manager.cli init --allowlist "<private_allowlist_json>" --client "<desktop_oauth_client_json>"
.\.venv\Scripts\python.exe -m ai_manager.cli connect A
.\.venv\Scripts\python.exe -m ai_manager.cli connect B
.\.venv\Scripts\python.exe -m ai_manager.cli refresh A
.\.venv\Scripts\python.exe -m ai_manager.cli refresh B
.\.venv\Scripts\python.exe -m ai_manager.cli scan A
.\.venv\Scripts\python.exe -m ai_manager.cli scan B
.\.venv\Scripts\python.exe -m ai_manager.cli status
.\.venv\Scripts\python.exe -m ai_manager.cli serve
```

꺾쇠 입력은 이번 프로젝트에서 지정한 저장소 밖 파일의 개인 경로로 바꿉니다. JSON 내용이나 실제 경로를 공개 저장소에 넣지 않습니다. allowlist 원본에는 `accounts`의 A/B 계정 매핑과 `roots`의 `account`·`id`·비어 있지 않은 `alias` 항목이 필요합니다(`name`은 선택사항). 기존 설정이 있으면 `init`은 덮어쓰지 않습니다. `connect`는 시스템 브라우저를 열고 최대 5분 동안 사용자 로그인·동의를 기다립니다. 두 계정을 각각 연결해야 하며 로그인·동의는 사용자 직접행위입니다.

`serve`는 임의 포트의 `127.0.0.1`에서 모델 조회·선정 모델 준비 대시보드를 엽니다. 해당 화면에서도 연결·갱신·스캔·해제와 작업 취소를 요청할 수 있습니다. CLI 연결 해제는 `disconnect A` 또는 `disconnect B`입니다. 토큰은 Windows 사용자 DPAPI로 암호화하고 설정·개인 인벤토리는 저장소 밖 앱 전용 비공개 위치에 보관합니다. 출력의 `credential_saved`는 저장된 인증정보 존재 표시이며 현재 권한·조회 성공과 별도로 확인해야 합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements.lock`에는 이번 실행에 설치한 직접·전이 런타임 의존성 버전을 기록합니다. 현재 M5 소스의 123개 자동·독립 테스트와 실제 비교 검증·다운로드 BLOCK은 [M5 보고서](docs/M5_REPORT.md), M4 당시 99개 테스트와 실제 실행 검증은 [M4 보고서](docs/M4_REPORT.md), M3 당시 72개 테스트·실자산·환경·준비 UI 검증은 [M3 보고서](docs/M3_REPORT.md), 조회 대시보드 검증 이력은 [M2 보고서](docs/M2_REPORT.md), 최초 두 계정 연결·수집 이력은 [M1 보고서](docs/M1_REPORT.md)에 구분해 기록합니다.

## M3 첫 모델 준비

현재 승인된 첫 준비 대상은 `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`입니다. 공식 revision `85e237c12c027371202489a0ec509ded67b5e4b5`의 manifest를 기준으로 지정된 읽기 전용 Drive 자산만 새 실행 디렉터리에 내려받습니다. 목록 발견과 준비 계획이 가능하더라도 다운로드·해시·환경 검증이 끝나기 전 준비 완료가 아닙니다. 이번 전량 바이트·해시·환경 검증 결과와 보존한 실패·중단 기록은 [M3 보고서](docs/M3_REPORT.md)를 따릅니다.

앱 환경과 별도 추론 의존성 환경을 분리합니다. 아래 환경 설치 스크립트는 기존 환경을 덮어쓰지 않으며 모델을 로딩하거나 추론하지 않습니다. 새 설치가 성공해야 환경 검사 명령을 실행합니다. 준비 명령은 새 다운로드를 시작하므로 현재 상태만 확인하려면 `preparation-status`를 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m ai_manager.cli preparation-status
powershell.exe -NoProfile -File .\scripts\setup_runtime.ps1
.\.venv\Scripts\python.exe -m ai_manager.cli runtime-check
.\.venv\Scripts\python.exe -m ai_manager.cli prepare
```

이 PC에서는 Windows PowerShell 5.1(`powershell.exe`)의 현재 정책이 RemoteSigned이고 이 로컬 스크립트에 Zone.Identifier가 없어 위 실행 경로가 허용되는 조건을 확인했습니다. PowerShell 7(`pwsh`)은 현재 Restricted이므로 직접 `.ps1` 실행 안내와 구분합니다. 실행 정책 변경·우회는 수행하지 않았습니다. 스크립트 자체를 새로 실행한 검증은 하지 않았고 이번 환경은 동일한 설치 단계의 수동 실행으로 검증했습니다.

`setup_runtime.ps1`은 Python 3.10 별도 venv에 pip 26.2.1과 PyTorch/torchaudio 2.9.1의 공식 CUDA 12.8 wheel을 먼저 설치한 뒤 `requirements-runtime.lock`의 97개 고정 버전(qwen-tts 0.1.1·gradio 5.49.1 포함)을 설치하고 `pip check` 후 같은 lock을 비공개 환경 기록으로 복사합니다. 이번 별도 환경의 설치·오프라인 import·CUDA 행렬연산과 실제 모델 전량 준비 검증은 통과했습니다. UI의 준비·환경 검사도 같은 기능을 사용합니다. 구성 충족·바이트 해시 일치·환경 준비와 모델 실행 성공은 별개이며 M4 추론은 이 명령에 포함하지 않습니다.

## M4 한국어 음성 실행

준비된 첫 모델의 실행 작업실에서 새 한국어 문장을 입력합니다. 현재 지원 조건은 Korean / Sohee / batch 1이며 instruct는 지원하지 않습니다. 입력은 최대 300자, 실행 제한은 600초·최대 1,024개 신규 토큰입니다. EOS 종료가 확인되지 않은 결과는 완료로 저장하지 않습니다. 이 제한은 기능 범위이며 모든 길이의 입력이 성공한다는 보장은 아닙니다.

실행마다 13개 모델 파일의 SHA-256을 다시 확인하고 별도 작업 프로세스에서 오프라인으로 모델을 로딩합니다. GPU 작업은 한 번에 1개이며 최대 3개가 기다릴 수 있습니다. 매 실행이 콜드 로딩이고 이전 WAV나 결과 캐시를 새 출력으로 사용하지 않습니다. 실행별 입력·모델·환경·출력 해시와 시각은 저장소 밖 비공개 실행 디렉터리에 남습니다.

실행 중 취소, 대기 작업 취소, 시간 초과, 비정상 종료와 손상 출력은 완료 상태와 구분됩니다. 완료 WAV는 브라우저에서 재생하거나 저장합니다. 오디오 요청의 Range에는 전체 파일 200 응답을 반환하는 현재 제한이 있습니다. 실제 발음·내용 정확도와 품질 비교는 자동 검증하지 않습니다. M4의 현재 E2E 판정과 알려진 제한은 [보고서](docs/M4_REPORT.md)를 따릅니다.

## M5 두 모델 새 A/B 비교

명시 승인된 대상은 Qwen3-TTS 0.6B 및 1.7B CustomVoice입니다. 비교 요청마다 동일한 새 한국어 입력·seed·공통 생성 조건으로 두 모델을 콜드 순차 실행하며 새 비교 ID와 두 실행 ID를 기록합니다. Korean / Sohee / batch 1, instruct 제외, 최대 300자·600초·1,024개 신규 토큰 조건을 사용합니다. 과거 WAV나 측정값을 새 비교 결과로 사용하지 않습니다.

두 모델의 시간·WAV·PyTorch peak GPU allocated memory를 해당 새 실행에 연결합니다. 메모리 수치는 전체 장치 VRAM과 구분하며 작은 표본을 일반 성능 순위로 해석하지 않습니다. 한쪽 실패는 부분 완료이며 자동 승자는 없습니다. 두 모델이 모두 성공한 경우에만 사용자가 직접 평가할 수 있습니다. 실제 준비·생성·재생·저장·취소·오류 검증 현황은 [M5 보고서](docs/M5_REPORT.md)를 따릅니다.

## 단계별 기능

| 단계 | 사용자에게 생기는 기능 | 상태 |
|---|---|---|
| M0 | 범위·출처·검증 기준 확정 | 조사·설계·OAuth 파일 준비 완료(M0 당시 앱 실인증 미검증) |
| M1 | 두 계정의 모델을 읽기 전용으로 조회 | 두 계정 인증·갱신·수집 성공 / 승인된 M1 범위 완료 |
| M2 | 검색·필터·모델 상세 대시보드 | 승인 범위 구현·실제 목록·독립 검증 완료 |
| M3 | 선택한 모델의 로컬 준비 상태 확인 | 승인 범위 구현·13개 실자산·환경·독립 검증 완료 |
| M4 | 음성 합성 모델 1종을 실제 실행 | 승인 범위 구현·새 WAV·재생·저장·취소·독립 검증 완료 |
| M5 | 같은 계열 모델 2종의 새 실행 비교 | 승인 기능 검증 완료(확인한 로컬·Edge 범위) / Chrome 알려진 제한 |
| M6 | 최신 패키지·신규 환경 설치·재시작/인증/DB/작업 복구·Edge 실제 사용 | 확인한 Windows/Edge 범위 출시 완료 · v0.6.0 Release |

첫 사용 가능한 버전은 **M2의 모델 조회 대시보드**, 첫 실제 추론 버전은 **M4**입니다. 실행 성공과 측정값은 실제 새 실행의 검증 결과에 연결합니다.

## 문서

- [Windows 설치와 실행](docs/INSTALL.md) · [보존 우선 복구](docs/RECOVERY.md)
- [프로그램 배포 형태 비교](docs/WINDOWS_DISTRIBUTION.md)
- [M6 개인용 로컬 출시 검증과 알려진 제한](docs/M6_REPORT.md)
- [M5 두 모델 비교와 당시 검증 범위](docs/M5_REPORT.md)
- [다운로드 자동검증 timeout 계약과 오프라인 검증](docs/DOWNLOAD_VALIDATION.md)
- [M4 한국어 TTS 실행과 당시 검증 범위](docs/M4_REPORT.md)
- [M3 첫 모델 준비와 당시 검증 범위](docs/M3_REPORT.md)
- [M2 대시보드 구현과 이번 검증 범위](docs/M2_REPORT.md)
- [M1 실제 수집 결과와 검증 범위](docs/M1_REPORT.md)
- [현재 승인 범위와 이후 필요한 승인](docs/APPROVALS.md)
- [M0 조사 결과와 미검증 사항](docs/M0_REPORT.md)
- [OAuth 준비 현황과 다음 단계](docs/SETUP_PREREQUISITES.md)
- [제품 품질과 단계별 검증 기준](docs/QUALITY_GATES.md)
- [제품 범위와 화면 계획](docs/PLAN.md)
- [수집·검증·실행 파이프라인](docs/PIPELINE.md)
- [마일스톤·완료 기준·검증 시나리오](docs/MILESTONES.md)
- [작업 규칙과 결과물 재사용 금지](AGENTS.md)

## 보존과 출처

- 기존 프로젝트의 코드·이미지·워크플로·로그·실행 결과를 가져오지 않고 새로 구현합니다.
- 지정된 모델 가중치와 필수 구성요소, 공개 라이브러리 및 공식 문서는 사용할 수 있습니다.
- Drive 원본은 조회와 선택한 파일의 다운로드 대상으로만 사용합니다. 삭제·이동·업로드 자동화는 초기 범위에서 제외합니다.
- 이 공개 저장소에는 자격 증명, 개인 Drive 목록·파일 ID·로컬 경로, 모델 가중치와 개인 결과물을 올리지 않습니다.
- 실제 실행 데이터는 로컬에 보관하며, 공개 예시는 별도 생성하고 예시임을 표시합니다.

작성일: 2026-10-16 (Asia/Seoul)


