# M6 개인용 로컬 출시 검증 보고서

작성일: 2026-10-17 (Asia/Seoul) · 판정: 확인한 Windows 로컬 환경·정상 지원 Edge·두 지정 모델의 M6 출시 준비 gate PASS. 최종 package-4-final·설치·격리 복구·새 실제 Edge/GPU·핵심 UI 표본을 검증했다. 공개 저장소 반영과 v0.6.0 태그/Release 식별은 최종 게시 단계이며 실제 완료 여부를 별도로 확인한다. 모든 환경·장애·접근성 인증의 보장이 아니다.

## 승인 범위와 보존

사용자는 최신 배포 패키지, 신규 환경 설치·인증/DB/작업 복구 검증, Edge 실제 사용, 문서·비식별 저장소 반영을 명시 승인했다. 모든 실무는 GPT-6.1 sol / medium 서브에이전트가 수행하고 부모는 조정·검토한다. 같은 프로젝트 코드·지정 모델과 공개 라이브러리는 출처·현재 해시를 기록해 사용할 수 있다. 다른 프로젝트 결과물은 가져오지 않는다.

M6 고유 실행별 경로와 입력/출력 출처를 새로 만든다. M5 보고서는 계획·알려진 제한의 참고 이력이며 현재 테스트·생성·다운로드·UI 성공의 증거가 아니다. 기존 개인 인증·DB·모델·결과를 보존하고 복구 실험은 격리된 검증 대상에서 수행한다. 이번 프로젝트의 지정 OAuth client JSON·allowlist 원본은 입력 설정 자산으로 fresh home에 적용할 수 있으나 토큰·state·output·inventory를 복사하지 않는다. 두 계정의 실제 fresh 인증은 사용자 로그인·동의가 필요하다. 새 개인 로그·계정·Drive ID·원시 경로·자격 증명은 공개하지 않는다.

작업공간 커스텀·Drive 쓰기·공개 서비스·서명 구매·새 모델 계열·원격 GPU·전역 보안 설정 변경은 범위에 없다. OAuth 로그인·동의는 사용자 직접행위다. 실제 필요한 사용자 참여는 이미 승인된 인증 검증을 위한 참여이며 새 범위 승인과 구분한다. [승인 기록](APPROVALS.md)

## 원계획의 완료 gate와 새 증거

근거는 [마일스톤 M6](MILESTONES.md)·[품질 gate M6 및 공통 기준](QUALITY_GATES.md)·[제품 범위](PLAN.md)다. 개인 PC 로컬 출시이며 공개 서비스 배포가 아니다. 초기 통과 기준을 문서에 고정하고 새 실행의 PASS·실패·미확인을 분리한다.

