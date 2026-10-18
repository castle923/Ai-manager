# M10 다종 모델 실행 진행 보고서

### candidate4·5의 시작 실패와 candidate6 수정

candidate4는 새 대상 설치 8,291개 파일 무결성을 통과했으나 앱 창 시작에 실패했다. 진단만 보강한 candidate5에서도 시작 실패를 보존했다. candidate5의 opt-in trace는 `home → SettingsStore → protect_directory → icacls`의 30초 timeout 호출 위치를 확인했다. WebView 초기화 전 단계이며, 채워진 디렉터리에 상속 ACL을 다시 적용하면서 자식으로 전파된 것이 정확한 지연 원인인지는 별도로 측정하지 않았으므로 가설로 남긴다.

candidate6은 Win32 API로 기존 root 디렉터리의 실제 owner·protected DACL·현재 사용자/SYSTEM의 정확한 두 full-control 규칙을 검사하고 일치할 때 재적용을 생략한다. 불명확한 ACL의 populated 디렉터리는 변경하지 않고 실패하며, 새 empty 디렉터리에만 기존 보호 절차를 적용하고 다시 검증한다. root의 계약 확인은 모든 자식 ACL을 전수 인증하는 것이 아니다. 전역 보안 설정을 변경하거나 보호 검사를 끄지 않는다.

명시적 opt-in 시작 진단은 단계·제한된 예외 종류·허용 module/line만 기록한다. 예외 원문·locals·실제 경로·계정·비밀값은 수집하지 않으며 16KiB·32 events로 제한한다. 진단 쓰기 실패가 원래 오류를 바꾸거나 시작 흐름을 가로막지 않도록 한다. 시작 진단과 worker의 별도 이미지 진단을 구분한다.

candidate6 소스 동결·native build·바이트 정합은 확인했고 전체 자동 회귀 280개 중 274개 통과·6개 skip, 관련 독립 CPU 13개 통과를 확인했다. candidate6는 새 설치본 8,292개 파일 검증과 실행 파일 SHA 일치, 같은 작업 영역의 실제 앱 창 진입을 확인했다. 현재 후보에서 새 TTS 생성·실제 취소·정상 저장, Whisper 전사와 합성 영상 TAPIR 추적을 확인했으며 LLM은 자원 gate 실패로 남긴다. 이번 새 A/B 양쪽 생성·native 재생 완료와 정상 종료·재시작 후 새 8개 기록 유지까지 확인했다. 선택된 기존 파일·인증 해시, 기존 DB 행 fingerprint·런타임 보존과 대표 STT JSON의 사용자 수동 정상 저장·해시 일치를 확인했다. 기존 22개 기록 조회는 보존된 과거 이력이며 새 실행 성공으로 계산하지 않는다. candidate4 설치 성공이나 이전 버전 모델 출력을 candidate6 실제 실행 성공으로 사용하지 않는다.


## 최신 통합 후보 상태 — 0.10.0 candidate6

**M10 전체 PASS 아님. 공개 프로그램 Release는 v0.7.0이며 로컬 candidate6는 별도 검증 후보다.** 이 절은 초기 개발 결과를 보존하면서 현재 후보의 변경·검증 범위를 구분한다. 새 Windows 실검증이 끝나기 전 과거 결과를 현재 성공으로 대체하지 않는다.

### 수정·로컬 검증

