# 실행 전 준비 안내

현재 판정: **조사·설계 완료 / 앱 OAuth 준비 대기(전체 PASS 아님)**. 지금 필요한 준비는 Google Drive 앱 인증용 설정이다. 새 Google 계정은 필요 없다. 앱 구현과 설치는 해당 단계 승인 후 진행한다.

## 지금 준비할 것: Google OAuth client

1. [Google Cloud 프로젝트 만들기](https://developers.google.com/workspace/guides/create-project) 안내에 따라 앱 전용 프로젝트 하나를 준비한다. 이름은 `Ai-manager`로 둘 수 있다. 적합한 기존 프로젝트도 사용할 수 있으나 다른 앱과 분리한 프로젝트를 권장한다.
2. 해당 프로젝트의 **API 및 서비스 → 라이브러리**에서 **Google Drive API**를 사용 설정한다.
3. **Google Auth Platform → Branding**에서 앱 이름과 지원 이메일·개발자 연락처를 설정한다. 화면 구성이 다른 경우 [공식 동의 화면 안내](https://developers.google.com/workspace/guides/configure-oauth-consent)를 따른다.
4. **Audience**에서 개인용 **External / Testing**으로 설정하고, 연결할 두 Google 계정을 test user에 등록한다. 두 계정 각각의 로그인·동의가 필요하다.
5. **Data Access**에 `https://www.googleapis.com/auth/drive.readonly`를 추가한다. 이 권한은 계정 전체 읽기 권한이다. 지정 폴더만 탐색하는 제한은 앱에서 구현한다.
6. **Clients → Create client → Desktop app**으로 OAuth client 하나를 만든다. 웹 애플리케이션 유형을 선택하지 않는다. [공식 자격 증명 생성 안내](https://developers.google.com/workspace/guides/create-credentials)
7. client JSON을 다운로드하여 **저장소와 Git 추적 범위 밖의 개인 보안 위치**에 보관한다. 두 계정용으로 client를 두 개 만들 필요는 없다.
8. 준비가 끝나면 JSON이 있는 **로컬 경로만** 작업 채팅에 알려준다. JSON 내용, client secret, token, 인증 코드를 채팅·공개 저장소에 붙여넣지 않는다. 실제 경로도 공개 문서에 기록하지 않는다.

현재 앱 client 생성·설정 여부는 미확인이다. 이 절차는 준비 안내이며 이미 설정을 완료했다는 보고가 아니다. 지금 브라우저에서 앱 로그인을 미리 수행할 필요는 없다. M1 앱 인증 구현 후 각 계정의 동의와 갱신을 확인한다. External / Testing에서는 refresh token 만료에 따른 재로그인이 필요할 수 있다. [공식 만료 조건](https://developers.google.com/identity/protocols/oauth2#expiration)

## 단계별 준비

| 단계 | 준비·실행할 항목 | 완료 판단 |
|---|---|---|
| M0 현재 | OAuth client 설정, 초기 allowlist와 저장 위치 검토 | 조사·설계 완료, 인증 준비 대기 |
| M1 승인 후 | 신규 앱/API 환경, 두 계정 로그인, 보안 토큰 저장, 읽기 전용 스캔 | 실제 계정별 조회·갱신·범위 차단·부분 실패 검증 |
| M2 | React + TypeScript 조회 화면 | 실제 새 인벤토리와 상태 구분 검증 |
| M3 | 새 Python 3.12 추론 환경 권장, 검증한 PyTorch/CUDA 조합, 선택 모델 다운로드·해시 검증 | 설치·장치·파일·쓰기 경로를 실제 검증한 준비 상태 |
| M4 | 이번 실행의 새 한국어 문장, Korean / Sohee / batch 1 | 새 WAV 생성·디코딩 검사·UI 재생 |
| M5 이후 | 승인된 두 번째 모델과 새 비교 입력 | 각각 새 실행으로 비교 |

PC에는 기본 Python 3.10.11과 RTX 3070 8 GiB가 확인됐지만 실제 CUDA 추론 적합성은 미검증이다. Python 3.12의 시스템 전체 부재를 단정하지 않는다. 신규 환경과 패키지 설치는 M3에서 검증하며, 기본 환경이나 기존 venv를 수정·재활용하지 않는다. 세부 근거는 [M0 보고서](M0_REPORT.md)에 있다.

## 지금 하지 않아도 되는 준비

- 새 Google 계정 만들기, API key 발급, 서비스 계정 만들기.
- 모델 전체 다운로드, 기존 모델·결과 폴더 정리 또는 이동.
- Python·CUDA·FlashAttention·WSL 설치 및 기존 환경 변경.
- 원격 GPU 생성, 유료 인프라 결제, 공개 배포.
- 과거 코드·시안·음성·로그·캐시를 새 프로젝트에 복사.

코드 저장소와 실제 모델·결과·DB는 분리한다. 공개 문서는 `<data_root>` 별칭을 사용하며 실제 제안 위치는 개인 기록에 보관했다. 제안 경로의 생성·쓰기 검증은 아직 하지 않았다. 다음 단계 시작은 OAuth 준비와 M1 범위 승인 뒤에 결정한다.
