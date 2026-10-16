# Ai-manager

두 Google Drive 계정에 보관한 AI 모델을 한곳에서 찾고, 필요한 파일을 확인하고, 새 테스트 결과를 비교하는 개인용 대시보드입니다.

> **현재 상태: M0 조사·설계·OAuth 파일 준비 완료 / 앱 실인증 미검증(전체 PASS 아님).** 이번 M0에서 Codex를 통한 초기 Drive 범위 조회와 PC 감사를 수행했습니다. **M1 로컬 구현·자동/독립 합성 검증은 완료됐습니다.** 두 계정 연결·읽기 전용 목록의 실계정 검증은 사용자 참여가 필요합니다. 계정 A 로그인 시도는 시간 초과, B는 미시작이며 실제 인증·Drive 조회·갱신 성공은 미검증입니다. 모델 실행·측정은 후속 단계입니다.

## 무엇을 할 수 있게 만드나요?

1. **모델 찾기:** 용도·저장 위치·계열로 검색하고 필터링합니다.
2. **준비 상태 확인:** 파일 발견, 구성 충족, 무결성 확인, 실제 실행 성공을 구분합니다.
3. **새 테스트 실행:** 선택한 모델에 입력을 넣고 진행·취소·실패 원인을 확인합니다.
4. **결과 비교:** 같은 조건에서 새로 실행한 결과와 처리 시간·메모리를 나란히 봅니다.

## M1 로컬 실행

현재 M1은 Windows의 Python 3.10 이상에서 사용하는 로컬 앱입니다. `pyproject.toml`의 직접 런타임 의존성은 `requests==2.32.5`, 빌드 의존성은 `setuptools>=68`입니다. 아래 명령은 저장소 루트의 PowerShell에서 실행합니다. 기존 환경 대신 새 `.venv`를 만들며 활성화 스크립트 없이 실행할 수 있습니다.

```powershell
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

`serve`는 임의 포트의 `127.0.0.1`에서 M1 연결·수집 화면을 엽니다. 해당 화면에서도 연결·갱신·스캔·해제와 작업 취소를 요청할 수 있습니다. CLI 연결 해제는 `disconnect A` 또는 `disconnect B`입니다. 토큰은 Windows 사용자 DPAPI로 암호화하고 설정·개인 인벤토리는 저장소 밖 앱 전용 비공개 위치에 보관합니다. 출력의 `credential_saved`는 저장된 인증정보 존재 표시이며 현재 권한·조회 성공과 별도로 확인해야 합니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`requirements.lock`에는 이번 실행에 설치한 직접·전이 런타임 의존성 버전을 기록합니다. 테스트 결과와 실계정 진행 상황은 [M1 보고서](docs/M1_REPORT.md)에 구분해 기록합니다. 이 안내만으로 실계정 E2E나 M1 완료를 선언하지 않습니다.

## 단계별 기능

| 단계 | 사용자에게 생기는 기능 | 상태 |
|---|---|---|
| M0 | 범위·출처·검증 기준 확정 | 조사·설계·OAuth 파일 준비 완료 / 앱 실인증 미검증(전체 PASS 아님) |
| M1 | 두 계정의 모델을 읽기 전용으로 조회 | 로컬 구현·합성 검증 완료 / 실계정 검증 대기 |
| M2 | 검색·필터·모델 상세 대시보드 | 미착수 |
| M3 | 선택한 모델의 로컬 준비 상태 확인 | 미착수 |
| M4 | 음성 합성 모델 1종을 실제 실행 | 미착수 |
| M5 | 같은 계열 모델 2종의 새 실행 비교 | 미착수 |
| M6 | 재시작·오류 복구·사용 안내를 포함한 개인용 출시 | 미착수 |

첫 사용 가능한 버전은 **M2의 모델 조회 대시보드**, 첫 실제 추론 버전은 **M4**입니다. M4 전에는 실행 성공이나 측정값을 표시하지 않습니다.

## 문서

- [M1 진행 현황과 검증 대기 항목](docs/M1_REPORT.md)
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
