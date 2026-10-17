# Windows 프로그램 형태 배포 검토

검토일: 2026-10-17 (Asia/Seoul) · M6 배포 선택 비교와 M7 구현 현황. 아래 세 옵션 표는 M6 시점 검토 이력이며 현재 M7 결과는 다음 절과 [M7 보고서](M7_REPORT.md)를 따른다. [M6 보고서](M6_REPORT.md) · [승인 범위](APPROVALS.md)

## M7 독립 앱 현황

후속 사용자 요청으로 0.7.1 후보에서 모델 원본 경로·실패 크기 표시를 보완하고 새 0.6B/1.7B A/B·재생·정상 native 저장을 검증했다. [새 A/B 보고서](M7_AB_REPORT.md)에 기록하며 공개 배포는 아래 v0.7.0을 유지한다. 0.7.1은 로컬 검증 후보로서 새 Release·태그 게시와 구분한다.

사용자가 Python 별도 설치 없는 독립 창을 명시 승인해 v0.7.0을 PyInstaller 6.22.3 onedir/windowed·pywebview 6.2.1 edgechromium으로 구현했다. 앱 Python과 python-build-standalone CPython 3.10.22 기반을 포함하며 추론 Torch 등 의존성은 앱에서 온라인으로 별도 준비한다. 현재 Windows의 WebView2 Runtime을 사용하고 없는 PC의 자동 전역 설치는 하지 않는다. [명령 없는 시작 안내](M7_INSTALL.md)를 따른다.

