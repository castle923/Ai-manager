# 2026-10-23 Colab 모델 관측과 감시 종료 회귀

기준 소스: `e0df07f2179b208cfec072da7e869ea40c5cc48e`, 제품 버전 `0.19.0`. 이 문서는 같은 프로젝트의 지정된 비공개 실행 증거를 읽어 비식별 요약한 기록이다. 문서화·종료 감시 수정 작업에서 모델을 다시 실행하지 않았으며 새 다운로드·유료 API 호출·Drive 접근을 하지 않았다. 과거 실측과 이번 합성 회귀를 서로 다른 검증으로 구분한다.

## 판정의 세 층

| 검증 층 | 판정과 범위 |
|---|---|
| 모델 엔진 smoke | Llama INT8의 단일 짧은 입력 생성은 성공. Qwen FP32 두 크기와 Kokoro 직접 음소 입력의 별도 엔진 관측은 아래 표 범위에서 성공 |
| 종료 감시 수정의 오프라인 회귀 | 30개 통과·실패/skip 0. 기존 20개와 신규 결정적 회귀 10개다. 원격 GPU·모델 실행 결과를 대신하지 않는다 |
| 문서의 증거 구분 | 엔진 성공·감시 미확정·합성 회귀를 분리하고 원문 출력·개인 경로·계정·Drive ID·원시 로그는 공개하지 않는다 |

## Llama INT8 단일 실행 관측

고정 모델은 Llama-3.1-8B-Instruct revision `0e9e39f249a16976918f6564b8830bc894c89659`다. 사용자가 제공한 결과 텍스트에서 보존한 result·phase·watchdog 요약을 대조했다. 이번 문서 작업은 라이브 VM·원격 결과 파일 또는 모델 바이트를 독립적으로 다시 검사한 것이 아니다.

| 항목 | 제공 증거의 관측 |
|---|---|
| 실행 범위 | 무료 T4의 INT8 r02, 단일 합성 입력·생성 호출 1회 |
| 생성 | 입력 41토큰, 새 출력 3토큰의 짧은 인사, EOS 도달, 길이 상한 미도달 |
| 양자화·배치 | Linear 224개 LLM.int8, 나머지 FP16. parameter 291개 모두 GPU, CPU·disk offload 없음 |
| 단계 | hash 시작/완료 → load 시작/완료 → generate 시작/종료 → done |
| 로딩·생성 시간 | 각각 69.2316초·1.7688초 |
| GPU 최대 메모리 | allocated 10,087,137,280 bytes, reserved 10,412,359,680 bytes |
| 의존성 | Torch 2.11.0+cu128, Transformers 4.57.3, Accelerate 1.12.0, safetensors 0.8.0, bitsandbytes 0.50.2 |

이 범위의 **엔진 smoke는 성공**이다. 다만 원래 watchdog은 `stopped / worker_identity_changed`로 끝났고, gate는 열렸으며 남은 소유 프로세스는 0이었다. cleanup 측정 오류는 false지만 `worker_returncode`가 보존되지 않았다. **정상 OS 종료코드 0과 전체 감시 PASS는 미확정**이며 엔진 결과로 이를 덮어쓰지 않는다.

관측된 최대 owned RSS는 6,546,640,896 bytes로 당시 cap 7,289,925,632 bytes보다 작았다. 최소 OS 가용 RAM 8,754,601,984 bytes와 최소 cgroup 여유 2,795,827,200 bytes는 각각 2 GiB floor보다 높았다. 제공 요약에서 메모리 floor에 따른 중단은 관측되지 않았다. 이 감시는 표본 기반이며 OS 메모리 상한 보장이나 모든 순간의 측정이 아니다.

종료 경쟁은 가능한 설명이다. 기존 감시에서 `child.poll()`로 생존을 확인한 뒤 별도로 identity를 검사하므로 그 사이 정상 종료나 zombie 전환이 일어나면 identity가 없어질 수 있다. 완전한 result·phase done·남은 owned 0은 이 가능성과 부합하지만 이번 실행의 identity 변경 원인을 확정하지 않는다. 원본에 없는 종료코드를 후속 회귀로 복원할 수 없다.

result 내부 `memory_prediction.model_loaded=false`와 `full_weight_SHA_verified=false`는 로딩 전 메모리 예측 helper의 선언값이다. 실제 load 완료·generate 종료·done과 다른 범위의 metadata이며 실행 실패 판정으로 해석하지 않는다. 전체 가중치 SHA 검증은 앞선 다운로드 및 worker 선결 계약에 근거한 기록이고 이번 문서 작업에서 바이트를 다시 읽어 확인한 것이 아니다.

## 별도 TTS 실행의 한정 관측

같은 날 각 고유 실행의 LOCAL_SUMMARY와 필요한 result를 읽었다. 아래는 Llama 결과에서 추론하거나 이전 제품 테스트로 대체한 결과가 아니다.

