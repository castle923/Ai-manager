# Llama Colab Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 앱의 새 작업실에서 요청을 내보내고 무료 Colab에서 사용자가 직접 생성한 결과를 가져온다.

**Architecture:** stdlib 계약 모듈을 앱과 수동 업로드 실행 코드가 공유한다. 새 local-only home의 sidecar는 요청과 외부 보고만 저장하며 기존 local inference 검증 계약과 분리한다. 작은 공개 코드 묶음과 요청 파일은 사용자가 Colab에 직접 전달하고, 자동 네트워크·패키지 설치 없이 현재 VM의 검증된 모델을 읽기 전용으로 사용한다.

**Tech Stack:** 기존 Python/unittest, stdlib JSON/hashlib/pathlib, React/TypeScript/Vite, 기존 Colab Torch/Transformers/bitsandbytes.

**Spec:** `docs/superpowers/specs/2026-10-25-llama-colab-handoff-design.md` — 2026-10-25 사용자 승인. 세부 구현·검증은 위임됐으므로 추가 계획 승인 없이 순차 진행한다.

## Global Constraints

- 제품 기준 소스 `c0812ed`. 기존 checkout에서 `codex/llama-colab-handoff` feature branch를 사용한다. 부모가 branch 전환 완료를 확인하기 전 변경을 시작하지 않는다. 기존 PR branch·개인 자료·원본 packet을 보존한다.
- 부모가 branch 전환을 확인했다. 사용자가 세부 진행을 위임한 범위에서 기존 checkout·feature branch를 사용해 설치 의존성 재사용과 환경 보존을 우선한다. 새 worktree와 자동 setup은 만들지 않는다.
- GPT-6.1 sol / medium 실무자와 fresh 검토자, 부모 조정·독립 검토. 작업별 brief와 spec/global constraints를 전달하고 다음 task로 넘어가기 전 인터페이스를 확인한다.
- Python 검증은 사전 지정된 기존 개발 venv, `PYTHONPATH=src`, 새 TEMP/evidence를 사용한다. 실행 경로는 비공개 ledger에 있다. 추가 의존성·다운로드·새 과금·권한 확대가 필요하면 사전알림 후 중단한다. D 드라이브와 기존 home을 탐색하지 않는다.
- 입력 UTF-8 2,048 bytes, 비공백·NUL 없음·lone surrogate 없음, chat template 포함 1~64 tokens; greedy/seed=0/batch=1/max_new_tokens=32. 기본 새 합성 입력은 `물은 얼면 무엇이 되나요?`이며 한국어 품질 평가가 아니다.
- raw request JSON 최대 16,384 bytes, raw result JSON 최대 65,536 bytes. 경로별 HTTP body 제한을 기본 4 KiB 처리보다 먼저 적용한다. wrapper/base64 JSON을 쓰지 않는다.
- UTF-8 canonical JSON은 `ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False`; 자기 digest 필드만 제외. Unicode 정규화 없음. duplicate/unknown keys, 비유한 숫자와 1e999, bool-as-int, 잘못된 UTF-8·surrogate·과도한 nesting은 거절한다.
- UUID는 lowercase UUID4 hex 32자, hash는 lowercase SHA-256 64자, created_at은 timezone 포함 UTC ISO8601. 신규 요청·결과만 지원하며 과거 smoke import는 제외한다.
- 모델 `llama-3.1-8b-instruct`, revision `0e9e39f249a16976918f6564b8830bc894c89659`, manifest SHA `a8fcf721121d9704daea0b45189868cdc479b18e6755df07d984e8637007318d`를 고정한다.
- 실행 profile `llama-colab-int8-handoff-v1`. runtime 계약은 Python `3.12.13`, torch `2.11.0+cu128`, numpy `2.0.2`, transformers `4.57.3`, accelerate `1.12.0`, safetensors `0.8.0`, bitsandbytes `0.50.2`. 상속 환경 전체 pip-check PASS를 주장하지 않는다. 버전 불일치 시 설치하지 않고 blocked다.
- 기존 guard SHA `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`를 유지한다. FP16/BF16 worker·profile·runtime과 기존 notebook은 변경하지 않는다. 새 app-request worker source SHA를 생성하고 고정 prompt worker와 구분한다.
- sidecar는 기능 데이터 범위다. 새 home의 정상 앱 초기화 DB/빈 registry/task-runs 생성은 허용한다. 기존 home/auth/DB/API key/runtime/모델 탐색·복사는 금지한다. 실제 Colab은 현재 cache로 가능할 때 사용자 확인의 단일 실행만 허용하며 keepalive·자동 retry는 없다.
- 사용자 추가 승인: 현재 public lock의 frontend 13개 누락 패키지, 다운로드 예상 20~60 MB·디스크 0.5 GB 준비만 허용됐다. 담당자가 설치·결과를 별도 보고한다. 모델/runtime/앱의 그 밖의 다운로드는 이 승인에 포함하지 않는다.
- 공개 앱의 source bundle export는 저장소의 공개 계약·worker·guard·manifest만으로 빌드돼야 한다. private frozen packet을 요구하지 않는다. `adapter_manifest_llama.json`의 원본 bytes가 고정 a8fc manifest이며 파생 normalize로 원본 digest를 대신하지 않는다.