| 필수 gate | 새 M6 검증의 수용 기준 | 현재 상태 |
|---|---|---|
| 최신 배포 패키지 | 현재 소스·UI·두 모델 manifest·lock과 배포 파일의 버전·해시·포함 파일 집합을 대조. 개인 데이터 제외 | PASS: package-4-final source 22개·installed package 21개·문서/스크립트/lock 7개·ZIP/release 10개·HTTP HTML/CSS/JS 3개 바이트 일치 |
| 신규 환경 설치·시작 | 기존 개발 환경에 의존하지 않는 격리 환경에서 안내대로 설치·시작하고 실제 패키지 코드/정적 UI를 로드 | PASS 범위: fresh venv site-packages 0.6.0·pip check·한글/공백 설치 경로 CMD 실제 시작·현재 Edge 대표 실제 흐름 확인 |
| 인증 회복 | 연결/갱신/해제·만료/권한 오류를 실제/합성 범위를 구분해 새로 검증. 비밀 비노출과 기존 인증 보존 | 새 M6 사용자 fresh A/B OAuth·실제 refresh_verified·새 수집 성공. 최종 설치로 같은 M6 home 연결 보존 확인. 만료/미연결/비밀 비노출은 신규 합성 검증과 구분 |
| 작업 중단·재시작 | 새 작업의 대기/실행·취소·프로세스 중단 후 재시작 상태와 소유권·고아 프로세스/잘못된 성공 상태를 확인 | 최종 설치본의 실제 Windows controller+새 합성 worker 중단/Job Object 종료·대기/실행 interrupted·audio 없음·새 소유권 PASS. 실제 GPU crash 시험 아님 |
| DB·기록 복구 | 정상 snapshot을 새 대상에 복원하고 손상/잠금/재시작 반례를 격리 검증. 원본 보존·상태 일관성 확인 | 최종 설치본 독립 8개 경계 PASS·backup deadline/정확 canonical schema 확인. 손상 원본 수리 기능이 아님 |
| 대표 실제 Edge E2E | 현재 설치본에서 실제 조회·선정 준비·새 실행·비교·재생·저장 등 대표 사용자 흐름을 새로 연결. 실제 원본/새 생성과 기록을 구분 | PASS: 새 M6 실제 A/B GPU 출력·재생·각 1회 저장·파일/설치 코드/모델 출처 독립 검증. 중립 평가 재조회·조회/상세 UI, CSS/package 교체 후 핵심 UI 재확인 |
| 전체 UI·접근성 목표 회귀 | 상태별 화면·한국어·긴 이름·키보드/포커스·대비/reduced motion·768/1280/1440/1920을 현재 UI로 확인 | 4개 계획 폭 가로 넘침 0·상세 Escape/포커스 복귀·Tab 3px·현재 reduce 핵심 표본 확인. 작은 텍스트 대비 3개를 보완해 최종 Edge 표본 4.5:1 이상 확인. 전면 WCAG/스크린리더 인증 아님 |
| 설치/시작/복구 안내·회귀·버전 태그 | 검증된 배포 형태의 재현 가능한 안내와 잔여 제한, 적절한 회귀·독립 검토·소스 반영·버전 식별 | INSTALL/RECOVERY 배포 포함·package-3 설치본 140개/19.797초 PASS, package-4-final Python 16개 불변과 정적 UI delta 독립 검증. 출시 준비 PASS·실제 게시/태그는 최종 단계 |

단순 smoke·API 응답·목업만으로 실제 화면 E2E를 대체하지 않는다. 운영 환경·표본·현재 해시가 다른 항목을 하나의 PASS로 합치지 않는다. 허용된 미해결 항목은 영향·다음 검증 조건을 남기고 완료 범위 검토에서 구분한다.

## 프로그램 형태 배포 가능성 검토

세 가지 선택의 런타임·용량 방향·업데이트·OAuth/저장 재검증 범위는 [Windows 프로그램 형태 배포 검토](WINDOWS_DISTRIBUTION.md)에 정리했다. 이번 installer/launcher는 새 설치·경계·CMD 시작과 실제 Edge E2E·CSS 보완 package-4-final의 핵심 UI/패키지를 검증했다. standalone exe/WebView2 host는 미구현 검토 항목이다.

사용자가 요청한 프로그램 배포는 가능성·형식·작업 범위 검토 단계다. 실행 패키지 형식과 UI가 표시되는 방식을 분리해야 한다. 현재 앱은 Python 로컬 서비스와 React 정적 UI이며 HTML 파일을 단독 열어 쓰는 앱이 아니다.

