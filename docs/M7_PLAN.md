# M7 — Python 별도 설치 없는 Windows 독립 앱

기준일: 2026-10-17 · 사용자 승인 범위 · desktop5 필수 실제 흐름·v0.7.0 출시 완료(확인한 로컬·0.6B 범위)

사용자는 별도 Python 설치 없이 실행하는 Windows 프로그램과 독립 창, 새 설치·인증·TTS·정상 저장 검증 및 저장소 반영을 승인했다. 출시 버전은 0.7.0이다. [승인 기록](APPROVALS.md) · [진행 보고서](M7_REPORT.md)

## 배포와 실행 방식

PyInstaller `onedir`·`windowed` 패키지에 앱 Python을 포함하고 pywebview `edgechromium`으로 독립 창을 제공하는 방향이다. 추론에는 python-build-standalone CPython 3.10.22 `install_only` 배포본을 함께 제공하고 격리된 런타임을 준비한다. 실제 버전·출처·해시·라이선스는 최종 빌드 기록과 연결한다. 별도 Python 불필요 조건과 시스템 WebView2 Runtime 전제를 구분하며, WebView2가 없는 PC는 필요한 조건을 안내하고 자동 전역 설치하지 않는다.

첫 실행에서 지정 OAuth client JSON·allowlist 원본을 선택하고 런타임 준비 상태·오류를 확인한다. Google 로그인·동의는 사용자가 새로 수행하며 이때 시스템 브라우저 사용은 허용한다. 앱 UI와 저장은 독립 창 및 정상 native SaveDialog/host API를 사용한다. 모델 가중치·개인 인증 자료는 배포물에 넣지 않는다.

## 완료 게이트

아래 표는 v0.7.0 출시 게이트 이력이다. 이후 승인된 0.7.1 후보의 새 두 모델 실행·재생·native 저장 검증은 [새 A/B 보고서](M7_AB_REPORT.md)를 따른다. 후속 검증이 기존 태그·ZIP을 변경하지 않으며 0.7.1 공개 Release는 게시하지 않았다.

| 필수 항목 | 새 M7 검증 근거 | 상태 |
|---|---|---|
| Python 포함 실행 | 호스트 Python과 PATH/PYTHONHOME/PYTHONPATH를 분리한 앱·추론 실행, 런타임 버전·해시 | desktop5 번들 Python 격리 실행·새 환경·CUDA·0.6B 실제 TTS 확인 |
| 설치·독립 창 | user-scope 새 대상, 버전·해시·no-overwrite·reparse 경계, 실제 독립 창, WebView2 필요 조건 안내 | desktop5 새 GUI 설치·전량 4,285개 집합/해시 확인 |
| 설정·실계정 | 지정 원본 선택, fresh home의 두 계정 사용자 OAuth·갱신·읽기 전용 수집 | desktop4 A/B 새 OAuth·수집, desktop5 재시작 후 A/B 실제 갱신 확인 |
| 실제 모델 실행 | 지정 모델의 새 준비 해시, 새 입력·run/output, 실제 GPU TTS·WAV 무결성·앱 재생 | 0.6B 새 준비 13개·새 실제 TTS·재생 확인; 1.7B 새 M7 추론 미검증 |
| 정상 파일 저장 | native SaveDialog 완료·취소, 기존 파일 보존, 실제 저장 바이트·해시와 출력 일치 | 실제 사용자 저장본 해시 일치·취소 지정 경로 무저장 확인 |
| 종료·재시작 | 앱 종료 시 소유 backend/worker 정리, 중복 실행·중단 상태·재시작 일관성 | desktop5 동시 종료 반례 해결·소유 11프로세스 종료·같은 설치/home 재시작 기록/해시 보존 확인 |
| UI·오류 | 독립 창의 설정·런타임·인증·실행/취소·저장·재시작 상태와 재생 확인 | 필수 실제 흐름 확인; 전면 접근성·모든 창 크기 검증은 미수행 |
| 배포·공개 | third-party notice, 개인 자료 제외, 최종 크기·해시·출처와 고정 소스 커밋 연결 | 소스 고정 커밋·태그·공개 Release uploaded ZIP 크기/digest 확인 |

같은 프로젝트 코드와 지정 모델·config/tokenizer·OAuth/allowlist 원본은 사용할 수 있다. M7 고유 stage/home/runtime/output에 출처와 새 증거를 보존한다. M6의 토큰·state·인벤토리·출력·WAV·검증 기록은 복사하거나 M7 성공 근거로 대체하지 않는다. 기존 M6 서버·개인 자료·배포·태그를 보존한다.

소스·문서 31개를 고정 커밋으로 반영하고 비변경 54개 blob·삭제 0을 확인했다. Python 포함 ZIP은 정상 [v0.7.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.7.0) asset으로 첨부했으며 58,405,026 bytes·GitHub SHA-256 digest를 검증한 로컬 ZIP과 대조했다. ZIP과 생성 static은 Git tree에 추가하지 않았다. 태그 대상은 `066e62d286cb50fee1755bd0146c3ddbd3188526`이며 이후 main 문서 갱신과 구분한다.

전역 PATH·보안·정책·관리자 설정·브라우저 download behavior는 변경하지 않는다. 새 모델·원격 GPU·Drive 쓰기·공개 서비스·서명 구매는 포함하지 않는다. 전면 접근성 인증·모든 PC 호환성·청취 품질 우열은 실제 검증 범위와 구분한다.
