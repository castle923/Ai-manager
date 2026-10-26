# 다른 PC·새 세션 개발 인계

기준일: 2026-10-26 (Asia/Seoul). 이 문서는 같은 Ai Manager의 소스·진행 상태를 이어받기 위한 공개 인계서다. 실제 개인 자료와 비밀은 포함하지 않는다. 새 PC 설치·인증·모델 실행을 이번에 검증했다는 뜻은 아니다.

## 2026-10-26 노트북 중복 설치 예방 — 최신 후속 상태

[설치 재사용·전체 사전 검사 분리 보고서](docs/COLAB_RUNTIME_REUSE_20261026.md)를 먼저 읽는다. 새 `Llama_Free_T4_INT8_Reusable_Runtime.ipynb`는 동일 커널의 성공한 준비 context를 실제 경로·payload SHA·격리 자식의 정확한 모듈/설치 버전으로 재검사한 뒤 설치를 건너뛴다. 원래 full preflight는 별도 기본 OFF gate와 UUID별 새 proof 경로로 분리했다. 불완전 준비/변조/실패는 자동 수리·새 ROOT·once 초기화 없이 중단하며, 기존 TTL·deadline·RAM floor/cap·모델/worker/guard/contract와 원본 packet을 보존했다. 새 오프라인 관련 회귀는 122개 중 121개 통과·실패/오류 0·symlink 권한 skip 1개이며, 실물 notebook 기본 Run all의 no-IO 네 단계 SKIP를 확인했다. 실제 RAM/GPU 효과·Colab 실행·app paired E2E·새 Windows 설치 프로그램은 미검증이다. 추가 다운로드·설치·Colab 재연결·과금은 하지 않았다.

## 2026-10-25 Llama 무료 Colab 파일 연결 — 최신 앱 상태

최신 후속 실행은 기존 무료 T4 세션의 정상 Edge 재연결 1회에서 GPU 사용량 제한으로 거절됐다. 유료 전환·CPU 대체·재시도·다운로드·설치·생성·결과 가져오기는 없었고 현재 cache/runtime/source는 연결되지 않아 미확인이다. 실제 app→Colab→결과 가져오기 E2E와 새 Windows standalone 설치 프로그램은 미검증이므로 배포 준비 완료로 판정하지 않는다. 설치본에 빠지던 공개 source pin·notebook 자산을 공통 staging과 wheel build hook으로 포함하도록 수정했고, 새 handoff 회귀 40개(39 통과·symlink skip 1) 및 packaging 3개 통과, 네트워크 거절 조건의 wheel 빌드/재빌드·checkout 없는 설치본 시작/metadata/합성 미리보기/notebook 응답을 확인했다. 전체 588개를 이번 수정 후 재실행한 결과는 아니다. UUID 재시도 차단은 현재 커널 메모리와 실행 디렉터리 marker 범위이며 커널 재시작·새 디렉터리를 넘어서는 영구 중복 방지가 아니다. 자세한 범위는 아래 연결 문서의 후속 절을 따른다.

[무료 Colab 파일 실행 안내와 검증 범위](docs/LLAMA_COLAB_HANDOFF.md)를 먼저 읽는다. 새 local-only 작업실에서 요청을 검토·내보내고, 사용자가 준비된 무료 T4에서 직접 실행한 결과 JSON을 가져오는 별도 handoff 기능을 추가했다. strict JSON·UUID/digest 결합·불변 sidecar·공개 소스 notebook·독립 앱 패널을 구현했으며 기존 로컬 FP16/BF16 profile과 검증 판정은 유지했다. 외부 보고를 로컬 `execution_verified`나 registry verified로 승격하지 않는다.

