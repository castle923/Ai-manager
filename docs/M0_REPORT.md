# M0 조사·설계 결과

기록일: 2026-10-16 (Asia/Seoul) · 판정: **조사·설계·OAuth 파일 준비 완료 / 앱 실인증 미검증(전체 PASS 아님)**

M0 진행 승인을 받아 이번 프로젝트에서 새로 수집한 Drive 조회 결과와 PC 감사, 공식 배포 문서를 정리했다. 아래 조회 결과는 조사 담당 에이전트가 전달한 이번 M0 증거를 문서화한 것이다. 이 문서 작성 에이전트가 Drive 조회나 PC 감사를 직접 수행했다는 뜻은 아니다. 앱 구현·모델 다운로드·설치·추론은 수행하지 않았다. M1 구현 승인도 아직 없다.

## 1. 관찰한 사실

### Drive 조회 범위

현재 Codex 연결에서 계정 A/B의 프로필·루트·초기 허용 폴더 직계 조회가 성공했다. 초기 범위는 A의 `A_ROOT_01`, `A_ROOT_02`, `A_ROOT_03`, B의 `B_ROOT_01`이다. 실제 계정·폴더 이름·Drive ID는 공개 저장소 밖 개인 allowlist에 기록한다.

이는 초기 범위 확인이며 재귀 인벤토리 완료나 두 Drive 전체 모델 목록의 완전성 증명이 아니다. 계정 전체 백업, 개인 원본 문서·과거 결과 보고서, 생성 이미지, 공유 드라이브, 바로가기, 코드·압축파일·`.cache`는 초기 범위에서 제외한다. 모델 config·tokenizer·공식 README/LICENSE 등 직접 필요한 배포 구성요소는 allowlist 안에서 허용한다. 범위 확장은 별도로 승인받는다. 폴더 제목만으로 모델을 확정하지 않는다.

Codex 연결에서 읽기 호출을 했다는 사실은 연결 토큰의 실제 권한이 읽기 전용이라는 증거가 아니다. 기존 연결의 effective scopes는 미확인이고, 제작 앱 인증으로 이전하지 않는다.

### 첫 실행 모델의 파일 메타데이터

선정 모델은 **Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice**다. 계정 B에서 새로 조회한 모델 폴더와 공식 배포 revision `85e237c12c027371202489a0ec509ded67b5e4b5`의 13개 파일 경로·크기가 일치했다. 합계는 **2,498,388,392 bytes**(약 2.50 GB / 2.33 GiB)다. `.cache`는 제외했다.

Drive 메타데이터에서 요청한 체크섬 필드가 반환되지 않았으므로 실제 바이트·해시 일치는 미검증이다. 경로·크기 일치는 공식 revision과의 바이트 동일성, 모델 준비 완료 또는 실행 성공을 증명하지 않는다.

공식 원본의 예상 SHA-256은 다음과 같다. M3에서 실제 다운로드한 바이트와 대조할 값이며 현재 Drive 파일의 검증 결과가 아니다.

| 파일 | 공식 원본 예상 SHA-256 |
|---|---|
| `model.safetensors` | `bc3c7e785eb961179c25450d1acff03f839e0002f2f3a5aeb67b5735c0fa2adb` |
| `speech_tokenizer/model.safetensors` | `836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258` |