desktop5 ZIP은 58,405,026 bytes·SHA-256 `661d8bd5b58edfa4e2ba811338fce787fb1744149c98caacd7deac4489eae4d0`이다. 새 GUI 설치·독립 창·새 인증·CUDA·새 0.6B TTS·native 저장을 확인했으며 정상 종료/재시작의 상태·해시 보존도 확인했다. 재시작 후 독립 창 재생·두 계정 실제 갱신을 확인했으며 정상 [v0.7.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.7.0)와 [첨부 ZIP](https://github.com/castle923/Ai-manager/releases/download/v0.7.0/AiManager-0.7.0-windows.zip)의 uploaded 상태·크기·GitHub SHA-256 digest를 검증한 로컬 ZIP과 대조했다. 이번 새 TTS는 0.6B 한 모델 범위이며 1.7B 새 추론은 미검증이다. 모델과 자격 증명은 포함하지 않는다. 모든 PC 호환성이나 전면 native widget 재작성으로 해석하지 않는다. 큰 ZIP은 정상 Release asset으로 배포했고 Git blob에 추가하지 않았다. 태그는 소스 `066e62d286cb50fee1755bd0146c3ddbd3188526`에 고정하며 이후 main 문서 갱신과 구분한다.

## M6 시점 권고 방향(이력)

이번 M6는 **기존 Python이 필요한 사용자 범위 설치 스크립트·launcher + Edge UI**를 먼저 새 환경에서 검증한다. 그 다음 배포 편의 개선 후보는 **Python을 포함한 PyInstaller one-folder 실행 프로그램**, 독립 앱 창이 필요한 경우는 **WebView2 host**다. 형식 검토 결과를 후속 구현 의사결정에 사용하고, 현재 결과에 미구현 exe·독립 창 성공을 포함하지 않는다.

현재 앱은 Python 로컬 서비스가 API와 React 정적 UI를 제공한다. HTML 파일을 단독으로 열어 실행하는 구조가 아니다. 실행 아이콘으로 시작하는 프로그램과 UI를 표시하는 브라우저/창은 별개의 선택이다. WebView2 창에서도 현재 React UI를 표시할 수 있으며, Windows native widget으로 화면 전체를 다시 작성하는 것과는 다르다.

## M6 시점 세 가지 선택 비교(이력)

| 항목 | 이번 M6: wheel·설치 스크립트·launcher + Edge | 후속 후보: PyInstaller one-folder exe + Edge | 후속 후보: 독립 WebView2 창 |
|---|---|---|---|
| 사용자 실행 | 설치 스크립트로 사용자 범위 fresh venv/private home을 준비하고 launcher 실행, Edge 화면 열기 | 배포 폴더의 exe 실행, 로컬 서비스와 Edge 화면 시작 | 앱 실행으로 독립 Windows 창에서 UI 표시 |
| Python 요구 | 지원되는 기존 Python 설치 필요. 앱 venv는 따로 생성 | 앱 interpreter·의존성을 bundle하므로 앱 자체의 전역 Python 요구를 줄임. 추론 환경 준비 방식은 별도 설계 | host와 Python backend를 어떻게 bundle할지 별도 결정. WebView2가 Python backend를 대체하지 않음 |
| 추가 런타임 | Edge·Python 및 현재 고정 앱 의존성. 추론은 별도 환경 | Windows/아키텍처에 맞춘 Python bundle·Edge. 별도 추론 환경은 유지 | WebView2 Runtime과 선택 host 의존성. pywebview 사용 시 pythonnet/.NET 조건도 확인 |
| UI 표시 | 일반 Edge 탭 또는 별도 Edge 실행 옵션의 범위 | 실행 파일이어도 UI는 Edge에 표시 | 브라우저 주소창 없는 독립 host 창. 현재 웹 UI 기술을 재사용 가능 |
| 배포 용량 방향 | wheel/스크립트 자체는 상대적으로 작고 Python·앱 venv 설치 공간이 별도 필요 | interpreter와 앱 의존성을 포함해 배포 폴더가 커짐 | host가 추가되고 Runtime을 별도 설치/공유하거나 고정 버전을 함께 배포할지에 따라 증가 |
| 시작·종료 | launcher·포트·중복 기동·로컬 프로세스 종료를 새로 검증 | bundle 내 정적 파일 경로·worker 실행 경로·의존성 탐지·정상 종료를 다시 검증 | UI 창 닫기와 backend/worker 종료, 중복 인스턴스와 callback 동작을 새로 검증 |
| 인증·저장 | fresh 두 계정 OAuth와 Edge 재생/저장을 이번 설치본에서 검증 | bundle 경로에서 OAuth 브라우저 열기·loopback callback·Edge 다운로드를 재검증 | 시스템 브라우저 OAuth와 host 창의 callback, 쿠키/프로필 경계·다운로드/prompt·재생/포커스를 재검증 |
| 현재 결과 범위 | package-4-final·fresh 설치·격리 복구·CMD 시작·새 실제 E2E 확인. 범위와 제한은 M6 보고서에 연결 | 가능성·권고 검토만 수행. exe 산출물·실행 증거 없음 | 가능성 검토만 수행. 독립 창 산출물·실행 증거 없음 |

용량은 아직 측정하지 않았으므로 정확한 MB·다운로드 시간·시작 성능을 제시하지 않는다. 모델 가중치와 Torch/CUDA 추론 환경을 포함하면 앱 host보다 큰 용량 요인이 되므로 아래처럼 별도 관리한다.

## 모델·추론 환경과 개인 데이터 분리

세 형식 모두 앱 소스/정적 UI, 고정 앱 의존성, 추론 환경, 모델 자산, 개인 상태를 구분한다. PyInstaller가 앱 Python을 포함한다고 GPU 드라이버·Torch/CUDA·모델 가중치까지 자동 준비되는 것은 아니다. 추론 worker의 Python·의존성·모델 파일은 별도의 버전·해시·무결성 검사·준비 안내가 필요하다.

배포 파일에는 OAuth 개인 client JSON·토큰·DPAPI 상태·계정·Drive 인벤토리·개인 DB·입력/출력·원시 로그를 포함하지 않는다. fresh 설치는 사용자가 이번 프로젝트에 지정한 설정 원본을 명시 입력으로 적용하고, 이전 토큰/state/output/inventory를 자동 복사하지 않는다. 모델은 허용된 지정 자산만 사용하며 다운로드·무결성·환경·실행 상태를 분리한다.

프로그램 교체와 개인 자료 보관 경로를 분리한다. 업데이트 전 현재 버전·파일 해시·출처를 확인하고 새 버전을 별도 설치/검증한 뒤 전환한다. 기존 모델·원본·개인 DB·실패 기록은 보존하며 업데이트나 제거가 자동으로 개인 자료를 삭제하는 흐름을 만들지 않는다. 설치 경로를 바꾸는 것만으로 이전 venv·DPAPI 상태의 이동성이 검증됐다고 주장하지 않는다.

## 업데이트·서명·안전한 원본 유지

실제 출시 파일에는 버전·출처·SHA-256·포함 파일 목록·의존성 버전을 연결한다. one-folder는 포함된 exe와 DLL·정적 파일 전체를 한 버전 집합으로 검증하고, 의존성이 바뀌는 업데이트는 해당 집합을 새로 검증한다. one-file는 시작 시 임시 추출이 있으므로 편의만 보고 첫 검증 형식으로 정하지 않는다.

향후 exe/설치 프로그램 출시에서는 서명·게시자·업데이트 배포 경로를 함께 설계한다. 서명은 파일 출처 신뢰에 도움을 주지만 모든 SmartScreen 경고가 사라진다는 보장은 아니다. 이번 작업에서 코드 서명 구매·인증서 설정·SmartScreen/Defender/브라우저 보안 해제·경고 우회는 수행하지 않는다. 경고가 나타나면 원인·파일 출처·해시·현재 관리 정책을 확인하고 결과를 보고한다. 기존 M5 Chrome 차단을 새 배포 형식의 안전성 근거로 재사용하지 않는다.

## 실제 후속 구현을 선택할 때의 판단

이번 M6의 설치·복구·실계정·Edge E2E 결과로 현재 launcher가 사용자에게 충분한지 먼저 판단한다. Python 설치 없이 실행하는 편의가 우선이면 onedir bundle의 실제 Windows 빌드·새 환경 검증을 계획한다. 브라우저 탭 대신 독립 앱 창이 우선이면 WebView2 Runtime 배포·OAuth·파일 저장·접근성·종료 동작을 포함한 host 검증을 계획한다. 전체 native UI 재작성 여부는 별도 제품 선택이며 이 비교로 자동 결정하지 않는다.

## 공식 출처와 버전 확인

아래 자료는 2026-10-17에 확인한 기술 출처다. 설치하거나 실행한 의존성 버전의 증거가 아니며, 실제 선택 시 lock·빌드 로그·패키지 메타데이터로 별도 기록한다.

- [PyInstaller operating-mode, 문서 표시 버전 6.22.3](https://pyinstaller.org/en/stable/operating-mode.html): interpreter·의존성 bundle, OS/Python별 산출물, one-folder/one-file의 차이와 one-folder 우선 검증 근거.
- [pywebview 공식 Windows 설치 조건](https://pywebview.flowrl.com/guide/installation): Windows pythonnet/.NET 및 WebView2 Runtime 조건. 해당 페이지의 pywebview 패키지 버전은 표시되지 않아 설치 버전으로 고정하지 않았다.
- [Microsoft WebView2 Runtime 배포](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution): production host에는 Runtime이 필요하며 일반 Edge 브라우저 설치와 구분. Evergreen 공유/업데이트와 Fixed Version 배포 선택이 런타임 관리에 영향.
- [Microsoft SmartScreen 개발자 안내](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation): 서명·평판과 배포 파일 신뢰를 함께 고려하는 근거. 서명 구매 또는 경고 우회를 실행한 자료가 아니다.