새 격리 앱의 실제 브라우저에서 합성 요청·결과의 정확한 다운로드/가져오기, Unicode·HTML 형태 문자열의 텍스트 표시, 동일 결과 재가져오기, 충돌 보존, 잘못된/과대 파일 거절, 중단/실패/32토큰 상한 구분, 새 페이지의 동일 결과 재가져오기 및 빈 registry 유지까지 확인했다. 자동 reload/history 복원은 제공하지 않는다. 테스트 임시 경로 이식성 수정 전 최종 전체 오프라인 회귀 588개는 580개 통과·실패 0·오류 0·skip 8, frontend production build는 통과했으며 정적 산출물과 공개 source pin의 커밋·working tree·bundle 바이트 일치를 확인했다. 최초 하네스 실패와 보정 조건은 비공개 증거에 보존했다. skip 8개는 symlink 권한 2개와 별도 tracking 의존성 6개다.

최종 검토에서 HTTP·store 테스트의 비공개 과거 증거 폴더 의존성을 제거했다. 공개 Git 소스만 둔 새 OS 임시 체크아웃에서 대상 15개 모두 수정 전 fixture 오류를 재현했고, 두 테스트 파일 수정 후 14개 통과·Windows symlink 권한 skip 1개·실패/오류 0을 확인했다. 표준 임시 디렉터리가 실행기의 TEMP/TMP를 따르며 제품 소스는 변경하지 않았다. 전체 588개를 재실행한 결과는 아니다. 프런트엔드 빌드는 사전 승인된 정확한 잠금 개발 의존성 23개 설치본을 재사용했다. 설치는 `ignore-scripts`·audit/fund 비활성 조건이며 전역 환경·`package.json`·잠금 파일은 불변이고 모델·런타임 다운로드는 없었다.

**새 앱 요청의 실제 paired-request Colab 생성·결과 import는 미검증·보류다.** 기존 화면의 T4 활성 세션은 관찰했으나 컴퓨터 사용 안전검사가 현재 브라우저 URL을 확인하지 못해 화면 조작을 중단했다. 빈 셀 하나 추가 이후 실행 소스 붙여넣기·모델 생성은 없었고, 정확한 source/runtime/model cache 검사는 미수행이다. 기존 VM·모델·새 요청을 보존했으며 다른 UI나 숨은 API로 우회하지 않았다. 다음 사용자 대화에서 UI 연결 복구 후 검사를 이어가고, 설치·다운로드가 필요하면 사전 안내한다. 아래 수정 guard의 과거 고정 prompt smoke는 별도 이력이다. 새로운 다운로드·설치·자동 재시도·Drive 연결·상시 원격 추론은 포함하지 않는다.

## 2026-10-25 수정 guard의 새 무료 T4 실제 완료 — 이전 실제 smoke 이력

[Colab 검증 보고서의 최신 실제 검증 절](docs/COLAB_MODEL_VALIDATION_20261023.md)을 먼저 읽는다. 종료 확인 수정 guard `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`의 별도 새 실행에서 단일 엔진 smoke와 guard 정상 완료를 확인했다. 원본 packet `5796fff3f78ad7fd915da99c7750d488c4ef82457dc877528658f26751a6e5c1`(11셀·코드 6개·자산 9개)은 불변이고, Drive 새 실행본은 정상 UI의 코드 6개와 안내 Markdown으로 구성해 코드 source 해시를 검증했다. 아래 준비 한정·실제 Colab 미검증 표기는 당시 이력이며 앞선 guard STOP도 그대로 보존한다.

이번 고정 모델 다운로드는 10파일·16,069,722,669 bytes·전체 SHA-256 true·token_saved false다. context·root·work true·phase done이며 생성 1회·입력 41/새 출력 3토큰·EOS true다. 로딩 70.153177724초·생성 2.018226058초, GPU peak allocated 10,087,137,280/reserved 10,412,359,680 bytes, 224개 INT8 Linear·GPU parameter 텐서 291개·CPU/disk offload 없음이다.

