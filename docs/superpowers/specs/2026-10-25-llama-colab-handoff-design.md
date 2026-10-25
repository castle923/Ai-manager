# Llama 무료 Colab 실행·결과 가져오기 설계

작성일: 2026-10-25. 상태: 사용자 설계 승인 완료, 세부 계획과 구현·검증 진행 위임. 이 문서는 구현·설치·추론 완료 보고서가 아니다.

## 목적과 선택한 방식

사용자가 선택한 방식은 **무료 Colab에서 직접 실행하고 결과 파일을 Ai Manager로 가져오기**다. 앱에서 짧은 입력을 준비하고, 사용자가 검토한 요청 JSON을 Colab에 직접 올려 한 번 실행한 다음 결과 JSON을 앱에서 읽는다. 최종 성공 경험은 앱에서 자신의 요청과 연결된 생성문, 토큰 수, 외부 실행 보고 상태를 확인하는 것이다. 기존 무료 T4 INT8 smoke는 참고 이력이며 새로운 요청의 성공 근거로 재사용하지 않는다.

검토한 대안은 로컬 INT8 runtime/profile 추가였다. 앱 안에서 직접 실행할 수 있지만 별도 Windows 의존성, 실제 GPU 여유, 지정 모델 읽기와 새로운 로컬 E2E가 필요하다. 기존 FP16 환경과 D 드라이브 보존 조건을 고려해 이번에는 선택하지 않았다. 선택한 수동 방식은 무료 대화형 Colab을 유지하며 기존 runtime을 바꾸지 않지만, 매 요청마다 사용자 파일 전달과 직접 실행이 필요하다.