## Review Focus

- 같은 요청으로 다른 결과가 들어오면 덮어쓰지 않고 conflict여야 한다 — Task 1 중복/경쟁 테스트.
- 한국어·combining characters·HTML 같은 출력은 변형 없이 안전한 텍스트여야 한다 — Task 1 canonical, Task 3 UI 테스트.
- 빈 home·로컬 모델 미등록에서도 Colab 화면이 열려야 한다 — Task 3 mocked/실제 UI.
- EOS와 length cap, 엔진 성공과 guard STOP이 섞이면 성공으로 오인하지 않아야 한다 — Task 1/2 상태 테스트.
- 오래된 Colab globals/marker·모델 cache 변경·실행 재클릭은 원본 보존과 no retry를 유지해야 한다 — Task 2 fresh context 테스트.

## 파일·공유 인터페이스

| 파일 | 책임 | 소유 task |
|---|---|---|
| `src/ai_manager/colab_contract.py` | stdlib strict JSON·정규화·요청/결과 계약 | 1 |
| `src/ai_manager/colab_handoff.py` | home-bound sidecar·원자적 no-overwrite 저장 | 1 |
| `scripts/colab/llama_handoff_worker.py` | 새 요청 전용 bounded INT8 worker | 2 |
| `scripts/colab/build_llama_handoff.py` | 작은 수동 업로드 bundle·entrypoint·source pins | 2 |
| `src/ai_manager/colab_source_pins.json` | 앱과 실행 bundle이 검증하는 공개 source SHA | 2 |
| `.gitattributes` | 새 pinned source의 최소 `text eol=lf` 항목만 추가 | 2 |
| `src/ai_manager/server.py` | raw JSON API·download | 3 |
| `frontend/src/ColabHandoffPanel.tsx`, `frontend/src/TaskPanel.tsx` | 기존 스타일의 독립 영역 | 3 |
| `tests/test_colab_handoff_contract.py`, `tests/test_colab_handoff_store.py` | 계약·sidecar | 1 |
| `tests/test_colab_handoff_bridge.py` | 합성 Colab bridge·worker | 2 |
| `tests/test_colab_handoff_http.py` | raw HTTP·보안·빈 home | 3 |
| `docs/LLAMA_COLAB_HANDOFF.md` | 사용자 흐름·실제 검증/제한 보고 | 4 |

공통 API: `parse_document(raw: bytes, kind: str) -> dict`, `canonical_bytes(value: dict, digest_field: str) -> bytes`, `document_digest(value: dict, digest_field: str) -> str`, `validate_input_text(text: str) -> dict`, `build_request(text: str, source_pins: dict) -> dict`, `validate_request(value: dict, source_pins: dict) -> dict`, `validate_result(value: dict, request: dict) -> dict`. 오류는 `ColabContractError(code: str)`이며 raw 입력·경로를 메시지에 담지 않는다. `parse_document`는 kind=`request`/`result` 크기와 strict JSON을 검사한다. preview의 text 검사는 validate_input_text를 사용하며 저장하지 않는다. schema_version은 정수 1, source_pins는 정확한 키 contract/worker/guard의 dict다.

