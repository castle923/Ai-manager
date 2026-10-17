# M7 진행 보고서

기준일: 2026-10-17 · 상태: 승인된 M7 구현·실검증·v0.7.0 출시 완료(확인한 Windows 로컬·0.6B 범위)

v0.7.0은 Python을 포함한 Windows 독립 앱이다. PyInstaller onedir/windowed·pywebview edgechromium을 사용하며 앱과 추론에 별도 전역 Python 설치가 필요하지 않도록 구성했다. desktop5 새 설치·독립 창·별도 런타임과 CUDA, 새 0.6B TTS·재생·native 저장·취소·종료/재시작을 확인했다. 재시작 후 성공 음성 재생·두 계정 갱신까지 확인했고 소스 게시·태그·정상 Release ZIP 첨부를 검증했다. [v0.7.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.7.0) · [계획과 완료 게이트](M7_PLAN.md) · [시작 안내](M7_INSTALL.md)

| 구분 | 현재 기록 |
|---|---|
| 승인 | 독립 앱 구현·공개 의존성/런타임 준비·새 설치·사용자 인증·실제 TTS·정상 저장·비식별 게시 |
| 사용할 기존 입력 | 같은 프로젝트 코드, 지정 모델과 직접 필요한 config/tokenizer, 지정 OAuth client/allowlist 원본 |
| 새 산출물 | M7 전용 stage/home/runtime과 새 빌드·설치·인증·수집·준비·TTS·저장 검증 기록 |
| 실제 설치·인증 | desktop5 새 폴더 GUI 설치 후 4,285개 payload 전체 집합·해시 일치. desktop4에서 사용자 직접 fresh OAuth A/B 및 refresh_verified를 확인한 같은 M7 home의 연속 재개이며 인증 복사 없음 |
| 새 목록·모델 준비 | 새 수집 A 515개/B 113개 파일·오류 0. 파일 수는 모델 수가 아님. 지정 0.6B 폴더 선택 후 새 준비 13개 파일·무결성 확인 |
| 런타임 준비 | desktop5 새 환경 ID·새 venv ready와 실제 CUDA/RTX 3070 확인. System32-only PATH·Python 환경변수 격리 시 실제 Python DLL과 base prefix가 설치본 번들 기반에 연결됨 |
| 실제 TTS·저장 | 새 한국어 입력의 0.6B cold TTS·끝까지 앱 재생·정상 native SaveDialog 저장 후 원본/저장본 바이트·SHA 일치 확인 |
| 취소·종료 | SaveDialog 취소의 지정 관측 경로 무저장, 별도 새 추론 취소 및 실행 중 창 종료의 cancelled/output null/WAV 없음 확인. 소유 프로세스 11개·listener 종료 확인 |
| 재시작 복구 | 같은 설치/home의 성공 1개·취소 2개 기록, active 없음·같은 런타임 ID ready·재설치 없음, 지정 데이터/출력 해시 보존 및 성공 WAV 끝까지 재생, A/B 각각 실제 refresh_verified 확인 |
| 공개 배포 게이트 | 소스·문서 31개 고정 커밋 바이트 일치·비변경 54개 blob 보존·삭제 0, v0.7.0 태그 대상·공개 Release·uploaded ZIP 크기/digest 일치 확인 |
| 보존 | M6 서버·인증·DB·출력·v0.6.0 Release와 태그 보존; 과거 성공을 이번 PASS로 사용하지 않음 |
| 배포 | desktop5 ZIP 58,405,026 bytes·SHA-256 `661d8bd5b58edfa4e2ba811338fce787fb1744149c98caacd7deac4489eae4d0`와 공개 Release asset metadata 일치 |

모델 가중치·자격 증명·개인 로그·실제 경로·Drive ID는 공개 배포물과 저장소에서 제외한다. 두 계정 Google 로그인·동의는 사용자 직접행위다. WebView2 Runtime의 시스템 전제와 별도 Python 설치 불필요 조건을 구분하고, 없는 PC에서 자동 전역 설치하지 않는다.

desktop5 독립 검증에서 payload 4,285개·ZIP 4,286 entries·CPython 3.10.22 파일 3,932개의 집합/해시와 source manifest 27개의 현재 코드·패키지 데이터 일치를 확인했다. 제한 PATH·Python 환경변수 격리 후 번들 Python 실행·기본 모듈 import를 확인했다. 이 격리검사만으로 Python 미설치 별도 PC의 실행을 검증한 것은 아니다. 실제 GPU 검증은 아래 새 실행으로 별도 수행했다. desktop5의 새 159개 테스트 통과(20.116초)와 npm build 통과를 확인했다.