- 이미지 worker의 실제 검사와 앱의 정확 패키지 검사에 `torchvision` 계약을 일치시켰다. 실제 검사 함수의 전후 비교에서 패키지 dict 동등성이 false에서 true로 바뀐 것을 확인했다. 이미지 모델 로딩·생성 성공이나 과거 원격 실패의 유일 원인을 확정한 것은 아니다.
- 역할별 runtime root/base 연결과 검증된 기존 library-only 환경 재참조를 구현했다. lock·소유 기록·원래 기반 Python과 라이브러리 파일·동등 bytecode·격리 metadata probe를 확인하며, ready 기록만 믿거나 기존 환경을 복사/수정하지 않는다. 기존 candidate3 Python 기반은 계속 필요한 참조 대상이므로 보존한다.
- 작업 UI의 안내 상태와 실제 hard gate를 분리하고 모델 선택·현재 worker 출처·기록 호환성을 맞췄다. 현재 앱의 로컬 이미지 준비·생성은 미검증이다. 원격 GPU 성공을 이 상태에 합치지 않는다.
- 현재 source snapshot Python 회귀는 총 **280개 중 274개 통과·6개 skip**이다. skip은 호스트의 tracking 런타임 관련 항목이다. 별도 핵심 CPU 13개 독립 검토도 통과했으나 전체 280개에 중복 합산하지 않는다. 합성/CPU 검증과 실제 모델·GUI 실행은 별개다.
- 같은 snapshot의 TypeScript/Vite 및 native build가 통과했다. native manifest의 source 61개 SHA와 snapshot이 모두 일치하며 native payload 8,292개 파일의 해시도 확인했다. candidate4 새 대상 설치 무결성은 확인했으나 시작에 실패했으며 **candidate6 설치본의 명시한 항목별 실제 검증은 확인했고 제한은 남긴다**. 아래 이번 설치본의 새 실행 결과만 별도 판정한다.

### 이번 candidate6 실제 사용의 현재 결과

다음은 Windows 실검증 담당의 새 관측과 독립 reviewer의 항목별 감사에 근거한 요약이다. publisher가 GUI를 대신 조작하거나 과거 모델 출력을 재실행 근거로 사용하지 않았다.

| 항목 | 이번 실제 관측·판정 | 제한 |
|---|---|---|
| TTS 새 생성·정상 저장 | 새 0.6B 실행 성공, 426,284 bytes WAV. native 저장 대화상자에서 사용자가 정상 저장했고 원본/저장본 full SHA가 일치 | 자동 대화상자 조작 성공을 뜻하지 않음; A/B 전체 회귀와 별도 |
| TTS 실제 취소 | CUDA 로딩 뒤 running 상태·실제 소유 worker를 관측하고 UI 취소 후 cancelled/output null/소유 자식 0 확인 | 별도 GPU PID 샘플은 수집하지 않아 GPU 프로세스 단독 관측으로 확대하지 않음 |
| 저장 취소 | 사용자가 native 대화상자에서 취소, 앱의 취소 표시·대화상자 닫힘·새 저장 폴더 파일 0 확인 | 사용자 수동 취소와 앱 반영의 검증이며 자동 modal 조작 PASS가 아님 |
| Whisper | 이번 새 TTS에서 파생한 16kHz 입력을 새 실행해 전사 text 120 bytes·JSON 212 bytes 생성 성공. 대표 JSON을 사용자가 정상 native 저장해 212 bytes·원본 full SHA 일치 및 앱 완료 표시 확인 | 입력 대본과 차이가 있어 정확 전사·품질 우수로 판정하지 않음 |
| TAPIR | 이번 새 16프레임 합성 영상·점 1개로 추적 성공, 출력 해시 검증 | 합성 표본이며 실제 촬영 영상·가림·다수 점의 품질 검증 아님 |
| LLM | 준비된 격리 환경에서 새 실행했으나 `memory_budget_unavailable`, 출력 0·소유 자식 0 | RAM/GPU/disk 공통 gate이므로 단일 RAM 원인으로 확정하지 않음; 응답 생성 PASS 아님 |
| 새 TTS A/B | 같은 새 text·seed·공통 조건, 양쪽 cold 실행으로 A 303,404 bytes·6.32초 / B 192,044 bytes·4.00초 WAV 생성 성공. 각 실행 source 13개 SHA 일치 및 각 native 재생 완료 | 단일 비교 표본이며 음질 우열을 평가하지 않음 |
| 기록·재시작 | 기존 22개 + 이번 새 8개 = 30개. 새 8개 ID/status와 STT 상세 SHA를 대조하고 정상 종료·소유 자식 0 뒤 같은 EXE SHA로 같은 home 재시작·창 진입, 기록 30개/새 8개 유지·STT 상세 재선택 SHA 일치 확인 | 기존 22개 UI 전수 ID 대조·모든 필터 검증은 아님. 상세 선택 자동 복원이 아니라 사용자가 다시 선택한 확인 |