| 대안 | 사용자 실행 방식과 검증 영향 | 현 단계 권고 |
|---|---|---|
| 로컬 설치 스크립트 + 프로그램 launcher + Edge UI | 사용자 범위의 fresh venv/private home에 설치하고 launcher로 로컬 서비스·Edge 화면을 시작. 기존 Python 설치가 필요하며 HTML 단독 실행이 아님 | 신규 설치·한글/공백 CMD 시작·새 Edge/GPU·package-4-final 핵심 UI/패키지 확인 |
| 실행 파일 bundle | Python 앱·필수 런타임·정적 UI를 Windows 실행 폴더 또는 exe에 묶음. 추론 환경·모델·개인 인증은 별도 | 다음 후보는 standalone PyInstaller one-folder. 이번 릴리스에 이미 독립 exe가 있다고 주장하지 않음. 서명·설치 프로그램 구매·전역 변경 자동 승인 아님 |
| 별도 desktop WebView host | UI를 브라우저 탭 대신 독립 창으로 표시. OAuth·오디오·파일 저장·접근성·종료 동작을 새 host에서 다시 검증 | 기술 가능성 검토. 별도 native UI 전체 재구현을 자동 확정하지 않음 |

[PyInstaller 공식 operating-mode 문서](https://pyinstaller.org/en/stable/operating-mode.html)는 Python interpreter와 의존성을 folder 또는 실행 파일로 묶고 산출물이 OS/Python에 종속됨을 설명하며 one-folder 검증을 먼저 권고한다. [pywebview 공식 usage](https://pywebview.flowrl.com/guide/usage.html)는 독립 window host를 제공한다. 이 자료는 형식 검토의 출처이며 본 프로젝트의 실제 exe·desktop host 성공 증거가 아니다. 이번 구현은 `--home`·`serve --port`·`--no-browser` 선택과 v0.6.0 wheel, user-scope 설치 스크립트·launcher·fresh venv/private home으로 진행한다. 선택·의존성·패키징 버전·검증 결과는 새 구현과 부모 검토 후 기록한다. 프로그램형 실행 경로와 standalone exe의 차이를 안내한다.

## 실제 신규 M6 실행·최종 패키지

M6 작업 실행은 `m6-86e746953f92404fbe38c3bb36a42e4c`, 독립 검토는 `m6-independent-24b7f1ed677d4402a918faa9c6ad6364`다. 원시 실행·설치 경로·개인 증거는 `<m6_private_stage>`와 `<m6_private_review>`에 보존하며 공개 문서에는 별칭만 쓴다. 기존 M5 wheel·WAV·토큰·inventory·로그를 이번 성공 근거로 사용하지 않았다. 같은 프로젝트 지정 모델과 OAuth client/allowlist 원본만 출처를 기록해 사용했다.

| 최종 산출물 | 크기 | SHA-256 |
|---|---|---|
| `ai_manager_local-0.6.0-py3-none-any.whl` | 143,598 bytes | `2ed825de0408663f615fd06f8f80166ff7f5ce67ded8a6efecdd0ef01a56a1bb` |
| `ai-manager-0.6.0-windows.zip` | 157,240 bytes | `b1626bc374196984033b56d5eeaf89f2cfc30b0e6baa762dd32744f0cd865133` |

package-3의 source manifest 22개와 source/wheel/final-installed package 파일 21개 바이트가 일치했다. 이후 CSS 보완 package-4-final을 새로 만들고 설치 package 21개 바이트·실제 제공되는 root/CSS와 wheel의 일치를 확인했다. 최종 wheel entry 26개와 현재 source manifest 22개도 독립 확인했다. 실제 서버의 HTML/CSS/JS 3개와 설치/배포 바이트 일치, manifest 백업과 명시 privacy 검사도 통과했다. JS 변경은 CSS 파일명 참조 delta였고 나머지 실행 코드는 동일했다. Python 모듈 16개는 package-3와 package-4-final에서 동일하다. 복사한 문서/스크립트/lock 7개, ZIP과 release 디렉터리의 MANIFEST 포함 10개 파일도 일치했다. wheel에는 검사한 알려진 개인 문자·WAV·DPAPI·SQLite·모델 가중치가 없었다. 이는 명시 패턴·파일 종류 검사 범위이며 모든 가능한 비밀 탐지 인증은 아니다. 이번 형식은 Python 3.10이 필요한 설치 스크립트/launcher이며 standalone exe가 아니다.

[INSTALL](INSTALL.md)·[RECOVERY](RECOVERY.md)는 package-3에서 freeze했고 package-4-final에도 같은 바이트로 포함했다. 문서·스크립트·lock은 CSS 보완 단계에서 바꾸지 않았다. 설치 코드는 기존 install/home·overlap·reparse 경로·잘못된 wheel/lock hash·잘못된 package identity를 거부하고 원본을 보존했다. 최종 installer 독립 경계 8개를 통과했다. 새 최종 설치 폴더의 앱 Python은 site-packages의 0.6.0을 import했고, 한글/공백 경로 `Start-AiManager.cmd --no-browser --port <port>`의 실제 시작·loopback listener를 확인했다. stderr는 비어 있었다. 기존 소유 서버의 도구 종료 동작은 자동 승인 검토에서 거절됐으며 사용자가 해당 서버를 직접 종료한 뒤 정상 시작했다. 거절을 우회하거나 전역 정책을 바꾸지 않았다.

이미 이번 M6에서 fresh 인증한 home은 정확 settings SHA와 별도 manifest 백업을 확인한 뒤 최종 새 설치본에 명시 연결했다. home-link 경계 5개 검증에서 home 파일 집합 불변·백업 일치·반복 백업 덮어쓰기 거부·잘못된 hash/overlap/reparse 거부를 확인했다. 실제 연결도 최종 wheel hash·현재 settings hash·백업 존재와 토큰/수집 상태 보존을 확인했다. 이전 M5 home을 복사해 fresh M6로 제출한 것이 아니다.

## 최종 설치본 코드·복구 독립 검토

CSS 보완 전 package-3 최종 설치본 140개 테스트가 19.797초에 PASS했다. 뒤의 package-4-final은 Python 모듈 16개를 바꾸지 않고 정적 UI/CSS를 보완했으며 새 설치 파일·표본 UI 검증과 구분한다. 초기 package-1의 source-only/설치 검증과 그 뒤 발견된 반례는 별도 중간 이력이며 final package-3의 검증으로 대체하지 않는다.

발견·수정·최종 검증한 주요 반례는 다음과 같다.

- source integrity 검사 후 exclusive lock이 생기면 backup이 계속 대기하던 반례: 짧은 busy timeout·10초 progress deadline을 추가했다. 최종 설치본이 독립 15초 harness 제한 안에서 `database_backup_timeout`을 반환하고 원본·실패 임시 증거를 보존하며 최종 target을 만들지 않음을 확인했다. 모든 I/O의 10초 상한을 보장하는 주장은 아니다.
- 동일 컬럼만 갖고 PK/FK/NOTNULL/unique 제약이 없는 DB를 허용하던 반례: 같은 앱의 정확 canonical schema와 비교해 거부한다. SQL literal `'run ning'`·`'RUNNING'` 변형도 최종 설치본에서 거부했다.
- 실제 os.link 공개 경합·기존 target·missing/corrupt source·잠금·unsupported schema 등 최종 DB 경계 8개를 통과했다. 복원은 정상 snapshot에서 새 target으로의 복사이며 손상 원본 자체 수리가 아니다.

실제 Windows controller 프로세스가 새 합성 worker를 시작한 뒤 controller를 종료하는 시험에서 owned worker/하위 프로세스가 종료되고 active/queued 작업이 interrupted·audio 없음으로 재시작됐으며 새 소유권을 얻었다. 실제 OS/Job Object 검증과 합성 작업을 사용한 상태 계약 증거다. 실제 모델/GPU crash·모든 드라이버 장애를 검증했다고 주장하지 않는다.

개발 중/package-1 시점의 별도 fresh CLI 합성 검증에서는 새 init·설정 덮어쓰기 거부·미연결 계정·controlled expired refresh 실패/credential 보존·경로 traversal 거부·출력의 합성 비밀값 부재를 확인했다. 이 개별 합성 실험을 package-4에서 전부 다시 수행했다고 표시하지 않는다. 최종 설치본의 동일 코드/패키지 바이트와 회귀 증거, 새 실계정 인증/수집·대표 실제 흐름을 각각 구분해 연결한다. 독립 verifier는 실계정 OAuth·Drive·GPU를 수행하지 않았으며 해당 실제 검증은 아래 새 증거와 분리한다.

## 새 인증·수집·runtime/모델 준비

이번 M6 fresh home에서 사용자가 A/B 각각 직접 OAuth 로그인·동의를 마쳤고 UI의 두 계정 refresh가 `refresh_verified`·error null로 확인됐다. 새 수집은 A 486 files·109 folders·excluded 319·errors 0, B 113 files·14 folders·excluded 34·errors 0으로 complete였다. 이는 계정별 파일 관찰이며 중복 제거 모델 수나 모든 가중치의 실행 성공이 아니다. 해당 인증·수집은 최종 wheel 교체 전에 같은 M6 home에서 수행했고 최종 설치본 연결 시 보존을 확인했다. 현재 최종 설치본의 새 대표 E2E도 아래와 같이 확인했다.

새 home의 별도 runtime 설치와 최종 설치 CLI probe에서 Python 3.10.11, qwen-tts 0.1.1, torch/torchaudio 2.9.1+cu128, transformers 4.57.3, accelerate 1.12, CUDA true·RTX 3070·blockers 없음으로 확인됐다. probe의 model_loaded/inference는 false이며 import/CUDA 준비가 실제 TTS 성공을 뜻하지 않는다. sox binary 미발견도 기록했다. 그 상태에서 이번 한국어 A/B 실제 생성·재생·저장은 성공했으므로 이번 검증 경로의 작동을 확인했지만 다른 sox 의존 기능의 지원까지 보장하지 않는다.

새 준비 실행에서 지정 0.6B 13개·1.7B 12개 모델 파일의 현재 바이트 해시와 ready를 확인했다. 기존 허용 모델 자산만 입력으로 사용했고 과거 run state/WAV를 준비 입력으로 섞지 않았다. runtime·준비 성공과 새 생성·재생·저장 성공은 별도의 gate다.

## 새 최종 설치본 Edge/GPU 실제 검증

이번 M6의 새 비교 `9b2878d1c6934b11961a6b38084da2e9`는 A/B 각각 새 run을 만들고 같은 새 텍스트·seed `3124752109`·공통 생성 옵션·cold A→B·offline·결과 cache=false로 실행했다. 입력 전문은 비공개에 보존하고 SHA-256은 `c0260872e6c1af45c93214e1973d5f4b701936caeb449cec9d4def61ad40f17f`다. 두 모델은 succeeded·EOS true·error null로 종료했다.

| 새 실제 출력 | A: 0.6B | B: 1.7B |
|---|---|---|
| 크기 | 564,524 bytes | 510,764 bytes |
| frames / 길이 | 282,240 / 11.76초 | 255,360 / 10.64초 |
| SHA-256 | `5bf1249726b620df45e535dc92e937fa2d1fac7f473e1c69ef195dba4922d59a` | `98aff1a3e10d5cf8fdac4fef1a9f574154fa27cb1fcd5f71f0b6e39177a8399e` |

두 출력은 24 kHz·mono·PCM16·clipped samples 0이었다. 새 M6 준비의 13/12개 모델 manifest/입력 바이트·현재 M6 home의 실제 model path·설치된 실행 모듈 5개 해시가 해당 run 출처와 일치함을 독립 확인했다. M5 WAV·실행 기록을 재사용하지 않았다. 실제 생성 성공은 해당 환경·입력의 확인이며 품질 우열이나 모든 입력·VRAM 상한을 뜻하지 않는다.

Edge native audio는 각각 ended=true·currentTime=duration·error null을 확인했다. 원본 저장 anchor 각 1회에서 지원 download observer·Page completed·실제 저장 파일의 크기/SHA-256을 연결했고 독립 저장 파일 검사와 일치했다. 예전 M5 다운로드를 현재 E2E로 제출하지 않았다.

평가는 undecided와 중립적인 기능 검증 메모를 저장하고 새 reload 후 같은 값의 재조회를 확인했다. schema의 source 값이 user여도 실제 입력은 에이전트의 중립 흐름 테스트이며 사용자 취향을 대행하거나 사람의 청취 품질 평가를 수행한 것이 아니다. 검색·계정 필터·상세의 메타/실행 구분·Escape 닫기와 포커스 복귀·Tab 3px outline을 확인했다.

768/1280/1440/1920의 가로 넘침 없음과 캡처를 확인했다. 이는 모든 폭/모든 상태 조합의 완전한 검증이 아니다. 현재 reduced-motion 선호 true의 핵심 표본에서 animation none·0초 transition을 확인했지만 전체 동작·스크린리더·전면 WCAG audit은 수행하지 않았다.

최종 대비 표본에서 본문·보조본문·primary button은 양호했으나 작은 설명/배지 텍스트 3개가 4.5:1 미만이었다. 이를 성공으로 숨기지 않고 CSS 색상 최소 보완과 package-4-final 새 빌드/설치 바이트 확인을 수행했다. 최종 Edge의 실제 computed 색상 표본에서 설명 4.952:1·neutral 배지 5.190:1·success 배지 5.766:1, 보조본문 5.675:1·primary 버튼 5.253:1·본문 12.156:1을 확인했다. 현재 reduce=true의 핵심 표본은 animation none·duration 0초·transition 0초였다. [WCAG contrast minimum 해설](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)의 일반 작은 텍스트 4.5:1 기준으로 확인한 표본이 통과했지만 화면 전체 audit·스크린리더·모든 상태 조합 인증은 아니다. 이 변경은 추론 모듈을 바꾸지 않으므로 같은 M6 실행의 모델/출력 증거와 새 UI/패키지 해시를 구분해 검증한다.

## 완료 범위·최종 게시와 알려진 제한

새 한국어 GPU 실행·비교·재생·저장·평가 재조회·핵심 UI의 현재 증거는 위와 같다. 작은 텍스트 대비 보완 뒤 package-4-final의 새 해시·소스/설치 바이트·대표 Edge UI를 재검증했다. 남은 최종 단계는 승인된 공개 파일 반영·원격 대조·v0.6.0 태그/Release 식별이다. 작업 crash/cancel의 실제 OS+합성 검증과 실제 GPU 결과를 분리한다. M5의 Chrome 제한은 알려진 이력으로 보존하고 이번 범위를 Chrome 조사로 확대하지 않는다. Edge를 우선한다.

초기 추가 390px 관측에서 목록 제목의 과도한 줄바꿈이 보였다. package-4-final에서 좁은 화면 header를 세로 배치하도록 보완했고 실제 390px의 column 배치·가로 넘침 없음은 확인했다. 다만 해당 제목 전체의 최종 시각 확인은 도구 캡처/viewport 제약으로 끝내지 못했다. 원계획 최소 폭 768px 밖의 추가 관측이며 모바일 완성 PASS로 표시하지 않는다. 4개 대표 폭의 가로 넘침 없음도 모든 상태 조합의 검증을 뜻하지 않는다.

현재 판정은 **확인한 Windows/Edge 환경의 M6 출시 준비 gate PASS, 공개 반영·원격 검증·태그/Release 식별은 최종 게시 단계**다. 공개 원문/비변경 blob·배포 ZIP 해시와 태그의 대상 커밋·Release 실제 존재는 게시 후 각각 확인한다. 태그 생성 전 완료됐다고 미리 주장하지 않는다. 알려진 Chrome 제한·390px 전체 시각 미확인·접근성 전면 audit/스크린리더·청취 품질·실제 GPU crash/장시간 stress 미검증을 보존한다.