desktop4의 환경 점검 요청 계약 오류와 설정 서버 동시 종료 경쟁 조건을 desktop5에서 수정했다. 새 독립 합성 검증에서 동시 종료 shutdown 1회·server close 1회·예외 0, 런타임 ID 분리 5개 경계, API 계약 4개 테스트를 확인했다. desktop4 환경은 보존하며 같은 M7 auth home을 토큰 복사 없이 이어 사용한다.

## 새 실제 실행과 저장

61자 새 한국어 입력의 SHA-256은 `d36631378a7195981bbe14e5d36f0aac958027d22536845ede58e0088fce3a2e`다. 원문은 공개하지 않는다. 새 런타임·현재 설치 코드 11개 해시와 모델 13개 원본/준비본/고정 manifest를 연결해 실제 실행을 독립 확인했다. 모델 로딩 2.688초·추론 32.968초·PyTorch peak allocated 2,482,457,600 bytes이며 전체 VRAM 사용량이나 반복 성능 측정은 아니다.

새 WAV는 491,564 bytes·PCM16 mono 24 kHz·10.24초, EOS true·clipped sample 0이며 SHA-256은 `b8e396b4ad823ceeefc049f3e9308531a4d1755749ace216adf114cb3f8aa97c`다. 앱에서 끝까지 재생하고 사용자가 정상 SaveDialog로 지정한 저장본의 바이트·형식·해시가 일치했다. 실제 선택 위치는 비공개에 보존했고 저장 WAV를 모델 입력에 포함하지 않았다. 파일 이동·삭제는 하지 않았다. SaveDialog 취소는 지정 디렉터리·예정 대상·기본 대상의 관측 범위에서 무저장을 확인했으며 전체 파일 시스템 무쓰기로 확대하지 않는다.

별도 새 추론의 취소와 다른 실행 중 앱 창 종료를 실제 확인했다. 종료 후 소유 프로세스 11개·listener가 사라졌고 중단 run은 cancelled·output null·해당 출력 디렉터리 WAV 0이었다. 같은 설치와 home으로 재시작한 뒤 성공 1개·취소 2개 기록과 active 없음·동일 런타임 ready를 재조회했다. 설정·DB·모델 준비·현재/이전 런타임의 지정 10개 해시와 성공 WAV/실제 저장본은 종료 전과 일치했다. DB는 새 M7 수집 2건·파일 628개를 유지했다. 재시작한 독립 창에서 성공 음성을 끝까지 재생하고 A/B 각각 실제 갱신의 refresh_verified를 확인했다. 같은 런타임 ID를 재설치 없이 사용했다. 정상 종료/재시작 확인이며 실제 GPU crash 복구를 뜻하지 않는다.

## 확인 범위와 남은 제한

[배포 ZIP](https://github.com/castle923/Ai-manager/releases/download/v0.7.0/AiManager-0.7.0-windows.zip)은 정상 Release asset으로 첨부됐다. GitHub API에서 2026-10-17T03:46:56Z 공개·draft false·prerelease false, asset 이름·uploaded 상태·58,405,026 bytes·SHA-256 digest를 확인했다. 추가 ZIP 다운로드는 하지 않았으며 이미 검증한 로컬 ZIP 해시와 API digest를 대조했다. v0.7.0 태그는 소스 커밋 `066e62d286cb50fee1755bd0146c3ddbd3188526`에 고정한다. 후속 main 문서 보완은 릴리스 코드·ZIP 변경이 아니며 기존 v0.6.0 태그/Release를 보존한다.

이번 필수 실제 TTS는 지정 0.6B 한 모델·새 입력 1건이다. 1.7B의 새 M7 추론·A/B 비교는 수행하지 않았으며 과거 결과로 대체하지 않는다. 청취 품질·모든 입력/PC·실제 GPU crash·장시간 stress·전면 접근성 인증은 미검증이다. native 재생 종료는 청취 품질 판정이 아니다. 번들 `M7_INSTALL.md`는 desktop5 빌드 시점 안내로 동결했고 후속 웹 보고서 갱신은 ZIP 변경을 뜻하지 않는다.