이번 TTS 생성 원본과 정상 저장본 SHA-256은 `9081b5500a215bee3f8e0ae22f62dd7f09f9868dac89f597007cf777deebb540`이다. 실행 출처 13개 코드 해시는 현재 설치 candidate6와 모두 일치했다. 실제 입력·출력 원문, 개인 경로와 원시 실행 로그는 비공개에 보존한다.

이번 추가 저장한 STT JSON의 SHA-256은 `8ec797d22f1358faefdd08302c3b619c991ad1cec75058914db428d20da2034f`로 원본과 같다. STT text는 `83624b478050f2427212774ccdace6d44cecaa3d33e84d5c27e3de807789a189`, TAPIR tracks JSON은 `fc877c71230e6880bef24dd8a13dd5503ad7c79f1db98762e73d81089bebdae1`, 표시 PNG는 `8279fa55411b84e39f815b6fff08d2a305ab04ec211116bc8cfc4fa7b53fea67`다. 새 A/B WAV는 각각 `78d6bdf89035aef4f32d067949127b7227db46581ac93631f889c548178d3e8c`와 `dec5f971f1489cb2dd338f1171dca2712670772ff3f0b287f8fcba647e061a10`이다. 파일 내용·품질의 우수성을 해시로 판단하지 않는다.

### 관리 상태·보존 확인 범위

등록된 세 모델 중 Whisper/TAPIR는 verified, Llama는 이번 자원 gate 실패 상태로 표시되어 환경 ready와 모델 실행 결과가 혼동되지 않았다. 기록 30개는 과거 22개와 새 8개를 합한 수이며 새 8개만 이번 상태 대조 대상이다. 기존 선택 파일 116개와 인증 파일 2개의 SHA는 변경되지 않았다. 이는 선택한 보존 대상의 확인이며 모든 기존 파일·모든 DB 행 보존을 전수 검증했다는 뜻은 아니다. 기존 registry model 3행과 reference 3행은 누락·변경 없이 fingerprint가 유지됐고 inventory는 0행 상태를 유지했다. 검토한 runtime 경로 10개는 각각의 기존 존재/부재 상태와 해당 pyvenv.cfg가 유지됐다. 이미지 역할의 Python 부재도 그대로이며 10개 venv가 모두 존재한다는 뜻은 아니다. 원래 candidate3 Python 기반을 보존했다. 새 runtime 설치·모델 다운로드는 0이다. 이 확인은 기록한 DB·경로·파일 범위이며 모든 PC 자료 전수 보존을 뜻하지 않는다.

### 패키지와 게시 경계

후보 버전은 0.10.0 candidate6다. ZIP 113,035,952 bytes·SHA-256 `00c87ce607ded28fb578aeaf1654f99c08dd7e93696804d698f7b54afbbcc9a1`, 실행 파일 SHA-256 `40155648d55131667cc3a8d1839db3dd0ad7e93b6059d78dee55faa44c4adfa2`, native manifest SHA-256 `1ef0471ff1159c88ed7fb9f9b818e9db6059198d53b7922f1b0b0b495d840e8b`로 후보를 식별한다. 공개 설치 자산으로 배포한 상태가 아니며 새 Release/tag는 만들지 않았다.

선택 게시 검토 범위는 source/frontend/adapter manifests·locks/관련 tests/build script와 공개 안내다. 생성 static은 Git에 넣지 않고 npm lock→새 UI build→wheel/native 순서로 재현한다. native manifest source 61개와 게시 delta 62개는 다른 집합이다. 내부 HQ worker와 관련 테스트는 후보 소스 집합 정합을 위해 포함하지만 앱 통합 기능이나 Windows 고품질 지원을 주장하지 않는다. 설치·빌드 순서는 [설치 안내](M10_INSTALL.md)를 따른다. 최종 공개 안내는 검증 결과를 반영한 후속 문서 갱신으로, native candidate6에 포함된 문서와 내용이 다를 수 있다. 실행 소스·EXE를 재빌드하거나 바꾼 것은 아니며 새 안내가 기존 후보 ZIP 안에 이미 들어 있다고 주장하지 않는다.

