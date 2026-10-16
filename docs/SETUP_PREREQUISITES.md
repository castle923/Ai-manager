# 실행 전 준비 안내

현재 상태: **M1 두 계정 실인증·강제 갱신·지정 범위 수집 성공 / 승인된 M1 범위 완료**. 사용자가 두 계정 로그인·동의를 완료했고 새 앱에서 실제 읽기 전용 scope·계정 일치·DPAPI 저장을 확인했다. M0 당시 정적 준비 기록과 이후 실검증을 구분한다. [실제 집계와 확인 범위](M1_REPORT.md)

## OAuth 준비 현황

| 항목 | 현재 근거와 상태 |
|---|---|
| 전용 Cloud 프로젝트·Drive API | 사용자 완료 보고; 콘솔 직접 확인 미수행 |
| External / Testing·계정 A/B test users·`drive.readonly` | Cloud 설정은 사용자 보고; M1에서 두 계정 실제 tokeninfo scope 확인 |
| Desktop OAuth client·저장소 외부 JSON 다운로드 | 사용자 완료 보고 |
| 지정 JSON | 별도 검사 에이전트의 읽기 전용 검사에서 존재·파싱·`installed`·필수 필드·프로젝트 일치·Google endpoint·loopback redirects 통과 |
| 앱 로그인·동의·토큰 발급/갱신·Drive API | M1에서 두 계정 실인증·DPAPI 저장·강제 갱신·지정 범위 수집 성공 |

검사는 파일 복사·수정·외부 전송·로그인 없이 수행했다. 실제 경로·프로젝트 ID·client 값·JSON 원문은 이 공개 문서에 기록하지 않는다.

## Google OAuth client 설정 안내

아래는 설정 재확인용 안내다. 사용자 보고와 로컬 JSON 검사로 완료된 준비를 반복 수행하라는 뜻은 아니다.

1. [Google Cloud 프로젝트 만들기](https://developers.google.com/workspace/guides/create-project) 안내에 따라 앱 전용 프로젝트 하나를 준비한다. 이름은 `Ai-manager`로 둘 수 있다. 적합한 기존 프로젝트도 사용할 수 있으나 다른 앱과 분리한 프로젝트를 권장한다.
2. 해당 프로젝트의 **API 및 서비스 → 라이브러리**에서 **Google Drive API**를 사용 설정한다.
3. **Google Auth Platform → Branding**에서 앱 이름과 지원 이메일·개발자 연락처를 설정한다. 화면 구성이 다른 경우 [공식 동의 화면 안내](https://developers.google.com/workspace/guides/configure-oauth-consent)를 따른다.
4. **Audience**에서 개인용 **External / Testing**으로 설정하고, 연결할 두 Google 계정을 test user에 등록한다. 두 계정 각각의 로그인·동의가 필요하다.
5. **Data Access**에 `https://www.googleapis.com/auth/drive.readonly`를 추가한다. 이 권한은 계정 전체 읽기 권한이다. 지정 폴더만 탐색하는 제한은 앱에서 구현한다.
6. **Clients → Create client → Desktop app**으로 OAuth client 하나를 만든다. 웹 애플리케이션 유형을 선택하지 않는다. [공식 자격 증명 생성 안내](https://developers.google.com/workspace/guides/create-credentials)
7. client JSON을 다운로드하여 **저장소와 Git 추적 범위 밖의 개인 보안 위치**에 보관한다. 두 계정용으로 client를 두 개 만들 필요는 없다.
8. 준비가 끝나면 JSON이 있는 **로컬 경로만** 작업 채팅에 알려준다. JSON 내용, client secret, token, 인증 코드를 채팅·공개 저장소에 붙여넣지 않는다. 실제 경로도 공개 문서에 기록하지 않는다.

Google 콘솔 설정은 사용자 보고, JSON 형식은 로컬 구조 검사, 이후 앱 인증·실제 scope·조회·강제 갱신은 M1 실검증으로 구분한다. 두 계정은 현재 인증·수집을 완료했으므로 동일 준비를 반복할 필요는 없다. External / Testing에서는 refresh token 만료에 따른 재로그인이 필요할 수 있다. [공식 만료 조건](https://developers.google.com/identity/protocols/oauth2#expiration)

## 단계별 준비

| 단계 | 준비·실행할 항목 | 완료 판단 |
|---|---|---|
| M0 당시 | 조사·설계, OAuth JSON 로컬 구조 검사 | 조사·설계·파일 준비 완료; 앱 실인증 미검증 |
| M1 승인 범위 완료 | 신규 앱/API 환경, 두 계정 로그인, 보안 토큰 저장, 읽기 전용 스캔 | 실제 계정별 조회·갱신·범위 차단·부분 실패 검증 |
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

코드 저장소와 실제 모델·결과·DB는 분리한다. 공개 문서는 `<data_root>` 별칭을 사용하며 실제 제안 위치는 개인 기록에 보관했다. 제안 경로의 생성·쓰기 검증은 아직 하지 않았다. 기존 파일을 자동 이동하거나 이전 결과를 입력으로 가져오지 않는다. M1 구현·테스트·수정·게시에는 재승인이 필요 없다. 후속 범위와 사용자 직접행위는 [승인 기록](APPROVALS.md)을 따른다.