[Colab 공식 FAQ](https://research.google.com/colaboratory/faq.html)의 대화형 계산 용도와 무료 자원 제한을 따른다. API 서버, public tunnel, 별도 웹 채팅 UI, Colab 웹 UI 우회, 상시 원격 추론은 만들지 않는다. 자동 Drive 로그인·마운트, 앱 인증 재사용, 토큰 전달도 포함하지 않는다. 일반 대화 품질, 장문 성능, 서비스 가용성을 보장하지 않는다.

## 사용자의 네 단계

1. 새 로컬 전용 작업실에서 Llama 외부 실행 영역을 열고 짧은 비밀 없는 텍스트를 입력한다. 초기값은 새 합성 질문이다. 검토 화면에 정확한 입력, 모델 revision, INT8 조건과 파일 전달 범위를 보여준다. 사용자가 내보내기를 선택해야 요청을 저장하고 JSON을 다운로드한다.
2. 사용자가 공식 Colab notebook에 요청 JSON을 직접 업로드한다. notebook은 요청과 실행 환경을 검사하고 사용자에게 한 번의 제한 실행을 확인받는다. 필요한 설치나 다운로드가 발견되면 실행하지 않고 용량·대상을 먼저 알린다.
3. 준비 조건이 충족되면 사용자가 직접 생성 한 번을 실행하고 결과 JSON을 다운로드한다. 자동 재시도나 모델 대체는 없다. 실패·중단·환경 불명은 해당 상태 그대로 보존한다.
4. 앱에서 결과 JSON 하나를 선택한다. 앱은 저장된 요청과 결합을 확인하고 생성문과 외부 보고 상태를 표시한다. 일치하지 않으면 거절하며 기존 결과는 보존한다.

## 요청·결과 계약

구현자가 제안하는 초기 제한은 UTF-8 입력 2 KiB, 비어 있지 않은 Unicode 텍스트, NUL 금지, tokenizer 적용 후 chat template를 포함한 입력 최대 64토큰이다. 바이트 한도는 파일·화면 자원을 제한하고 토큰 한도는 기존 짧은 smoke 범위를 유지한다. 한국어도 허용하되 정확한 토큰 판정은 Colab의 지정 tokenizer가 한다. 초과하면 자르거나 다시 실행하지 않고 거절한다. greedy 생성, seed 0, batch 1, `max_new_tokens=32`를 고정한다. EOS 도달과 길이 상한 도달은 구분한다.

요청은 schema version, UUID, 생성 시각, 입력과 입력 SHA-256, 고정 모델 revision, manifest SHA, INT8 profile ID, 정확한 runtime 버전 계약, worker·guard source SHA, 입력/출력 토큰 한도를 포함한다. 결과는 같은 UUID·request digest·입력 hash·모든 계약 값을 반복하고 생성문, 토큰 수, 종료 이유, runtime 관측, 모델 검증 상태, phase 및 guard 요약을 담는다. model manifest 일치와 실행 profile 일치를 별도로 검사한다.

각 digest는 자신의 digest 필드만 제외한 문서를 `ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False`로 직렬화한 UTF-8 바이트의 SHA-256이다. Unicode 정규화는 하지 않는다. 중복 키·lone surrogate·`1e999`처럼 변환 후 무한대인 숫자도 거절하고 정수 필드에 bool을 허용하지 않는다. request digest는 요청 결합용이고 canonical result digest는 결과 중복 판정용으로 구분한다.

요청 파일은 최대 16 KiB, 결과 파일은 최대 64 KiB로 제한한다. strict JSON으로 중복 키, 알 수 없는 필드, NaN/Infinity, 잘못된 타입·범위, path 및 auth 관련 키를 거절한다. 토큰·키·계정·Drive ID·실제 경로·원시 로그는 어느 계약에도 없다. 모델 출력은 텍스트로 escape하여 표시하고 HTML이나 Markdown 명령으로 실행하지 않는다. 결과 내보내기는 사용자 선택의 로컬 JSON 저장만 지원한다.

결과는 신뢰할 수 없는 **외부 실행 보고**다. hash 결합은 파일 일관성을 검사하며 암호학적 원격 증명이나 실제 VM 상태의 독립 확인이 아니다. success·stopped·failure별 정확한 허용 필드를 가진 schema를 분리하며 실패에 성공 필드를 채워 넣지 않는다. engine 결과, guard 완료, 파일 일관성을 각각 표시한다. 외부 보고의 engine 성공 조건은 생성 호출 1회, 입력 1~64토큰, 새 출력 1~32토큰, INT8 Linear 224개, GPU parameter tensor 291개, CPU/disk offload 없음이다. EOS와 길이 상한은 정확히 하나만 참이어야 하며 상한 도달은 32토큰과 일치해야 한다. guard 완료는 `completed/worker_exited`, gate true, 두 종료코드 0, 남은 owned 0, cleanup 오류 false와 phase done을 모두 요구한다. 누락이나 STOP은 성공으로 승격하지 않는다.

## 격리 저장과 실행 준비

사용자가 명시적으로 선택한 새 local-only home의 작업실 아래 `colab-handoff` sidecar에 기능 데이터를 저장한다. 원본 입력은 사용자의 명시적 내보내기 후 이 비공개 sidecar에만 저장한다. 기존 home·settings·DB·registry·API key·auth·runtime은 탐색·복사·변경하지 않는다. 요청과 결과는 UUID별 새 파일로 원자적으로 게시하며 덮어쓰지 않는다. 같은 UUID와 동일 canonical result digest 재가져오기는 기존 기록을 반환하고 다른 result digest는 충돌로 거절한다. 요청 binding 검사는 별도로 수행한다. Git에는 합성 fixture와 공개 코드·문서만 들어간다. 인증 토큰은 앱·요청·결과·채팅으로 전달하지 않으며 필요해지면 사용자에게 Colab의 정상 직접 입력만 안내한다.

Colab에 현재 검증된 모델 파일이 남아 있다면 읽기 전용 입력으로 재사용 가능성을 검사할 수 있다. 새 요청 entrypoint는 UUID별 fresh context·WORK·marker·worker proof를 만들고 정확한 revision·전체 파일 SHA·runtime·worker·guard hash를 검증한다. 고정 prompt worker와 앱 요청 worker는 서로 다른 source SHA와 profile을 갖는다. 과거 ROOT/WORK/globals/context를 수동 재할당하거나 old marker를 변경·삭제하지 않는다. 기존 결과·원본 packet은 보존한다. 검토한 작은 실행 코드·요청 파일을 사용자가 수동 업로드하는 행위는 원격 패키지·가중치 다운로드와 구분한다. VM이 없거나 payload·runtime·모델 설치/다운로드가 필요하면 대상과 용량을 먼저 알리고 멈춘다. 이전 smoke 승인으로 새 다운로드를 자동 진행하지 않는다.

## 앱 접점과 상태

`TaskPanel.tsx`의 기존 panel·상태 스타일과 fetch 처리를 재사용하고 새 시각 방향은 추가하지 않는다. Colab 영역은 빈 home에서도 로컬 모델 등록·runtime 준비·Drive 로그인 없이 접근할 수 있는 독립 영역이다. 예상 API는 `POST /api/colab-handoff/requests`, `GET /api/colab-handoff/requests/{id}`와 `POST /api/colab-handoff/results`다. 요청 다운로드는 해당 ID에 한정한다. POST body는 wrapper 없는 raw JSON이며 request 16 KiB/result 64 KiB의 경로별 제한과 strict parser를 `server.py:379`의 기본 4 KiB 처리보다 먼저 적용한다. 기존 loopback Host/Origin·CSRF 검증은 유지한다. 파일 선택은 브라우저에서 바이트를 읽어 전송하며 서버에 임의 경로를 입력하지 않는다.

신규 계약·sidecar 서비스와 `server.py` 라우트, notebook builder의 별도 요청 실행 경로가 주요 변경 접점이다. `adapters.py:66-69`, `registry.py:282-352`, `task_inference.py:266-277`의 로컬 검증 계약은 유지한다. 외부 기록을 `task-runs`나 기존 validation DB에 주입하지 않는다. 로컬 `execution_verified` 및 registry verified 판정은 외부 결과로 바뀌지 않는다. 기존 과거 smoke 가져오기는 이번 최소 범위에서 제외한다.

## 수용 기준과 다음 작업

오프라인 합성 계약 테스트로 정상 결합, 변조·누락·과대 파일·중복 키·충돌 거절과 기존 DB 무접근을 확인한다. mocked HTTP, frontend production build, 새 격리 home·작업실·port의 실제 앱 브라우저 UI에서 로컬 내보내기·가져오기를 검증한다. 실행 중인 기존 앱은 입력으로 사용하지 않는다. sidecar 격리는 이 기능 데이터의 저장 범위이며 새 home의 정상 앱 초기화로 inventory·registry·task-runs 등이 생성되는 것은 허용한다. 실패와 길이 상한도 성공과 구별해 표시한다. 새 실제 Colab paired-request E2E는 추가 다운로드 없이 준비 조건을 충족할 때만 한 번 수행한다. 불가능하면 합성 UI 통과와 실제 Colab 미검증을 명시적으로 분리한다.

설계 승인 후 남은 작업은 ① 계약·격리 저장 구현, ② 앱 내보내기·가져오기와 notebook 요청 결합, ③ 합성·HTTP·빌드·격리 UI 검증, ④ 조건 충족 시 단일 실제 E2E와 비식별 보고다. 세부 구현 계획은 설계 승인 뒤 작성한다.