개인 계정·Drive ID·인증·모델·registry/DB 원문·원시 로그·개인 절대경로·실제 입력/출력은 공개하지 않는다. 기존 공개 AGENTS와 과거 RunPod 보고서 전체 이력을 보존한다. [원격 GPU 보고](M10_RUNPOD_REPORT.md)는 별도 Linux 실행의 결과이며 로컬 이미지 PASS나 앱 원격 GPU 연동 완료가 아니다.

### 현재 남은 실제 검증

| 항목 | 현재 판정 |
|---|---|
| candidate6 동결 소스→빌드·manifest 정합·새 설치·실제 앱 창 진입 | 확인; 새 모델 실행 gate와 별도 |
| 모델 선택·새 실제 실행 | TTS/Whisper/TAPIR의 명시 표본 확인; LLM 자원 gate 실패·이미지 로컬 미검증 |
| 실행/대기 취소·해당 worker 정리 | TTS running 취소·소유 자식 정리 확인; 모든 유형·대기 경로 검증으로 확대하지 않음 |
| 정상 native 저장·취소·저장본 SHA | 이번 TTS WAV 및 대표 STT JSON 사용자 수동 정상 저장·SHA 일치, TTS 저장 취소 확인; 추가 TAPIR PNG·A/B 저장 변형·덮어쓰기 경계는 미검증 |
| 현재 후보 기록·결과 및 정상 재시작 | 이번 새 8개 상태·STT 상세 및 재시작 후 유지 확인; 기존 22개 UI 전수 대조/모든 필터 미검증 |
| 기존 TTS 두 모델의 새 회귀 | 동일 새 조건의 양쪽 cold 생성·source SHA·native 재생 완료; 품질 우열 미평가 |
| Windows 로컬 이미지 실행·생성 | 미검증; 원격 결과로 대체하지 않음 |
| M10 전체 완료·새 public Release | 미완료 / 게시하지 않음 |

아래 초기 상태·실측·미확정 원인은 해당 시점의 기록으로 보존한다. 최신 후보 통과 증거와 합산하거나 초기 모델 출력을 새 candidate6 결과로 표시하지 않는다.


## 초기 작성 시점의 계획·상태 기록

아래 본문은 초기 시점의 계획·관측과 미완료 항목을 보존한 기록이다. 위 candidate6 최신 결과가 현재 검증 범위를 설명하며, 아래 초기 pending 문구를 현재 미수행 상태나 현재 성공 근거로 대신 사용하지 않는다.

기준일: 2026-10-18 · **초안 / 구현·검증 진행 중 / M10 전체 PASS 아님**

M10은 Whisper STT·Qwen Image 2.1·Llama 3.1 8B·TAPIR 추적의 네 별도 어댑터를 구현한다. 아래는 현재 실행 담당자가 전달한 중간 상태이며 문서 담당자의 독립 실측이나 최종 동결 패키지 검증으로 표현하지 않는다. 새 증거와 독립 검토에 따라 갱신한다. [계획과 완료 게이트](M10_PLAN.md)

## 이번 실행의 경계

같은 Ai-manager 소스·문서는 승인된 후속 갱신 입력이다. 모델은 사용자 지정 Drive 자산을 우선하고 승인된 Llama 공식 누락 구성만 보완한다. 새 입력·중간 결과·출력·환경·로그는 M10 전용 실행 영역에서 생성한다. 과거 M9 A/B·WAV·로그·스크린샷·측정값·배포물을 이번 성공 근거로 재사용하지 않는다.

공개 기록에는 모델/라이브러리 정보와 비식별 결과 요약만 남긴다. 상세 출처·개인 경로·파일 ID·입력 본문·원시 로그·인증 정보는 비공개에 보존한다. 문서 검토는 전체 입력/출력/의존 경로 감사와 다르므로 이 초안만으로 “재사용 없음 확인 완료”를 단정하지 않는다.

## 자산·환경·실행 상태

