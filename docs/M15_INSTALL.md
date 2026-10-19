# Ai-manager 0.15.0 Windows 독립 앱 설치와 복구

Python을 따로 설치하지 않는 onedir 앱이며 UI는 Microsoft Edge WebView2 독립 창이다. Microsoft Edge WebView2 Runtime이 필요하다. 모델과 AI 모델 실행용 CUDA 패키지, OAuth client·allowlist·로그인 정보는 ZIP에 포함하지 않는다. 최초 다운로드/실행 환경 준비는 별도 명시 범위를 따른다.

1. 새 ZIP과 공개 SHA-256을 대조하고 기존 앱 폴더와 다른 새 폴더에 압축을 푼다. `DESKTOP-MANIFEST.json`과 `SOURCE-PROVENANCE.json`을 함께 보존한다.
2. `AiManager.exe`를 실행한다. 처음 시작 화면에서 이번 프로젝트에 지정한 OAuth client JSON·allowlist JSON을 선택한다. 새 작업실을 사용하며 기존 home/tokens/state/output을 복사하지 않는다. 시스템 브라우저의 Google 로그인·동의는 사용자가 직접 수행한다.
3. 선택 설치는 사용자 폴더 아래 새 `AiManager-0.15.0`을 만들며 기존 대상은 덮어쓰지 않는다. 관리자 권한·OS 전역 PATH·보안·브라우저 설정 변경은 필요하지 않다.
4. 자동 검수 화면에서 명시 로컬 모델 root와 허용한 기존 runtime Python/lock JSON을 입력한다. 원본 관찰·새 plan·코드/원본/환경·원래 시간 및 누적 예산을 확인하고 명시 승인한다. 새 plan은 case당 최대 두 attempt의 한도를 처음부터 포함한다.
5. 앱이 중단됐다면 같은 작업실로 다시 실행한다. 기존 검수 이력을 열고 `이전 실행 소유권·중단 상태 확인`을 누른다. 살아 있는 소유 작업·불명확한 Job 관찰이면 재개하지 않는다. 소유 종료가 확인된 중단 상태에서 `부분 재개 명시 승인` 후 `승인한 부분 재개 시작`으로 같은 batch의 미완료 case만 진행한다.
6. 완료 case와 receipt는 그대로 보존되고 미완료 시도에는 새 attempt/run ID가 부여된다. 원래 만료 시각·누적 소비는 유지된다. source/runtime/code 변경, 완료 receipt/input/output 변경, 원장 불일치·예산 소진은 새 계획을 요구한다. 옛 성공을 새 검수 성공으로 계산하지 않는다.

프로그램 종료 전에 진행 중 검수를 취소하고 소유 작업 정리를 기다리는 것이 정상 흐름이다. 새 경로 설치·DB 복구 실험은 원본 home을 보존한 격리 대상에서 수행한다. 새 PC·모든 모델·전면 접근성·장시간 스트레스·품질 우열까지 보장하는 패키지는 아니다. 이번 실제 완료/미검증 범위는 `M15_REPORT.md`를 따른다.

지원 진단: `AiManager.exe --package-self-check <새 절대경로 JSON>`은 창을 열기 전에 해당 frozen package의 전체 파일·동봉 소스와 실제 import code·code SHA를 검사한다. 진단 결과는 로컬 경로를 포함할 수 있으므로 공개 게시하지 않는다. `--home <새 절대경로>`는 별도 작업실을 선택하며 기존 작업실을 옮기거나 삭제하는 옵션이 아니다.
