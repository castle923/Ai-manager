# Ai-manager

두 Google Drive 계정에 보관한 AI 모델을 한곳에서 찾고, 필요한 파일을 확인하고, 새 테스트 결과를 비교하는 개인용 대시보드입니다.

> **현재 상태: v0.4.0 · 승인된 M4 첫 한국어 TTS 실행 범위 완료.** 최종 소스에서 새 WAV 생성·모델/입력/출력/소스 해시 연결·브라우저 재생·저장·실행 취소를 확인했습니다. 99개 자동/독립 테스트와 대표 폭·키보드 점검을 통과했습니다. [M4 보고서](docs/M4_REPORT.md)에 실제 E2E와 오류 주입 검증, 청취·내용 정확도 등 미검증 한계를 구분해 기록했습니다. M5 비교와 이후 단계는 아직 미승인입니다.

## 현재 조회 기능과 후속 계획

현재 대시보드는 실제 인벤토리의 후보 묶음과 파일을 검색하고 필터링하며, 메타데이터·수집 출처·관찰 항목을 상세에서 확인합니다. 후보 묶음은 계정과 실제 부모 폴더 ID로 구분한 관찰 그룹입니다. 용도 분류는 파일 경로에 근거한 추정입니다. 인벤토리 메타데이터만으로 구성·무결성·환경·실행을 판정하지 않으며, 지원하는 첫 모델의 실제 준비 결과는 별도 준비 화면에서 확인합니다.

첫 모델 다운로드·환경 준비는 M3에서 구현·검증했으며, 새 테스트 실행·오디오 재생은 승인된 M4에서 구현·실제 검증을 완료했으며, 같은 조건의 새 결과 비교는 미승인 M5의 계획입니다. 현재 화면의 모델 발견을 실행 성공으로 해석하지 않습니다.

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

`requirements.lock`에는 이번 실행에 설치한 직접·전이 런타임 의존성 버전을 기록합니다. 현재 코드의 99개 테스트와 실제 실행 검증은 [M4 보고서](docs/M4_REPORT.md), M3 당시 72개 테스트·실자산·환경·준비 UI 검증은 [M3 보고서](docs/M3_REPORT.md), 조회 대시보드 검증 이력은 [M2 보고서](docs/M2_REPORT.md), 최초 두 계정 연결·수집 이력은 [M1 보고서](docs/M1_REPORT.md)에 구분해 기록합니다.

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

## 단계별 기능

| 단계 | 사용자에게 생기는 기능 | 상태 |
|---|---|---|
| M0 | 범위·출처·검증 기준 확정 | 조사·설계·OAuth 파일 준비 완료(M0 당시 앱 실인증 미검증) |
| M1 | 두 계정의 모델을 읽기 전용으로 조회 | 두 계정 인증·갱신·수집 성공 / 승인된 M1 범위 완료 |
| M2 | 검색·필터·모델 상세 대시보드 | 승인 범위 구현·실제 목록·독립 검증 완료 |
| M3 | 선택한 모델의 로컬 준비 상태 확인 | 승인 범위 구현·13개 실자산·환경·독립 검증 완료 |
| M4 | 음성 합성 모델 1종을 실제 실행 | 승인 범위 구현·새 WAV·재생·저장·취소·독립 검증 완료 |
| M5 | 같은 계열 모델 2종의 새 실행 비교 | 미착수 |
| M6 | 재시작·오류 복구·사용 안내를 포함한 개인용 출시 | 미착수 |

첫 사용 가능한 버전은 **M2의 모델 조회 대시보드**, 첫 실제 추론 버전은 **M4**입니다. 실행 성공과 측정값은 실제 새 실행의 검증 결과에 연결합니다.

## 문서

- [M4 한국어 TTS 실행과 이번 검증 범위](docs/M4_REPORT.md)
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