| 대상 | 이번에 확인한 중간 상태 | 아직 확인하지 않은 범위 |
|---|---|---|
| Whisper | Drive 11개 파일 1,622,443,339 bytes 새 다운로드·전량 SHA-256·별도 전량 재읽기 검증. 초기 소스에서 이번 새 TTS → 이번 16 kHz 변환 → 등록 Whisper 새 실행 성공, 전사 대본 UTF-8 정확 일치 보고 | 최종 패키지·독립 창 표시·오류/취소·정상 저장·재시작의 전체 게이트 |
| BootsTAPIR v2 | Drive checkpoint 218,886,140 bytes 새 다운로드·SHA-256 재검증. 실제 checkpoint의 218개 state 안전 CPU 로딩, 별도 추적 런타임 자동 테스트 9개와 초기 소스의 새 GPU 추적 성공 보고 | 최종 수정판·패키지·독립 창 표시·오류/취소·정상 저장·재시작 게이트 |
| Llama 3.1 8B | 지정 Drive 3개 파일과 승인된 공식 7개 파일을 새 통합 폴더에 준비. 총 10개·16,069,722,669 bytes 전량 크기·SHA-256·복사본 재읽기 검증, 추가/누락 0. 초기 소스의 새 LLM 짧은 응답 성공과 합성 테스트 8개 통과 보고 | 최종 패키지·UI·오류/취소·정상 저장. 선행 CPU 8 GiB 배치의 자원 감시 실패 원인은 미확정 |
| Qwen Image 2.1 | Drive 필수 구성 24개 파일 33,131,601,593 bytes의 메타데이터 확인. 이미지 worker 합성 테스트 8개 통과 보고. 초기 Python 3.11.17 전용 환경의 고정 의존성·pip check·pipeline import-only 점검 완료 | 모델 다운로드·전체 해시·실제 생성. 요구 GPU 여유 7 GiB / RAM 여유 18 GiB보다 실제 여유가 작아 두 gate 미충족·실행 차단 상태 |

다운로드 진행률이나 인증 성공을 실행 성공으로 해석하지 않는다. 표의 용량은 명시한 모델 자산 범위의 집계이며 모든 의존성·출력·설치 공간의 합계가 아니다.