실제 guard 필드는 `completed / worker_exited`, worker_returncode 0·final_worker_returncode 0·remaining_owned_count 0·cleanup_measurement_error false다. elapsed 186.037초·917표본, `owned_zombie / main_poll`·종료 확인 1표본/0.201초를 관측했다. 최소 cgroup 여유 2,807,578,624 bytes > 2 GiB, peak owned RSS 6,658,187,264 bytes < cap 7,340,994,560 bytes이며 자동 재시도는 false다. helper 보조 필드뿐 아니라 지정된 이번 비공개 download·watchdog·phase·file-result-check·runtime·실행 허용값 증거의 실제 필드를 직접 대조했다. 원격 OS의 독립 감사나 모든 종료 경쟁·순간별 메모리 상한 보장은 아니다.

무료 계정·구독 없음·유료 CU 0을 UI에서 확인한 범위이고 유료 API 호출은 0회다. Python 3.12.13·Torch 2.11.0+cu128·NumPy 2.0.2에서 격리 text API를 실행했으며 사용하지 않는 Gradio/huggingface-hub 충돌이 남아 전체 상속 환경 `pip check` PASS는 아니다. 품질·일반 성능·앱 통합으로 확대하지 않는다. 이번 문서 갱신 자체는 모델 실행·다운로드·네트워크·인증/DB 접근 없이 두 문서만 추가 변경했으며 기존 미커밋 변경·packet·실행 증거를 보존했다.

남은 앱 연결 작업: 현재 앱 manifest의 model revision·10파일은 일치하지만 로컬 FP16 프로필(Torch 2.9.1·NumPy 2.2.6, GPU 3 GiB/CPU 4 GiB offload)과 이번 Colab INT8 전량 GPU 계약은 다르다. 별도 INT8 runtime/profile 연결과 합성 검증·새 실제 앱 E2E가 필요하다. 이번 Colab 결과로 로컬 `execution_verified=true`를 자동 갱신하지 않는다. 추가 다운로드 승인은 Colab 범위에 한정하며 D 드라이브 I/O는 보류하고 기존 모델·인증·DB를 보존한다. 직전 문서 갱신 시점에는 commit·push를 수행하지 않았다. 후속 검토·게시 단계는 별도 기록으로 구분한다.

## 2026-10-25 수정 감시기 노트북 준비 — 준비 당시 기록

[Colab 검증 보고서의 최신 노트북 준비 절](docs/COLAB_MODEL_VALIDATION_20261023.md)을 먼저 읽는다. 종료 확인을 수정한 canonical guard `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`와 새 읽기 전용 결과 helper를 포함한 별도 새 packet을 로컬에 준비했다. 전달 후보 `Llama_Free_T4_INT8_Exit_Confirmation.ipynb`는 80,682 bytes·SHA-256 `5796fff3f78ad7fd915da99c7750d488c4ef82457dc877528658f26751a6e5c1`, 11셀·코드 6개·내장 자산 9개다. 기존 packet·동결 원본·helper는 보존했다.

확인/승인/live 허용값 6개는 모두 False다. 새 helper는 컨텍스트·경로 결합과 제한된 파일 읽기를 검증하고 새 identity/poll/종료 확인 진단 필드를 허용 목록으로 출력한다. 컨텍스트가 없는 기본 실행에서는 파일을 읽지 않는 `not_ready / live_context_absent`를 출력한다. 완료 보조 필드만으로 OS cleanup을 보장하지 않으며 최종 종료코드와 cleanup 측정 오류도 별도로 확인해야 한다.

이번 새 타깃은 guard 45개·builder 18개·helper 8개 합계 71개다. 독립 검토자 7.330초·부모 7.224초에 모두 통과했고 실패·오류·skip은 0이다. 생성한 실제 notebook의 6개 코드 셀도 빈 namespace에서 파일·외부 실행을 거절하는 sentinel 아래 검증 표시 1개·live SKIP 3개·결과 진단 SKIP를 확인했으며 ROOT 생성·파일시스템 호출은 없었다. 추가 도구 설치·전체 제품 회귀는 하지 않았다.

