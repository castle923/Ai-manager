# Ai-manager

두 Google Drive 계정에 보관한 AI 모델을 한곳에서 찾고, 필요한 파일을 확인하고, 새 테스트 결과를 비교하는 개인용 대시보드입니다.

> **현재 상태: v0.2.0 · M2 실제 목록 조회 대시보드 구현·새 검증 완료.** 실제 수집 목록에서 검색·계정/용도 후보/파일 유형 필터·정렬·페이지 조회·수집 이력 선택·후보 묶음/파일 상세를 사용할 수 있습니다. 이번 확인 화면은 549개 파일 관찰·77개 폴더 후보 묶음이며, 중복 제거하거나 실행을 검증한 모델 개수가 아닙니다. [M2 보고서](docs/M2_REPORT.md)에 새 검증과 한계를 기록했습니다. M3 이후의 다운로드·환경 준비·추론·비교는 아직 승인되지 않았습니다.

## 현재 조회 기능과 후속 계획

현재 대시보드는 실제 인벤토리의 후보 묶음과 파일을 검색하고 필터링하며, 메타데이터·수집 출처·관찰 항목을 상세에서 확인합니다. 후보 묶음은 계정과 실제 부모 폴더 ID로 구분한 관찰 그룹입니다. 용도 분류는 파일 경로에 근거한 추정이며, 구성 충족·무결성·런타임 준비·실행은 미확인으로 표시합니다.

선택 모델 다운로드·환경 준비는 M3, 새 테스트 실행·오디오 재생은 M4, 같은 조건의 새 결과 비교는 M5의 계획입니다. 현재 화면의 모델 발견을 실행 성공으로 해석하지 않습니다.

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

`serve`는 임의 포트의 `127.0.0.1`에서 M2 조회 대시보드를 엽니다. 해당 화면에서도 연결·갱신·스캔·해제와 작업 취소를 요청할 수 있습니다. CLI 연결 해제는 `disconnect A` 또는 `disconnect B`입니다. 토큰은 Windows 사용자 DPAPI로 암호화하고 설정·개인 인벤토리는 저장소 밖 앱 전용 비공개 위치에 보관합니다. 출력의 `credential_saved`는 저장된 인증정보 존재 표시이며 현재 권한·조회 성공과 별도로 확인해야 합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements.lock`에는 이번 실행에 설치한 직접·전이 런타임 의존성 버전을 기록합니다. 이번 테스트·실제 목록·반례·UI 검증은 [M2 보고서](docs/M2_REPORT.md), 최초 두 계정 연결·수집 이력은 [M1 보고서](docs/M1_REPORT.md)에 구분해 기록합니다.

## 단계별 기능

| 단계 | 사용자에게 생기는 기능 | 상태 |
|---|---|---|
| M0 | 범위·출처·검증 기준 확정 | 조사·설계·OAuth 파일 준비 완료(M0 당시 앱 실인증 미검증) |
| M1 | 두 계정의 모델을 읽기 전용으로 조회 | 두 계정 인증·갱신·수집 성공 / 승인된 M1 범위 완료 |
| M2 | 검색·필터·모델 상세 대시보드 | 승인 범위 구현·실제 목록·독립 검증 완료 |
| M3 | 선택한 모델의 로컬 준비 상태 확인 | 미착수 |
| M4 | 음성 합성 모델 1종을 실제 실행 | 미착수 |
| M5 | 같은 계열 모델 2종의 새 실행 비교 | 미착수 |
| M6 | 재시작·오류 복구·사용 안내를 포함한 개인용 출시 | 미착수 |

첫 사용 가능한 버전은 **M2의 모델 조회 대시보드**, 첫 실제 추론 버전은 **M4**입니다. M4 전에는 실행 성공이나 측정값을 표시하지 않습니다.

## 문서

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
