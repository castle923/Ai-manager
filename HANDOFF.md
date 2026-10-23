# 다른 PC·새 세션 개발 인계

기준일: 2026-10-23 (Asia/Seoul). 이 문서는 같은 Ai Manager의 소스·진행 상태를 이어받기 위한 공개 인계서다. 실제 개인 자료와 비밀은 포함하지 않는다. 새 PC 설치·인증·모델 실행을 이번에 검증했다는 뜻은 아니다.

## 2026-10-23 모델 관측과 종료 감시 후속 작업

현재 후속 개발의 시작 소스는 `e0df07f2179b208cfec072da7e869ea40c5cc48e`이며 아래 제품·배포·이전 회귀 항목은 각 시점의 이력으로 보존한다. [이번 Colab 모델 검증과 종료 감시 보고서](docs/COLAB_MODEL_VALIDATION_20261023.md)를 먼저 읽는다. 지정된 원본 결과를 문서화하고 모델 재실행 없이 감시 종료 경쟁을 수정·오프라인 회귀하는 범위다.

Llama INT8 r02의 단일 짧은 입력 생성은 3토큰·EOS로 엔진 smoke 성공이다. 원래 watchdog은 `worker_identity_changed`로 중단되고 종료코드가 보존되지 않아 전체 감시 PASS는 미확정이다. Qwen FP32 두 크기의 단일 WAV와 Kokoro 직접 음소 FP32 smoke는 별도 근거의 한정 성공이며 청취 품질·전체 텍스트 G2P·앱 통합 성공으로 확대하지 않는다. `scripts/colab/llama_watchdog.py`의 새 합성 타깃 회귀는 기존 20개·신규 10개 합계 30개 통과·실패/skip 0이며 부모 독립 실행에서도 통과했다. 명령과 시간은 위 보고서를 따른다. 이는 제품 전체 회귀가 아니다. 기존 동결/업로드 notebook·현재 Colab을 교체하거나 재실행하지 않았고 수정된 감시기의 실제 Colab 모델 실행은 미검증이다.

기존 인증·키·DB·보안·모델·원본 실행 증거를 보존한다. 이번 후속 작업에서 모델 재실행·다운로드·유료 API 호출·Drive 접근은 하지 않는다. 원본에 없는 OS 종료코드는 합성 회귀로 복원할 수 없다.

## 먼저 읽을 상태