소형 코드 packet 3파일 합계는 83,880 bytes다. builder는 실제 직렬화 합계와 1 MiB 여유분을 제외하고 최소 500,000,000,000 bytes를 보존하는 사전 검사로 조정했다. 생성 후 C 여유 표본은 598,362,329,088 bytes이며 동시 외부 사용 예약이나 전후 차이 전체의 작업 귀속을 보장하지 않는다. 모델·런타임 설치 정책 변경이나 cleanup은 아니다.

새 Colab 업로드·화면·GPU·설치·모델 다운로드/실행·Drive·유료 API·기존 인증/키/개인 DB 접근은 수행하지 않았다. 수정 guard의 실제 Colab 실행은 미검증이며 앞선 실제 엔진 smoke PASS/guard STOP 판정은 유지한다. 아래 '새 live packet 미생성'과 59개 검증은 이번 준비 이전 감시 수정 시점의 이력이다.

## 2026-10-25 새 Llama 실행과 감시 후속 진단 이력

[Colab 검증 보고서의 2026-10-25 절](docs/COLAB_MODEL_VALIDATION_20261023.md)을 먼저 읽는다. 아래 2026-10-23·24 및 제품/배포/전체 회귀 항목은 각 시점의 기록이다. 새 실행의 결과 출처는 사용자가 직접 수행한 읽기 전용 `FILE_RESULT_CHECK` 출력의 허용 필드 요약이며 원격 파일 전체를 독립 재검사한 결과가 아니다.

새 무료 T4 실행에서 고정 모델 10파일 16,069,722,669 bytes 다운로드와 전체 SHA-256 검증 true·토큰 저장 false를 관측했다. context·root·work 검증은 모두 true이고 Llama LLM.int8 단일 smoke는 1회 생성·입력 41/새 출력 3토큰·EOS로 성공했다. 로딩 69.674526초·추론 1.986636초, 224개 양자화 Linear·GPU 파라미터 텐서 291개·CPU/disk offload 없음이며 7개 phase의 마지막은 done이다.

감시는 다시 `stopped / worker_identity_changed`였다. 이번에는 `final_worker_returncode=0`·남은 owned 0을 확인했으나 `worker_returncode`는 없고 전체 guard 완료 PASS는 아니다. 최소 cgroup 여유 2,835,795,968 bytes는 2 GiB보다 높고 peak owned RSS 6,634,229,760 bytes는 cap 7,347,048,448 bytes보다 작다. OOM·traceback 표시는 false다. 실제 identity가 None이었는지 달라졌는지는 요약에 없어 실제 원인을 확정하지 않는다. 브라우저 결과 JavaScript·reCAPTCHA 오류와 도구 timeout의 원인도 미확정이며, 사용자 직접 결과 확인은 모델 재실행이 아니다.

오프라인에서는 독립 poll/psutil 제어로 같은 소유 zombie·process_absent인데 즉시 poll이 None인 두 종료 순서의 조기 STOP 결함을 재현하고 수정했다. 이 두 상태에만 1초 표본 기준 종료 확인 창을 두고 매회 기존 보호와 상태·RSS를 재검증한다. 1초는 OS 강제 시간 보장이 아니며 확인 기한을 넘긴 poll/wait 0으로 소급 PASS를 만들지 않는다. 실제 identity 변경·소유권 불명은 STOP을 유지한다. 새 진단 요약 필드는 identity 관측·poll 경로·확인 표본 수/시간이며 향후 새 읽기 전용 helper에 포함해야 한다. 이번 동결 helper는 보존했다.

수정 전 두 사례 실패 → 수정 후 guard 45개·builder 14개 통과를 확인했고 독립 검토자 합계 59개 7.197초·부모 독립 합계 59개 7.219초에 통과했다. 실패·오류·skip은 모두 0이다. canonical 감시기 raw LF SHA-256은 `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`이며 builder pin을 연동했다. 새 live packet은 생성하지 않았고 이번 전체 제품 회귀는 반복하지 않았다. 이 수정과 오프라인 결과로 실제 Colab guard STOP을 재분류하지 않는다.