`HandoffStore(home: Path, source_pins: dict)`는 `save_request(value: dict) -> dict`, `get_request(request_id: str) -> dict`, `import_result(raw: bytes) -> dict`, `detail(request_id: str) -> dict`를 제공한다. build_request는 저장 없는 preview이며 save_request는 전체 문서 검증 후 저장한다. 저장 경로는 `home/colab-handoff/{requests,results}/{uuid}.json`, detail은 정확히 `{request: dict, result: dict|null}`다. get/detail은 읽기 전용이다. 결과의 동일 UUID+동일 result digest는 기존 기록 반환, 다른 digest는 `result_conflict`; request digest 일치 검사는 언제나 별도다. 원자적 게시와 no-replace를 함께 보장한다.

요청 top-level 정확한 키는 `schema_version, request_id, created_at, input, model, execution, request_sha256`. input=`text,sha256,bytes`; model=`model_id,revision,manifest_sha256`; execution=`profile_id,runtime,source_sha256,limits`. limits=`max_input_tokens:64,max_new_tokens:32,seed:0,do_sample:false,batch_size:1`; source_sha256=`contract,worker,guard`의 실제 파일 SHA. runtime 키는 위 버전 계약의 `python,torch,numpy,transformers,accelerate,safetensors,bitsandbytes`다.

결과 공통 top-level 키는 `schema_version,request_id,request_sha256,input_sha256,model,execution,status,result_sha256`. status=`success`이면 추가 정확한 키 `response,engine,phase,guard`; stopped/failure이면 추가 정확한 키 `reason,phase,guard`만 허용하고 출력 원문을 받지 않는다. response=`text,input_tokens,generated_tokens,eos_reached,length_cap_reached`; engine=`generation_calls,quantized_linear_count,gpu_parameter_tensor_count,cpu_offload,disk_offload,model_sha_verified,runtime_verified`; phase=`stage` enum(`preflight,hashing,loading,generating,done`); guard=`status,reason,gate_opened,worker_returncode,final_worker_returncode,remaining_owned_count,cleanup_measurement_error`. guard status enum은 `not_started,completed,stopped`, reason은 `not_started,worker_exited,guard_stopped,worker_failed,cleanup_failed`. stopped reason은 `approval_required,environment_unavailable,source_mismatch,model_mismatch,input_token_limit,guard_stopped,already_started`, failure reason은 `worker_failed,output_invalid,cleanup_failed`다. guard의 원래 세부 사유는 private VM 로그에만 남기고 대응 enum으로 줄인다. 실패 단계의 nullable 종료코드는 허용하되 성공 guard는 두 값 0을 강제한다. 모든 reason은 enum이며 traceback/log/path는 받지 않는다. success의 engine 두 검증 bool은 true여야 한다.

### Task 1: strict 계약과 새 sidecar

**Interfaces:** 위 공통 함수와 HandoffStore를 생산한다. source pins는 필수 주입하며 아직 실행 source가 없으면 합성 테스트용 pins만 사용한다. 실제 앱 export는 Task 2의 pin 파일 검증 전 차단한다.

- [ ] 1. 실패 테스트 작성: duplicate/unknown/NaN/1e999/surrogate/bool/oversize/nesting 거절, Unicode normalization 없음, 자기 digest 제외, 한 글자 변조 거절. success는 calls=1/Linear224/GPU291/no offload/input≤64/output≤32/EOS xor cap을 확인하고 cap이면 32를 요구한다. guard STOP과 nullable 종료코드는 성공으로 승격하지 않는다.
- [ ] 2. 지정 기존 Python으로 `-m unittest discover -s tests -p test_colab_handoff_contract.py -v`를 실행해 RED를 확인하고 stdlib만으로 최소 구현한다. 모델·runtime import 금지 sentinel과 네트워크 차단 mock을 포함한다.
- [ ] 3. 새 임시 home에서 store 테스트 RED→GREEN: 명시적 export 전 저장 없음, UUID 경로 검증, symlink/reparse 거절, atomic no-replace, 동일 결과 중복/다른 결과 충돌, 동시 게시 경쟁, 이전 데이터 보존, raw 경로·키 없는 error. `test_colab_handoff_store.py`를 같은 unittest discover 방식으로 실행한다.
- [ ] 4. 두 타깃 PASS와 source diff를 fresh 검토자에게 넘긴다. 검토 후 해당 task 파일만 커밋하고 해시·명령·실측을 private report에 남긴다. 부모와 공유 인터페이스를 확정한 뒤 Task 2로 이동한다.