| 구분 | 고정 기준과 의미 |
|---|---|
| 현재 제품 소스 | `b545d56ede9031a714c5672168becfc201d5b7cf`, Python 제품 버전 `0.19.0` |
| 인계 직전 문서 기준 | `3aa351b26d06588b8886971d54657c720eb0b2bb`; 이후 인계 문서 변경은 제품 코드·ZIP 변경이 아니다 |
| 0.19.0 기능 | 명시 동의 후 Claude 후보 분류·추천. 기본 꺼짐, 자동 API 전송·모델 등록·다운로드·실행 없음 |
| 0.19.0 패키지 | 로컬 portable Windows 패키지 검증 이력은 [0.19.0 보고서](docs/CLAUDE_RECOMMENDATIONS_0190.md). 공개 Release 자산으로 배포했다는 뜻은 아니다 |
| 공개 배포 이력 | [v0.15.0 Release](https://github.com/castle923/Ai-manager/releases/tag/v0.15.0), 제품 소스 `6c2cb6738c0208b7607385658804e85df7f58c5b`. 최신 소스 기능과 구분한다 |

README의 M0~M15와 과거 버전 항목은 각 단계 당시 기록이다. 이번 TTS·LLM 실제 API 관측은 [2026-10-22 검증 보고서](docs/CLAUDE_VALIDATION_20261022.md)를 따른다. 최신 상태는 이 문서와 [0.19.0 보고서](docs/CLAUDE_RECOMMENDATIONS_0190.md), [0.18.0 작업실](docs/WORKSHOP_REFERENCES_0180.md), [0.17.0 설정·탐색](docs/PERSONAL_MODEL_HUB_0170.md)을 먼저 읽는다. `frontend/package.json`의 `0.2.0`은 프런트엔드 내부 패키지 표기이며 제품 버전은 `pyproject.toml`을 따른다.

## 다음 개발자·에이전트의 시작 순서

1. [AGENTS.md](AGENTS.md)를 읽고 새 작업공간에도 적용한다. 모든 실무는 GPT-6.1 sol / medium 서브에이전트가 수행하고 부모는 조정·독립 검토를 담당한다. 같은 프로젝트 코드·문서의 후속 갱신은 허용되지만 다른 프로젝트 산출물이나 과거 출력으로 새 검증을 대신하지 않는다.
2. 새 clone 또는 독립 작업 디렉터리에서 `git status`, 현재 commit, 원격 URL을 확인한다. 변경이 있으면 보존하고 덮어쓰지 않는다. 이 문서를 받은 것만으로 원격이 GitHub라고 가정하지 않는다. 공개 GitHub 소스는 `https://github.com/castle923/Ai-manager.git`이다.
3. 인계받은 정확 문서 commit을 확인하고 별도 개발 branch를 만든다. 아래 예시의 `<published_handoff_commit>`은 게시 완료 뒤 전달된 commit으로 바꾼다. `b545...`는 제품 코드 기준이고 후속 인계 문서까지 포함하는 commit은 아니다.
4. 현재 작업의 고유 run ID·새 evidence/output 경로와 입력 출처 목록을 저장소 밖에 만든다. 소스 commit·의존 lock·실제 지정 자산의 버전/해시를 기록한다. 과거 보고서는 이력으로만 읽고 현재 테스트 결과는 새로 수집한다.
5. 아래의 로컬 개발 환경을 준비한다. 개인 자료가 필요한 작업은 사용자가 지정한 입력과 승인 범위를 먼저 확인한다. 외부 API·Drive 수집·다운로드·추론은 bootstrap에 포함하지 않는다.

```powershell
git clone https://github.com/castle923/Ai-manager.git Ai-manager-new
Set-Location Ai-manager-new
git switch --detach <published_handoff_commit>
git switch -c codex/continue-development
git status --short
git remote -v
git rev-parse HEAD
```

기존 checkout을 계속 쓰는 경우 무조건 reset/pull·강제 push를 하지 않는다. 해당 checkout의 변경과 대상 branch를 먼저 확인한다. 위 clone 명령은 새 PC에서 운영자가 실행할 안내이며 이번 인계 작업에서 새 clone을 실행한 결과가 아니다.

## 모델·로그인 없이 소스 개발 시작

Windows 소스 개발에는 Python과 Node.js/npm, Git을 준비한다. 이번 새 격리 환경에서는 Python `3.12.14`로 오프라인 회귀 477개 중 470개 통과·7개 skip·실패 0을 확인했다. 아래 venv 예시는 Python 3.12를 사용한다. 자세한 범위와 skip 사유는 [새 개발 환경 회귀 보고서](docs/DEVELOPMENT_REGRESSION_20261022.md)를 따른다. 이 결과는 기존 Python 3.10 기반 모델별 런타임이나 frozen 패키지를 3.12로 전환·검증한 것이 아니다. 전역 Python·PATH나 다른 프로젝트 환경을 바꾸지 않고 프로젝트 전용 venv를 사용한다.

Vite 7의 Node 요구 범위는 20.19 이상 또는 22.12 이상이다. 잠금 파일은 `frontend/package-lock.json`, `requirements.lock`이며 모델별 런타임은 별도다. Windows 독립 창을 빌드하려면 추가로 `requirements-desktop.lock`과 WebView2 Runtime이 필요하다. 전체 회귀에는 desktop 경계 테스트도 있으므로 `requirements-desktop.lock`을 같은 개발 venv에 설치한다. 브라우저 개발 실행과 frozen 독립 앱 검증은 별개다.

저장소 루트 PowerShell에서 실행한다. `<new_private_absolute_home>`은 이번 작업을 위한 새 절대경로로 바꾸고 Git 저장소 밖에 둔다. 다른 home의 settings/token/DB/output을 복사하지 않는다. `.venv`가 이미 있으면 기존 환경을 보존하고 별도 새 경로를 선택한다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e .
Set-Location frontend
npm.cmd ci --ignore-scripts
npm.cmd run build
Set-Location ..
.\.venv\Scripts\python.exe -m ai_manager.cli --help
.\.venv\Scripts\python.exe -m ai_manager.cli --home "<new_private_absolute_home>" init-local
.\.venv\Scripts\python.exe -m ai_manager.cli --home "<new_private_absolute_home>" serve --no-browser
```

`serve`가 표시하는 loopback URL을 Edge에서 연다. `--home`은 subcommand보다 앞에 둔다. `init-local`은 새 로컬 전용 설정만 만들고 Google 인증·Drive 수집·모델 준비를 하지 않는다. 이 빈 작업실에 기존 수집 후보가 보이지 않는 것은 정상이다. `serve` 실행 중인 터미널은 개발 서버 소유권을 유지하며 종료 시 해당 서버만 정상 종료한다. 모델 실행이나 실제 API 전송 버튼을 개발 smoke에 포함하지 않는다.

`src/ai_manager/static`에는 ignore 규칙이 있지만 현재 제품의 정적 번들 3파일(`index.html`, CSS, JavaScript)은 추적된 snapshot이다. 새 clone에도 해당 파일이 포함된다. 프런트엔드 수정·wheel/desktop 재패키징 시 `npm.cmd run build`로 새 번들을 생성하고 소스와의 정합성을 검증한다. `scripts/build_desktop_bundle.py`는 새 출력 디렉터리와 공개 Python 런타임 다운로드를 사용하는 별도 패키징 작업이다. 실행 전 현재 source binding·출처·해시·필요 네트워크/디스크 범위를 검토한다. `scripts/install_windows.ps1`은 과거 0.6.0 wheel 설치 경로이므로 0.19.0 개발 설치에 사용하지 않는다. 전역 PATH·실행 정책·보안/브라우저 설정을 바꾸지 않는다.

오프라인 단위·합성 회귀 실행은 다음 명령을 사용한다. 결과의 실제 통과·skip·시간은 새 환경에서 다시 기록한다. tests는 격리된 합성 자료를 사용하며 개인 home을 입력으로 주지 않는다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

전체 회귀 전에 `requirements-desktop.lock`을 설치하고, 테스트는 저장소 루트에서 실행한다. 한국어 Windows에서도 JSON·Node 파이프의 UTF-8 계약을 유지한다. Windows DPAPI·개인 디렉터리 ACL 검증은 제한된 sandbox에서 실패할 수 있으며 정상 사용자 컨텍스트의 새 합성 자료로 환경 원인을 구분한다. 검사를 skip하거나 보안 보호를 완화해 통과시키지 않는다.

## 개인 자산·비밀과 PC 이동

GitHub에서 이어받는 것은 소스·공개 문서·의존성 선언이다. Google OAuth client/allowlist, 계정·Drive ID, 실제 모델 경로/인벤토리, token·API key·보호된 추천 결과, settings·DB·원시 payload·로그·모델/출력은 공개 인계에 포함하지 않는다. `.gitignore`만으로 안전을 단정하지 않고 게시 전 추적 파일과 실제 diff 내용을 검사한다.

Windows DPAPI 자료는 기존 Windows 사용자·PC에 결합될 수 있다. 다른 PC에서 복호화·인증·같은 결과 복원을 보장하지 않는다. 기존 home·credentials·provider 보호 저장소를 자동 복사하거나 암호화를 약화하지 않는다. 저장된 credential 표시도 현재 인증 유효성 검증은 아니다.

새 PC의 Drive 연결이 필요해지면 사용자가 지정한 OAuth client JSON과 allowlist를 저장소 밖에서 제공하고, 로컬 전용 home과 다른 별도 새 Drive home에 설정한다. `init`은 기존 `init-local` 설정을 덮어쓰거나 Drive 모드로 바꾸지 않는다. 계정 A/B의 Google 로그인·동의는 사용자 직접행위다. API 기능이 필요해지면 사용자가 새 PC의 앱에 키를 직접 입력하며 에이전트는 키 값을 요청·조회하지 않는다. 모델 root·runtime 경로도 새 PC에서 명시 지정하고 바이트/버전·환경 준비·실제 추론을 각각 새로 검증한다. 이 인계 요청은 새 인증·수집·다운로드·자료 이관·모델 실행을 자동 승인하지 않는다. 같은 PC·동일 home 개발 재개와 다른 PC의 새 home 설치를 혼동하지 않는다. 복구가 필요한 경우 [복구 원칙](docs/RECOVERY.md)을 읽고 대상·보존·격리 범위를 별도로 고정한다.

## 완료 이력과 미검증 범위

다음 세 항목은 기존 동일 프로젝트의 기록이며 이번 인계 작업에서 재실행한 결과가 아니다.

- 0.19.0 최종 제품 회귀: 475개 중 468 통과·7 skip·실패 0. fake transport·합성 UI와 실제 API 관측의 범위는 [보고서](docs/CLAUDE_RECOMMENDATIONS_0190.md)에서 구분한다.
- 사용자가 직접 승인·전송한 STT 세 후보 관측 1건: `finished`, 입력 1,382·출력 332토큰, usage 기반 기본 요율 계산 USD 0.0003042. 실제 청구서·세금·계약 청구액은 미확인이다. 광범위 분류 정확도나 모델 실행 성공의 근거가 아니다.
- 같은 Windows 사용자·같은 PC·같은 home의 정상 재시작 1회에서 보호된 추천 결과·usage·이유의 로컬 재표시를 확인했다. 새 PC·강제 종료·장기 유지·현재 계정 인증 유효성은 미검증이다.

## 2026-10-22 새 승인에 따른 TTS·LLM 검증 완료

사용자는 현재 후보 범위와 새 미리보기·전송 조건을 확인하고 앱에서 각 목적의 최종 동의·전송을 직접 선택했다. TTS·LLM 두 목적 모두 `finished`·오류 없음·`stale=false`와 usage 기반 비용 표시를 확인했다. 이전 STT 승인이나 아래 과거 네 목적 계획을 재사용한 전송이 아니다.

TTS의 비식별 후보 A/B는 `tts/high`, 후보 C는 `unknown/unknown`, LLM의 후보 A는 `llm/high`를 반환했다. 입력/출력 토큰은 TTS 1,409/336, LLM 1,063/117이며 합계 2,472/453이다. 기본 요율 계산은 각각 USD 0.0003089, USD 0.0001648, 합계 USD 0.0004737이다. 실제 공급자 청구서는 미확인이고 목적별 앱 예산 USD 0.01은 청구 hard cap이 아니다.

성공 작업자 경로 근거는 count 2회·Messages 2회이며 독립 네트워크 counter가 아니다. 이는 metadata 분류 관측으로 모델 identity·전체 가중치·무결성·runtime·추론·품질·성능 검증이 아니다. 추가 이미지 후보는 제외했고 점 추적은 미확인이다. 개인 집계·후보 대응·원시 payload·식별자·인증정보는 공개하지 않는다. 상세 범위는 [이번 검증 보고서](docs/CLAUDE_VALIDATION_20261022.md)를 따른다.

현재 지원 taxonomy는 `tts`, `stt`, `llm`, `image`, `tracking`이다. TAPIR의 `tracking`은 점 추적이며 일반 영상 생성으로 설명하지 않는다. 후보 폴더 이름·metadata 분류는 가중치 완전성·identity·revision·실행 환경·품질 확인과 별개다. 모든 모델·입력·브라우저·PC의 성공, 전면 접근성, 장시간 stress를 보장하지 않는다.

## 과거 미승인 이력: 네 목적의 제한 API 검증 계획

인계 당시 TTS·이미지·LLM·점 추적의 네 목적을 각 세 후보로 대조할 비공개 계획만 준비됐고 그 계획은 미승인이었다. 해당 옛 계획 자체의 실제 외부 count/Messages 호출은 0이다. 위 TTS·LLM 검증은 현재 자료·새 미리보기·사용자의 별도 직접 승인으로 수행했으며 이 네 목적 계획의 실행이나 완료로 취급하지 않는다. 이전 STT 1회 승인을 재사용하지 않는다. 원본 후보·계정·ID·경로·개인 집계·정확 payload는 공개하지 않는다. 새 세션에서 비공개 계획을 자동 탐색·전송하지 말고 사용자가 지정한 자료를 받아 확인한다. 다른 PC에서는 현재 로컬 자료로 후보를 다시 대조하고 새 mapping·새 preview를 만든다. 새로운 Drive 수집이 필요하면 실행 범위부터 확인한다. 옛 payload/nonce를 재전송하거나 옛 후보 대응을 현재 사실로 간주하지 않는다.

제안 한도는 목적별 무료 count 최대 1회와 유료 Messages 최대 1회, 네 목적 합계 각각 최대 4회, 자동 retry 0, 최대 출력 2,048토큰이다. 각 앱 예산 USD 0.01·배정 합계 USD 0.04는 공급자 청구 hard cap이 아니다. 당시 로컬 시나리오 합계 USD 0.0069642는 실토큰 count나 실제 청구액이 아니며 새 시점의 요율·본문·한도를 재확인한다.

실제 외부 전송 전에 사용자가 볼 수 있는 정확 표시명/필드·후보 순서·본문 bytes/SHA·현재 snapshot·모델/정책·비용·보관/제외 항목·호출 상한·실패 중단 조건을 다시 고정하고 **새 사용자 승인**을 받는다. 실제 앱의 새 preview가 승인한 payload와 일치하는지 대조하고 바뀌면 중단/재승인한다. 최종 동의와 전송은 사용자가 직접 선택한다. 키를 자동 조회·복사하지 않는다. 하나라도 실패·timeout·청구 불명으로 끝나면 다음 목적 전송도 중단하고 자동 재시도·후보 교체를 하지 않는다.

이번 결과 문서의 GitHub 최신화는 추가 API 전송, Drive scan/download/write, 모델 추론, 보안 설정 변경, cleanup, 비밀 이전, 새 Release/설치 자산 게시를 포함하지 않는다. 새 PC 실제 설치·실계정/모델 E2E는 수행 전 범위와 보존 방법을 고정하고 새 증거로 보고한다.

## 새 세션에 전달할 시작 지시

> 같은 Ai Manager 프로젝트를 이어서 개발한다. 먼저 저장소 AGENTS.md와 HANDOFF.md, 최신 0.19.0 보고서를 읽고 현재 commit/status/remote를 확인하라. 모든 실무는 GPT-6.1 sol / medium 서브에이전트가 수행하고 부모는 조정·독립 검토한다. 기존 자료·인증·DB·모델·보안 설정을 보존하고 고유 실행/evidence 경로를 만들어라. GitHub 공개 소스에 개인 비밀/인벤토리는 없다. 새 PC에서 기존 token/DB/home를 자동 복사하지 말라. 2026-10-22 TTS·LLM은 별도 새 승인으로 검증 완료했지만 과거 네 목적 계획은 실행 승인이 아니며, 추가 API를 호출하지 말라. 이번 검증 보고서의 실제 관측과 미검증 한계를 먼저 확인하라. 현재 요청의 범위와 사용자가 지정한 입력을 확인한 뒤 독립적으로 가능한 로컬 개발부터 진행하라.