| 공식 모델 출처 | 이번 고정 revision | 라이선스 |
|---|---|---|
| [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo/tree/41f01f3fe87f28c78e2fbf8b568835947dd65ed9) | `41f01f3fe87f28c78e2fbf8b568835947dd65ed9` | MIT |
| [google/tapnet](https://huggingface.co/google/tapnet/tree/5d3fb48e76c5422841e38501514121e251beabb7), [공식 checkpoint 설명](https://github.com/google-deepmind/tapnet) | `5d3fb48e76c5422841e38501514121e251beabb7` | checkpoint Apache 2.0 |
| [meta-llama/Llama-3.1-8B-Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/tree/0e9e39f249a16976918f6564b8830bc894c89659) | `0e9e39f249a16976918f6564b8830bc894c89659` | [Llama 3.1 Community](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/0e9e39f249a16976918f6564b8830bc894c89659/LICENSE) |
| [Qwen/Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1/tree/d26bb61231c349cf6b7896fa83353113880e1ba3) | `d26bb61231c349cf6b7896fa83353113880e1ba3` | [Qwen Research](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/LICENSE) |

BootsTAPIR v2 checkpoint의 이번 SHA-256은 `8493c7a69e02c85b9382fbb3c7b8b539b36bc08ede744b9e99feb739a0129f4b`다. 각 파일의 개인 Drive 매핑과 전량 manifest는 비공개 기록으로 관리한다.

초기 Whisper의 전달된 실측은 로딩 1.172초·추론 1.140초·전체 9.704초, PyTorch peak GPU allocated 1,675,869,696 bytes다. 이번 초기 소스의 단일 표본이며 전체 장치 VRAM·모든 입력 성능·품질 순위를 뜻하지 않는다. 최종 패키지의 성능 측정이나 네 유형 모두의 성공으로 확대하지 않는다.

초기 TAPIR는 이번 새 합성 영상 8프레임·8 fps·첫 점 1개로 GPU 추적 성공을 보고받았다. 로딩 0.984초·추론 0.797초·전체 4.719초, PyTorch peak GPU allocated 477,803,008 bytes다. 새 합성 정답과의 오차 평균 0.1863 px·최대 0.2947 px는 이 단일 단순 표본의 결과이며 실제 촬영 영상·가림·다수 점·일반 추적 품질의 성능 보장이 아니다. 최종 패키지·UI·native 저장의 증거와 구분한다.

초기 Llama 새 실행은 CPU 4 GiB·GPU 3 GiB의 가중치 배치 계획과 디스크 offload 조건에서 EOS로 종료한 2 token·2 byte의 짧은 응답을 생성했다. 추론 20.734초·PyTorch peak GPU allocated 약 4.04 GB를 보고받았다. 배치 계획은 실행 전체 메모리 quota가 아니며 실제 peak가 가중치 배치 예산을 넘을 수 있다. 이 표본은 응답 품질·긴 입력·일반 메모리 적합성의 증거가 아니다. 선행 CPU 8 GiB 조건의 로딩 자원 감시 실패는 원인 미확정으로 보존하고 성공 실행으로 덮어쓰지 않는다. 최종 Windows 패키지·UI·취소·저장은 아직 미완료다.

## 구현·독립 반례 상태

공용 실행 슬롯·입력/출력 유형·native 저장·registry/history·네 worker·자원 감시 경계에서 독립 반례를 발견하고 수정 fixture 통과를 확인한 중간 상태를 전달받았다. 개발 소스 최신 자동 테스트는 총 237개 중 231개 실행 통과·호스트 런타임의 추적 관련 6개 skip으로 보고받았다. 별도 추적 전용 환경의 9개 실행 통과는 범위가 달라 합산하지 않는다. 초기 합성 테스트와 fixture 통과는 실제 모델 E2E를 대신하지 않는다. 최종 수정판·패키지에 대한 전체 자동 테스트 집계와 독립 재검증은 아직 확정하지 않았다.

현재 구현 계약은 다음과 같으며 최종 앱 검증과 동일하지 않다.

- STT: 16 kHz mono PCM16 WAV, 최대 30초·960,128 bytes를 받고 전사 JSON/TXT를 만든다.
- LLM: 새 UTF-8 입력 최대 8 KB, 템플릿 256 token 제한·greedy 최대 신규 64 token으로 응답 JSON/TXT를 만든다. CPU/GPU 배치 계획과 RAM·VRAM·디스크 사전 검사 및 소유 worker RSS 감시는 실제 모델 실행으로 추가 검증해야 한다.
- TAPIR: 새 MP4 최대 5 MB·32프레임·20초와 첫 프레임의 정규화 점 1–8개를 받고 tracks JSON과 768×280 표시 PNG를 만든다.
- 이미지: 512×512·4 steps·seed 0·CFG 4로 PNG와 메타데이터 JSON을 만드는 제한 실험이다. 일반 이미지 품질 평가나 모든 크기 지원을 뜻하지 않는다.

새 task run은 registry generation/fingerprint와 연결하고 선언된 모든 모델 파일을 실행 전에 해시 검사한다. 공용 슬롯은 같은 home의 TTS와 유형별 worker 점유를 조정하며 서로 다른 home 전체의 전역 GPU 잠금을 뜻하지 않는다. 기존 TTS API·두 모델 비교·DB schema는 유지하는 방향이다. 입력 MIME/내용/디코딩 경계·출력 해시·native 확장자·덮어쓰기 금지·reparse·취소/오류를 검증한다. 현재 다른 유형의 기본 런타임은 Transformers 4.57.3 / Torch 2.9.1 CUDA 12.8이며 이미지 전용 런타임은 분리 준비 단계다.

Windows 경로 길이 오류는 짧은 새 전용 home 경로로 정상 해결하는 방향을 적용했다. 실패 환경은 보존하고 OS 보안 설정을 변경하지 않는다. 이 조치는 모델 실행·설치 전체 완료의 근거가 아니다.

## 라이선스와 자원 제한

Qwen 이미지 지정 모델의 공식 연구용 라이선스에 따라 연구·평가·개인 실험 범위로 다룬다. 상업 사용 가능으로 표시하지 않는다. 일반 offload API 존재와 현재 PC에서 해당 모델 생성 성공은 별개다. 메모리 gate를 충족하지 못한 상태에서 성공을 추정하지 않으며 모델 축소·다른 모델·원격 GPU로 자동 대체하지 않는다.

Llama의 gated 접근·인증 성공은 필요한 파일을 받을 권한의 확인일 뿐 구성 충족·무결성·로딩·생성을 보장하지 않는다. 각 공식 라이선스의 조건은 위 고정 출처를 따르며 모델 사이에 동일한 이용 권한을 가정하지 않는다.

## 남은 최종 검증

| 게이트 | 현재 판정 | 필요한 새 증거 |
|---|---|---|
| 네 모델 자산·revision·해시·의존성 확정 | 부분 완료 | Llama 전량 통합 해시·초기 이미지 분리 의존성/import 점검 완료. 이미지 실제 자산·자원 조건과 최종 패키지 연결 검증은 남음 |
| 네 어댑터 실제 새 출력 | 부분 완료 | 이미지 실제 실행, 초기 Whisper·TAPIR·짧은 Llama를 포함한 각 유형 최종 수정판 재검증 |
| 오류·timeout·취소·자원 정리 | 부분 구현/합성 검증 | 실제 패키지에서 유형별 실패·대기/실행 취소와 worker 종료 확인 |
| 최종 Windows 패키지·독립 창·정상 저장 | 미완료 | 동결 소스·새 패키지·새 설치본 연결, 각 결과 표시·native 저장본 무결성 |
| 재시작·기록/결과 보존 | 미완료 | 현재 최종 패키지의 정상 종료/재시작과 경로·상태·해시 대조 |
| 기존 TTS 두 모델 새 A/B 회귀 | 미완료 | 이번 새 입력·비교 ID·두 run, 재생·저장·무결성의 새 증거 |
| UI·독립 검토·게시 검토 | 진행 중 | 한국어·대표 폭·키보드·상태 정합, 독립 반례 종결, 정확한 공개 allowlist·비식별 검토 |

후보 버전 0.10.0 반영과 패키지 준비, 이미지 전용 의존성 설치/import-only probe는 승인 범위다. 고정 이미지 diffusers가 Python 3.11 이상을 요구해 Python 3.10 설치가 정상 거절된 기록을 보존한다. TTS·Whisper·TAPIR·LLM의 번들 CPython 3.10.22 기반은 유지하고 이미지 전용 Astral CPython 3.11.17+20261009를 별도 동봉·격리한다. 이미지 Python 공개 archive 48,233,938 bytes·SHA-256 `4d307648d2fe5f8d927e10380cc33eb7afd8a34a7efe0ed786b5860b5f2d3408`을 전량 검증했다.

이번 비공개 `image-import-only-probe.json`을 직접 확인했다. 초기 이미지 환경의 Python 3.11.17·Torch 2.9.1+cu128·Transformers 5.17.0·diffusers 0.41.0.dev0에서 `QwenImage21Pipeline` import가 성공했다. 구현 담당자는 설치 로그의 pip check 정상 종료도 확인했다. pipeline 소스 SHA-256은 `e75e4ce38d38e194edaac818bba99b2115b4bb2bfdbd15ce03a2813b0fe8856c`이며 실제 호출 signature와 전체 전이 패키지 버전 목록을 비공개에 기록했다. probe는 PATH를 Windows System32만으로 제한한 상태다.

동일 probe의 RAM 여유는 12,148,547,584 bytes(약 12.15 GB)로 18 GiB(19,327,352,832 bytes)에 못 미치고 GPU 여유도 7,459,569,664 bytes로 7 GiB(7,516,192,768 bytes)에 못 미쳐 실제 자원 gate는 false다. import 성공만으로 모델 로딩·실제 이미지 생성을 완료 처리하지 않으며 모델 가중치 다운로드·실제 생성은 0이다. 초기 별도 환경과 최종 독립 배포의 증거를 구분하고 기존 TTS 환경을 보존한다.

현재 보고서는 M10 중간 결과를 검토하기 위한 초안이다. 소스 반영·프로그램 Release·M10 전체 완료를 각각 구분한다. 기존 공개 v0.7.0 Release와 이전 검증 이력은 보존하며 새 태그·Release는 이 초안 작성으로 생성하지 않는다.