### Task 2: 수동 업로드 Colab bridge

**Interfaces:** `build_bundle(output: Path) -> dict`는 새 출력 전용으로 stdlib 계약·새 worker·guard218·원본 `src/ai_manager/adapter_manifest_llama.json` bytes·entrypoint와 pins를 묶는다. manifest는 공개 repo에 존재하며 별도 private packet·normalize·네트워크 입력 없이 raw SHA a8fc를 검증한다. `run_request(request_bytes: bytes, model_root: Path, workspace_root: Path, approved: bool=False) -> dict`는 명시적 VM 로컬 경로만 받는다. 경로는 request/result로 전달하지 않는다. 결과는 Task 1 계약 그대로다.

- [ ] 1. `test_colab_handoff_bridge.py` RED: 기본 approved=false면 모델 import/읽기/실행 0, source/manifest/runtime 변조와 기존 WORK 거절, 과거 globals·marker 불변, 반복 실행 0, 모델 read-only sentinel. 검토 가능한 작은 bundle이며 새 패키지 요구가 없음을 정적 검사한다.
- [ ] 2. 새 worker/entrypoint 최소 구현. tokenizer는 `local_files_only=True`, `trust_remote_code=False`; template 적용 후 64토큰 초과면 생성 0. 고정 manifest 전량 SHA와 runtime/source pins 검증 후 UUID fresh WORK/context를 만든다. 공개 guard218 `run_owned` 아래 single INT8 generation을 수행하고 모델에 CPU/disk offload가 생기면 실패한다. 부수 로그는 새 VM WORK에만 남기고 결과에는 whitelist summary만 쓴다. guard 자원 한도는 현재 canonical 계약을 유지한다.
- [ ] 3. fake tokenizer/model/guard로 한 번 생성·EOS/cap·worker failure·guard STOP/cleanup failure·source 변경을 테스트한다. canonical result를 Task 1 validator로 직접 읽어 소비자 일치를 검증한다. bundle SHA와 app pins를 실제 source bytes에서 생성하고 빌드 시 재검사한다. 새 source가 기존 FP16/BF16/고정 prompt worker와 다름을 확인한다.
- [ ] 3a. Windows autocrlf로 pin이 달라지지 않도록 `.gitattributes`에 `src/ai_manager/colab_contract.py`, `scripts/colab/llama_handoff_worker.py`와 새 별도 entrypoint/bridge 등 실제 pinned source의 정확 경로만 `text eol=lf`로 추가한다. 기존 guard/helper LF 규칙을 보존하고 광범위 변환하지 않는다. source-pins JSON은 자기 자신을 해시하지 않는다. source map에 entrypoint를 추가할 때 request의 exact contract/worker/guard 키는 바꾸지 않고 bundle manifest에서 entrypoint를 별도 검증한다.
- [ ] 4. 두 task 타깃 PASS·기존 watchdog/builder 회귀를 실행하고 fresh 검토 후 task 파일과 pins만 커밋한다. 모델 다운로드·실제 Colab 실행은 이 task 합성 검증에 포함하지 않는다.

### Task 3: raw API와 독립 UI

**Interfaces:** POST `/api/colab-handoff/preview`는 raw JSON 정확한 키 `text`(16KiB)를 받아 저장 없이 전체 request 문서를 반환한다. POST `/api/colab-handoff/requests`는 export 클릭에서만 전체 raw request를 받고 validated no-replace 저장 후 detail을 반환한다. GET `/api/colab-handoff/meta`는 공개 pins·limits·기본 합성 text, GET `/api/colab-handoff/requests/{id}`는 detail, GET 같은 경로 `/download`는 raw request attachment. POST `/api/colab-handoff/results`는 raw result를 받는다. 기존 local registry 연결을 요구하지 않는다.