첫 실행은 Korean, Sohee, batch 1, 이번 실행에서 새로 작성한 짧은 문장으로 계획한다. 첫 검증은 화자·언어를 고정한 기본 합성으로 범위를 제한하고 instruct 파라미터를 제외한다. 실제 음성 생성은 M4다. [고정 모델 revision](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/85e237c12c027371202489a0ec509ded67b5e4b5), [공식 Qwen3-TTS 문서](https://github.com/QwenLM/Qwen3-TTS)

### PC 읽기 전용 감사

이번 M0 PC 감사는 모델 설정 변경 전의 gpt-5.6-sol 서브에이전트가 새로 수행했다. 이후 생성 서브에이전트의 설정은 GPT-6.1 sol / medium이다.

| 항목 | 이번 조회값 / 한계 |
|---|---|
| OS | Windows 11 Home 64-bit, build 22631 |
| CPU | Ryzen 5 5600X, 6 cores / 12 threads |
| RAM | 31.95 GiB, 조회 당시 여유 13.80 GiB |
| GPU | RTX 3070, 8,192 MiB; 조회 당시 여유 6,527 MiB |
| NVIDIA driver | 616.64 |
| 데이터 볼륨 | 제안 볼륨 여유 약 734.19 GiB; 쓰기 검증 미수행 |
| 기본 Python / launcher | 3.10.11 / 3.10 등록 확인; 시스템 전체의 다른 Python 부재는 단정하지 않음 |
| Node / npm / Git | 24.21.0 / 11.19.0 / 2.53.0.windows.2 |
| 환경 도구 | uv, ffmpeg, sox가 PATH에 없음 |
| 기본 Python 패키지 | torch, torchaudio, torchvision, qwen-tts, transformers, accelerate, soundfile, numpy, gradio 배포 메타데이터 없음 |
| WSL | WSL2 Ubuntu 24.04 등록; 기동·내부 패키지·GPU 미검증 |

`npm.ps1`은 실행정책으로 차단되어 `npm.cmd`로 버전을 확인했다. 기존 venv를 탐색·실행하지 않았다. 실제 PyTorch CUDA, VRAM 적합성, 모델 로딩은 미검증이다. 조회 중 설치·다운로드·추론·프로세스 종료는 없었다. 메모리 여유는 시점에 따라 변한다.

## 2. 기술 결정과 제안

- React + TypeScript 화면, Python 로컬 API, SQLite를 유지한다. 정확한 설치 조합의 호환성은 아직 검증하지 않았다.
- 저장 위치는 `<data_root>/models`, `<data_root>/runs`, `<data_root>/db`를 제안한다. 제안한 실제 경로는 조회 당시 없었으며 생성·쓰기 검증은 하지 않았다. 실제 경로는 개인 기록에만 둔다.
- 추론은 신규 Python 3.12 독립 환경을 권장하고 M3에서 준비한다. 공식 `qwen-tts==0.1.1`은 Python >=3.9, `transformers==4.57.3`, `accelerate==1.12.0` 및 torchaudio/soundfile/sox/onnxruntime 등을 요구한다. README는 새 Python 3.12 환경을 권장한다. [고정 소스 pyproject](https://raw.githubusercontent.com/QwenLM/Qwen3-TTS/022e286b98fbec7e1e916cb940cdf532cd9f488e/pyproject.toml)
- PyTorch·torchaudio·CUDA wheel 조합은 M3 설치 검증 후 lock한다. NVIDIA 드라이버 확인은 CUDA 추론 성공 증거가 아니다. [PyTorch 설치 안내](https://pytorch.org/get-started/locally/)
- native Windows에서 기본 attention 경로부터 검증한다. FlashAttention 2는 필수로 두지 않는다. WSL 전환은 실패 근거를 검토한 뒤 별도 결정하고 자동 변경하지 않는다.

## 3. 앱 인증 설계와 미확인 사항

앱 전용 Cloud 프로젝트와 Desktop OAuth client 하나를 권장한다. 같은 client에서 두 계정이 각각 동의하고 연결·토큰·해제 상태를 분리한다. 새 Google 계정은 필요 없다. 적합한 기존 Cloud 프로젝트를 명시적으로 선택해 사용하는 것도 가능하다.

시스템 브라우저, PKCE와 state 검증, `127.0.0.1` 임의 포트 loopback을 사용한다. 제안 scope는 `https://www.googleapis.com/auth/drive.readonly`다. 이 scope는 계정 전체 읽기 권한이며 폴더 제한은 **앱 allowlist**에서 구현한다. Google가 폴더 단위로 토큰을 제한한다고 표시하지 않는다. `drive.file`은 쓰기도 가능한 선택 파일 scope로, 기존 중첩 모델 트리 전체의 읽기를 대체한다고 보장할 수 없다. API key만으로 개인 Drive 파일을 읽을 수 없다. [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Drive scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)

client JSON은 Git 밖에 두고 토큰은 OS 보안 저장소에 보관한다. 연결 해제·권한 취소·갱신 실패를 처리한다. External / Testing 사용 시 두 계정을 test user로 등록하고, 해당 조건에서 refresh token이 7일 후 만료될 수 있으므로 재로그인을 지원한다. [토큰 만료 조건](https://developers.google.com/identity/protocols/oauth2#expiration)

사용자가 앱 전용 Google Cloud 프로젝트, Drive API 활성화, External / Testing, 계정 A/B의 test user 등록, `drive.readonly`, Desktop OAuth client 생성과 저장소 외부 JSON 다운로드를 완료했다고 보고했다. Cloud 콘솔 설정과 실제 발급 토큰의 권한을 직접 검증한 결과는 아니다.

이번 추가 M0에서 별도 검사 에이전트가 사용자가 지정한 로컬 JSON을 읽기 전용으로 확인했다. 파일 존재, JSON 파싱, `installed` 구조와 필수 필드, 지정 프로젝트 일치, Google 인증·토큰 endpoint, loopback redirect 검사가 통과했다. 실제 프로젝트 ID·로컬 경로·client 값·원문은 공개 문서에 기록하지 않는다. 파일 복사·변경·외부 전송·로그인 없이 수행한 **로컬 구조 검사**다.

앱 로그인·계정별 동의·토큰 발급·갱신·Drive API 호출은 **미검증**이다. OAuth 파일 준비를 실인증 성공이나 M0 전체 PASS로 해석하지 않는다. 기존 연결 토큰 추출, 보관소 해제, rclone 인증 재사용도 수행하지 않았다.

## 4. M1 진입 및 종료 조건

OAuth 파일 준비가 완료됐으며 M1 시작에는 사용자 M1 범위 승인이 필요하다. [준비 현황](SETUP_PREREQUISITES.md)을 참고한다. M1은 아직 미착수이고 M0 전체 PASS를 선언하지 않는다.

M1 종료에는 새 앱에서 계정 A/B 각각 로그인·허용 범위 조회·토큰 갱신을 실제 검증하고, 지정 범위를 페이지 끝까지 스캔하거나 부분 실패를 명시해야 한다. 인증 취소·만료, allowlist 밖 탐색 차단도 검증한다. Codex 조회 성공으로 이 조건을 대체하지 않는다.

## 5. 이번 산출물과 검증 범위

사용자의 작업공간 커스텀 요구를 동일 프로젝트 설계에 추가했다. 작업공간 이름·로컬 루트, 계정과 Drive allowlist 선택, models/runs 저장 위치, 대시보드 위젯 배치·표시와 테마를 계획 대상으로 기록했다. 구체 선택값은 미확정이며 구현·기존 파일 이동·과거 산출물 가져오기를 승인한 것으로 해석하지 않는다. 상세 경계와 검증 목표는 [화면 계획](PLAN.md), [파이프라인](PIPELINE.md), [품질 게이트](QUALITY_GATES.md)에 있다.

이번 산출물은 이 보고서, 준비 안내, 갱신한 동일 프로젝트 계획 문서, 개인 allowlist·증거 기록이다. 동일 프로젝트 계획문서 갱신은 사용자 명시 승인 범위다. 모델 가중치·추론 결과는 생성하지 않았다.

공개 문서의 내부 링크와 개인 식별자 노출을 검사한다. 실제 입력·출력·의존 경로 전체를 검사한 상태가 아니므로 “재사용 없음 확인 완료”라고 단정하지 않는다. M3/M4에서 실제 준비·실행 경로와 파일 해시를 새로 검증해야 한다. 이전 프로젝트 구현·생성 결과를 이 문서의 원본으로 사용하지 않았다.
