# M3 첫 모델 준비 구현·검증 기록

기록일: 2026-10-16 · 버전: 0.3.0 · 판정: **승인된 M3 첫 모델 준비 구현·실자산·환경·독립 검증 완료**

## 승인·출처·범위

첫 모델의 읽기 전용 다운로드·바이트 검증·별도 환경 준비·공개 의존성 설치·구현·UI·테스트·문서·저장소 반영이 명시 승인됐다. 작업공간 커스텀, 다른 모델 자동 준비, 원격 GPU·공개 서비스 배포와 M4 이후 모델 로딩·추론·WAV 생성·비교는 포함하지 않는다. [승인 기록](APPROVALS.md)

대상은 `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, 공식 revision `85e237c12c027371202489a0ec509ded67b5e4b5`, 라이선스 Apache-2.0이다. 허용된 지정 Drive 모델 자산을 입력으로 사용하며 공식 manifest는 13개 파일·2,498,388,392 bytes를 기록한다. [고정 모델 원본](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice/tree/85e237c12c027371202489a0ec509ded67b5e4b5)

공식 상대 파일 경로·size·SHA-256은 공개 manifest에 포함한다. 개인 계정·Drive ID·인벤토리 전체 경로·사용자 절대경로·자격 증명·개인 목록 스크린샷은 공개하지 않는다. 기존 프로젝트 결과물·중단 실행의 부분 자산·생성 캐시를 새 성공 근거로 쓰지 않고 실행별 새 출력과 출처 기록을 남긴다. 같은 프로젝트의 명시 지정 메타데이터·허용 모델 가중치 및 필수 구성요소는 승인된 입력이다.

## 현재 검증 상태

| 확인 항목 | 현재 근거와 한계 |
|---|---|
| 공식 manifest 독립 비교 | 고정 revision의 LFS oid 2개와 비LFS 공식 파일 새 수신 11개의 size/SHA-256 비교, 13개 일치. 로컬 Drive 다운로드 성공 증거는 아님 |
| 독립 반례 | 최종 고정 코드에서 독립 반례 42개 통과 보고. checksum 이후 검사·잠금 guard·경로 위장·삭제 자산 stale-ready·환경 기록 stale-ready·Range/version·동시 인증·401 단일 갱신·429 재시도 등 수정 후 재검증 |
| 전체 Python 회귀 | 최종 고정 코드의 unittest 전체 72개 통과 보고. 실제 전량 자산 및 환경 검증과는 별개 |
| TypeScript·Vite·의존성 | 최종 SHA 열 레이아웃 수정 후 빌드 통과·npm audit 0건 보고. 전체 보안 보증은 아님 |
| 준비 UI | 1280·1440·1920·768 폭·키보드·대비 최소 4.70:1 확인 보고. 상단 진행률·수신/전체 bytes·현재 파일의 1440/768 추가 시각 확인, Enter 출처 접기·상태별 UI·고정 오류 33개 한국어 매핑 확인. 최종 실제 화면에서 동일 run의 13/13·100%·READY와 별도 runtime 준비·실행 미수행 확인. UI 환경 검사 running→finished/ready·RTX 3070·패키지 표시 확인. 최종 1440/768에서 SHA-256 64자 전체 표시·선택 가능, 768은 표 내부 스크롤만 유지 |
| 실제 지정 모델 다운로드 | 새 실행에서 13개·2,498,388,392 bytes 전량 수신·공식 manifest SHA-256 일치. 독립 검토도 정확한 13개 입력 상대경로·고유 source ID·revision·부분파일 부재 확인 |
| 공식 런타임 wheel | 새 공식 index SHA-256·HEAD size/ETag·다운로드 전량 SHA-256 독립 일치. torch wheel 2,862,053,390 bytes. 환경 전체 성공 증거는 아님 |
| 별도 환경 | Windows Python 3.10.11·97개 고정 버전 설치 완료, pip check 0건. 독립 오프라인 7개 import·RTX 3070 CUDA 12.8의 32×32 float32 행렬곱과 CPU 결과 대조 통과. 모델 로딩·추론은 미수행 |
| 새 패키징 | 기존 build/lib 캐시를 배제한 최종 새 staging의 PEP 517 wheel 통과. 현재 package 15개 파일의 raw SHA와 wheel 내용 일치, 최종 CLI·HTML·JS·CSS·preparation·probe·manifest 및 metadata 버전 0.3.0 확인 |
| 모델 로딩·추론·WAV | 수행하지 않음. M4 이후 미승인 |
| 독립 최종 검토 | 독립 최신 소스 72개 테스트·실자산·환경·최종 API 검증 통과. |

이 표는 담당 구현자와 독립 검토자가 이번 새 실행에서 보고한 최종 증거를 정리한 것이다. 문서 작성자가 실제 모델 바이트 다운로드나 환경 설치를 수행한 의미가 아니다. 진행률을 완료 근거로 사용하지 않고 실제 전량 파일·해시·환경·상태 검증으로 판정했다.

## 실패·중단과 보존

이번 프로젝트의 준비 시도 5개를 새로 대조했다. 앞선 미완료 4개는 보존했고 최종 성공 시도의 입력으로 재사용하지 않았다. 공개 별칭은 개인 Drive ID나 로컬 경로를 노출하지 않는다.

| 공개 별칭 | 보존한 결과 |
|---|---|
| prep-attempt-01 | Windows 상태 파일 공유 위반 후 프로세스 중단. 당시 저장 상태는 downloading·5개 검증·부분파일 1개. 저장 상태만으로 성공을 판정하지 않음 |
| prep-attempt-02 | UI 소유 실행으로 전환하는 조율을 위해 CLI 프로세스를 명시 중단. 당시 downloading·5개 검증·부분파일 보존. UI 취소 아님 |
| prep-attempt-03 | 초기 UI 서버 종료 후 중단. 당시 downloading·5개 검증·부분파일 보존. UI 취소 아님 |
| prep-attempt-04 | failed·preparation_io_failed·5개 검증·부분파일 보존. 동시 인증 잠금 경합을 실제 계정과 합성 반례로 재현해 수정했으나 해당 시도의 원 예외가 없어 직접 원인 확정으로 표현하지 않음 |
| prep-attempt-05 | 최종 새 실행: ready·13개 검증·2,498,388,392 bytes·부분파일 없음 |

실제 UI 취소 E2E는 수행하지 않았다. 취소 반례는 독립 합성 회귀의 통과 범위다. 실패·중단은 성공 상태로 표시하지 않으며 이전 시도의 부분 자산을 최종 수신·해시 성공으로 집계하지 않았다. 전송 최적화 후 고정 코드에서 Range·버전·인증 갱신·재시도 회귀를 다시 수행했다.

## 구현과 의존성

첫 모델만 지원하는 전용 준비 화면은 모델 파일 READY와 별도 runtime 상태를 구분하고 실행은 항상 미실행으로 남긴다. 모델 로딩·추론·WAV·비교 버튼은 제공하지 않는다. 새 출력 디렉터리·부분 파일·출처·해시 기록을 생성하고 디스크 부족·누락·전송 변화·해시 불일치·환경 실패를 차단 상태로 표시한다.

Drive 전송은 1 MiB 범위·8 workers로 최적화하며 Range 응답·수신 크기·자산 버전과 최종 SHA-256을 검증한다. 인증 동시 접근·401 갱신·재시도를 별도로 검사했다. 개발 중 전송 최적화는 측정된 다운로드 시간 보장이나 모든 네트워크의 성능 보증이 아니다.

공개 런타임 설치는 PyTorch 공식 CUDA 12.8 index 및 공개 qwen-tts 패키지를 사용한다. `scripts/download_runtime_wheel.py`는 선택된 Windows CPython 3.10 공식 torch wheel만 새 위치에 수신하고 공식 index의 SHA-256·ETag·Range를 확인하는 보조 도구다. qwen-tts의 Python 3.12 권장과 이번 Python 3.10.11 사용을 구분하며 실제 import/CUDA 결과로 지원 범위를 판단한다. 설치 완료한 97개 name==version을 `requirements-runtime.lock`에 기록했다. 공개·비공개 lock은 byte 단위로 동일하며 최종 raw SHA-256은 `744b3882453eca5dbeff875f51c3d03a7a859d1e82cc1ad643b53c8448a78857`다.

주요 환경 버전은 qwen-tts 0.1.1, torch/torchaudio 2.9.1+cu128, transformers 4.57.3, accelerate 1.12.0, soundfile 0.14.0, onnxruntime 1.23.2, gradio 5.49.1이다. 독립 검토는 `HF_HUB_OFFLINE`·`TRANSFORMERS_OFFLINE` 설정 아래 torch·torchaudio·transformers·accelerate·soundfile·onnxruntime·qwen_tts import를 새로 수행했다. CUDA 계산 검증은 작은 행렬연산의 실제 실행 근거이며 선택 모델의 가중치 로딩·음성 생성 성공 근거가 아니다.

SoX Python 패키지와 실행파일은 구분한다. 현재 SoX CLI는 설치하지 않았고 import 시 경고가 관찰됐다. 독립 검토의 공개 패키지 소스 추적에서는 25Hz 클래스 eager import가 경고를 발생시키고 실제 SoX 사용은 25Hz XVectorExtractor 경로에 있었다. 선정 고정 모델의 tokenizer config는 12Hz이며 CustomVoice의 12Hz decode는 torch 경로를 사용한다. 이 정적 확인은 선정 모델의 실제 추론 보장이 아니며 25Hz 확장·입력 리샘플 등의 경로는 검증하지 않았다. M4에서 실제 선택 모델 흐름을 검증해야 한다.

## 실행·입출력 기록

앱 CLI는 `preparation-status`, `prepare`, `runtime-check`를 제공하고 설치는 `scripts/setup_runtime.ps1`로 분리한다. 설치·확인 명령과 Windows PowerShell/pwsh 정책 구분은 [README](../README.md)를 따른다. 설치 스크립트 직접 실행은 미검증이고 동일 단계의 수동 실행·환경 결과를 검증했다. 정책 변경이나 우회는 수행하지 않았다. 환경 검사만으로 모델 적재·한국어 생성 품질을 확인했다고 주장하지 않는다.

새 준비 실행은 실행 ID별 자산 출력·manifest·소스 출처·진행 상태·파일 해시를 비공개 앱 위치에 기록한다. 공개 보고는 경로 별칭 `<private_app_home>`과 비식별 집계만 사용한다. 독립 반례·공식 manifest 비교도 이번 검토의 별도 신규 실행 기록에 보관한다. 최종 준비 실행 ID는 `f3a3965b8bc94dd7884f9d5298c119a1`이다. 독립 최종 API 대조는 같은 run의 `ready`·`configuration=complete`·`integrity=matched`·`runtime=ready`·`execution=not_run`·검증 파일 13개·오류 없음 상태를 확인했다. 구현 담당도 새 로컬 13개 SHA/size와 현재 Drive 메타데이터 13개를 입력 snapshot과 재대조해 일치를 보고했다. 구현 담당 확인과 독립 확인은 별도로 기록했다. 실행 환경의 editable 설치 metadata도 0.3.0으로 대조했다.

공식 manifest 비교·실물 해시·wheel·환경·최종 API·소스 해시와 전체 테스트 증거는 이번 비공개 검토 실행 기록에 보관한다. 이 보고서는 개인 Drive 원본을 공개하지 않는다. GitHub 게시 후 확정 커밋의 공개 파일 전문·기존 blob 보존·생성물/개인정보 제외를 다시 확인한다.

입력·출력·의존 경로 확인 범위는 이번 프로젝트의 지정 자산·구현·실행 기록이다. 확인이 끝나기 전 재사용 없음 확인 완료를 단정하지 않는다. 과거 다른 프로젝트 결과물 유입은 금지하며 기존 자료는 삭제·이동하지 않는다.