- [ ] 1. `test_colab_handoff_http.py` RED: 새 home·auth stub의 loopback 앱에서 request 16KiB/result64KiB 경로 제한, wrapper 거절, chunk/truncated/잘못된 Content-Length 거절, strict duplicate parser, Host/Origin/CSRF 거절, wrong request/conflict 반환, 경로 없는 오류, existing local execution_verified 불변을 검사한다.
- [ ] 2. Task 1의 build_request/save_request를 위 API에 연결한다. UI 입력은 preview 클릭 시 로컬 서버로 가며 외부 전송은 없다. 전체 요청 검토 뒤 별도 export 클릭에서 `/requests`에 그 문서를 raw 전송한다. 이 결정으로 브라우저 canonical 구현 중복을 피한다. preview와 export 사이는 digest를 비교하고 입력 수정 시 preview를 무효화한다.
- [ ] 3. `ColabHandoffPanel`을 existing task panel 스타일로 독립 표시한다. 단계는 입력/preview→명시적 JSON 다운로드→Colab 사용자 직접 실행 안내→file input 64KiB 검사/import다. `textContent`/React text node만 쓰며 위험 HTML 출력·stopped/failure·입력 편집 후 stale preview를 mocked HTTP 테스트로 고정한다. 실제 요청 UUID와 결합된 출력·EOS/cap·외부 보고/로컬 미검증 문구를 표시한다.
- [ ] 4. Python HTTP/계약 회귀 PASS 후 기존 frontend 의존성이 실제 사용 가능하면 `npm.cmd run build`를 실행한다. node_modules가 없으면 npm ci/install을 하지 않고 즉시 부모에게 알린다. 같은 프로젝트의 명시적 cache·기존 lock 일치 설치본만 읽기 전용 preflight하며 설치가 필요하면 대상·예상 용량과 다운로드 범위를 먼저 알린다. 이때 backend/계약의 독립 작업은 계속한다. 지정된 기존 의존성을 재사용할 때 provenance를 기록한다. 기존 정적 snapshot은 실제 새 build 성공 없이 만들어진 것으로 주장하지 않는다. fresh UI/code 검토 뒤 task만 커밋한다.

### Task 4: 통합 검증과 한계 문서

**Interfaces:** 이전 task의 immutable request/result를 새 격리 home·port에서 사용한다. private report에는 run ID·입력 출처·명령·결과·한계를 기록하고 공개 문서는 비식별 요약만 담는다.

- [ ] 1. 새 합성 request/result E2E를 loopback HTTP와 새 앱 UI에서 수행한다. 빈 home 접근, 정확한 preview/download, reload 뒤 재표시, 같은 결과 재가져오기, 다른 digest conflict, HTML escape, failed/stopped 표시와 로컬 verified 불변을 확인한다. 기존 앱·old home은 접속하지 않는다.
- [ ] 2. 앞선 타깃 및 기존 registry/history/task/watchdog 회귀, frontend build를 수행한다. 실패·skip은 이유와 범위를 기록한다. 테스트가 없는 browser-only 상호작용은 새 UI 관찰로 보완한다. 추가 설치가 필요하면 그 검증을 미완료로 남기고 사전알림한다.
- [ ] 2a. 최종 커밋의 각 pinned source blob 바이트 SHA와 working tree·bundle의 pin을 대조한다. `.gitattributes` 범위와 LF를 확인하며 불일치면 게시·실제 Colab E2E를 진행하지 않는다. 이 검사는 Task 2 pin 생성과 별개의 최종 소스 결합 확인이다.
- [ ] 3. 현재 Colab VM/cache와 지정 코드만으로 가능하면 사용자 검토한 작은 bundle/request 수동 업로드와 단일 합성 생성 후 결과 import를 수행한다. source/runtime/model SHA가 다르거나 VM이 없으면 멈추며 새로운 다운로드·keepalive·토큰 복사·자동 Drive 연결을 하지 않는다. 미실행이면 실제 paired-request E2E 미검증으로 명시한다.
- [ ] 4. `docs/LLAMA_COLAB_HANDOFF.md`와 진행 ledger를 실제 결과로 갱신한다. 공개 tracked diff·비밀/경로·generated source pins·정적 bundle 정합성을 검토하고 부모의 독립 최종 검증 후 GitHub 반영 절차로 넘긴다. 새 Release·설치 패키지·공개 서비스는 범위 밖이다.

## 자체 검토

설계의 모든 요구는 Task 1의 계약/저장, Task 2의 fresh Colab 단일 실행, Task 3의 API/UI, Task 4의 통합 검증에 대응한다. 검토 초점 다섯 항목은 각 task의 테스트에 연결했다. preview/export는 Task 3의 저장 없는 preview API와 validated save_request로 단일화한다. 세부 plan은 승인된 범위의 실행 결정이며 추가 사용자 승인 요청을 만들지 않는다.