실행 전 builder 컨텍스트 보호의 별도 합성 13개 통과는 해당 준비 시점 기록이며 이번 감시 수정 검증으로 재사용하지 않는다. 기존 원본 packet·동결 소스·실행 증거·모델·인증·키·개인 DB를 보존한다. 새 모델 실행·다운로드·유료 API·Drive·브라우저·개인 인증/DB 접근을 하지 않으며 후속 수정의 실제 Colab 모델 실행도 수행하지 않는다.

## 2026-10-23 모델 관측과 종료 감시 후속 작업

현재 후속 개발의 시작 소스는 `e0df07f2179b208cfec072da7e869ea40c5cc48e`이며 아래 제품·배포·이전 회귀 항목은 각 시점의 이력으로 보존한다. [이번 Colab 모델 검증과 종료 감시 보고서](docs/COLAB_MODEL_VALIDATION_20261023.md)를 먼저 읽는다. 지정된 원본 결과를 문서화하고 모델 재실행 없이 감시 종료 경쟁을 수정·오프라인 회귀하는 범위다.

Llama INT8 r02의 단일 짧은 입력 생성은 3토큰·EOS로 엔진 smoke 성공이다. 원래 watchdog은 `worker_identity_changed`로 중단되고 종료코드가 보존되지 않아 전체 감시 PASS는 미확정이다. Qwen FP32 두 크기의 단일 WAV와 Kokoro 직접 음소 FP32 smoke는 별도 근거의 한정 성공이며 청취 품질·전체 텍스트 G2P·앱 통합 성공으로 확대하지 않는다. `scripts/colab/llama_watchdog.py`의 새 합성 타깃 회귀는 기존 20개·신규 10개 합계 30개 통과·실패/skip 0이며 부모 독립 실행에서도 통과했다. 명령과 시간은 위 보고서를 따른다. 이 타깃 결과와 별도로 PR #2 병합 소스와 동일 tree의 새 전체 오프라인 회귀를 실행해 507개 중 500개 통과·7개 skip·실패/오류 0(71.789초)을 확인했다. skip은 tracking CPU 4개·decode 2개 의존성 미설치와 비특권 symlink 1개다. 전후 추적 소스 동일·새 격리 임시 자료·C 여유 조건을 확인했으며 부모 Python audit의 비-loopback 거절 기록 0은 OS 전체 계측이 아니다. 기존 동결/업로드 notebook·현재 Colab을 교체하거나 재실행하지 않았고 수정된 감시기의 실제 Colab 모델 실행은 미검증이다.

기존 인증·키·DB·보안·모델·원본 실행 증거를 보존한다. 이번 후속 작업에서 모델 재실행·다운로드·유료 API 호출·Drive 접근은 하지 않는다. 원본에 없는 OS 종료코드는 합성 회귀로 복원할 수 없다.

2026-10-24에는 수정 감시기와 r02 캐시 보호를 연결하는 별도 노트북 builder·합성 타깃 테스트를 로컬에 준비했다. 기본 무료 확인·새 실험 승인·세 live 허용값은 모두 False이며, 새 노트북의 stdlib 검사 및 기본 전체 5개 코드 셀에서 실단계 3개 SKIP를 확인했다. 새 합성 7개 통과(0.120초)는 앞선 전체 507개 회귀와 다른 검증이다. 원본/업로드 Colab을 변경하지 않았으며 업로드·설치·토큰 입력·GPU·모델 실행·시각 검증은 하지 않았다. 향후 외부 실행은 별도 승인 대상이다. 자세한 입력 핀·기본 차단·검증 공백은 위 보고서의 2026-10-24 절을 따른다.

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