| 모델·실험 | 확인된 단일 실행 결과 | 한계 |
|---|---|---|
| Qwen3-TTS 0.6B FP32 | T4·FP32·sdpa, 로딩 2.630초·생성 16.997초, EOS 도달. WAV 6.56초·24 kHz·mono, 로컬 독립 readback 통과·clipped samples 0 | 청취 품질·FP16 동등성·앱 통합 미검증 |
| Qwen3-TTS 1.7B FP32 | T4·FP32·sdpa, 로딩 3.440초·생성 9.906초, EOS 도달. WAV 3.92초·24 kHz·mono, 로컬 독립 readback 통과·clipped samples 0 | 청취 품질·FP16 동등성·앱 통합 미검증 |
| Kokoro 직접 음소 FP32 | T4·FP32, single forward, WAV 1.575초·24 kHz, 로컬 독립 readback 통과·clipped samples 0 | 직접 음소 입력 엔진 smoke만 확인. 전체 텍스트→G2P·청취 품질·Ai Manager adapter 통합 미검증 |

이 TTS 실행들의 비공개 요약에는 공식 UI의 연결 해제·삭제 및 활성 세션 없음 관측이 남아 있다. 무료 계정·구매/유료 CU 미선택이라는 UI 관측과 실제 공급자 청구서 확인은 구분하며 청구서는 미측정이다. 해당 종료 관측을 Llama의 종료코드나 실제 GPU 삭제 증거로 옮겨 쓰지 않는다. Python worker의 네트워크 audit도 OS 전체 외부 통신 측정이 아니다.

## 이번 수정과 새 오프라인 검증

수정 대상은 저장소의 canonical 소스 `scripts/colab/llama_watchdog.py`이며 회귀는 `tests/test_colab_watchdog.py`다. identity가 없어졌을 때 같은 `Popen`의 종료를 다시 확인한다. `_record_confirmed_exit()`는 gate가 열렸고 종료코드가 0이며 확인된 소유 자손이 없을 때만 completed로 분류한다. 살아 있는 PID의 identity 변경과 계속 실행 중인 소유권 불명은 STOP을 유지한다. `finally`의 `final_worker_returncode`도 보존하며 기존 중단 사유를 덮지 않는다.

기존 동결 notebook·현재 Colab의 코드를 변경하거나 재실행하지 않았다. 현재 업로드된 notebook이 자동으로 교체되는 변경도 아니다. 수정된 소스의 실제 Colab 실행은 미검증이며 원본 notebook의 종료 결과를 소급해 성공으로 바꾸지 않는다.

기존 개발 venv의 Python으로 저장소 루트에서 다음 명령을 실행했다. 새 합성 프로세스·격리 자료만 사용하고 실제 Llama·TTS를 재실행하지 않았다.

```powershell
python -m unittest discover -s tests -p test_colab_watchdog.py -v
```

| 실행 | 실제 결과 |
|---|---|
| 구현자 최종 타깃 회귀 | 30개 통과·실패/skip 0, 6.900초. 실행 전후 소스 동일 |
| 부모 독립 타깃 회귀 | 30개 통과·실패/skip 0, 6.858초 |
| 원본 대비 결정적 red/green | 원본 모듈로 종료 경쟁 2개 실패·오류 0 → 수정본에서 같은 2개 통과. 원본 파일은 불변 |

30개는 기존 20개와 신규 결정적 회귀 10개다. 신규 검증은 identity 소실/오래된 생존 관측 사이 종료, nonzero 종료, gate 전 종료, 살아 있는 PID 재사용, 계속 살아 있는 소유권 불명, 남은 소유 자손, OS/cgroup floor·deadline·로그 오류의 우선 처리를 확인한다. 최종 종료코드가 중단 사유를 덮지 않는 것도 검사한다. red/green은 동결 원본을 변경하지 않고 모듈을 주입해 같은 종료 경쟁을 재현한 결과다.

독립 정적 검토는 GO이며 부모의 새 타깃 실행도 통과했다. 이 명령은 CPU 합성 watchdog 타깃 검증으로 제품 전체 회귀는 이번에 실행하지 않았다. 과거 전체 회귀의 수치를 이번 결과로 옮겨 쓰지 않는다.

## 보존·미검증 범위

지정된 비공개 결과 요약만 문서 근거로 읽었고 개인 home·인증·키·DB·모델 자산을 조사하거나 변경하지 않았다. 기존 원본 worker·advisor·resume과 기존 실행 결과는 보존한다. 공개 문서는 입력·출력 원문, WAV, 모델, 로그 또는 실제 개인 경로를 포함하지 않는다.

장문·한국어 대화 품질·일반 성능·양자화 전후 동등성·모든 입력/환경·Ai Manager 실제 모델 통합·수정된 watchdog의 Colab 실제 모델 실행은 미검증이다. 현재 짧은 smoke 시간은 벤치마크나 성능 보장이 아니다. 이번 소스·문서 작업은 새 Release·설치 패키지 게시·원격 GPU 실행·추가 모델 실행 승인이 아니다.
