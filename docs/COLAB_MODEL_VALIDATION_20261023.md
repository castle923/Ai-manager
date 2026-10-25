# 2026-10-23 Colab 모델 관측과 감시 종료 회귀

기준 소스: `e0df07f2179b208cfec072da7e869ea40c5cc48e`, 제품 버전 `0.19.0`. 이 문서는 같은 프로젝트의 지정된 비공개 실행 증거를 읽어 비식별 요약한 기록이다. 문서화·종료 감시 수정 작업에서 모델을 다시 실행하지 않았으며 새 다운로드·유료 API 호출·Drive 접근을 하지 않았다. 과거 실측과 이번 합성 회귀를 서로 다른 검증으로 구분한다.

## 2026-10-25 종료 확인 수정 guard의 새 무료 T4 실제 검증 — 최신 상태

이번 별도 새 실행은 **단일 엔진 smoke와 수정 guard의 정상 완료를 확인**했다. 아래의 실제 Colab 미검증·로컬 준비 한정·이전 guard STOP 표기는 각 작성 시점의 이력이다. 앞선 `stopped / worker_identity_changed` 결과는 보존하며 이번 결과로 소급 변경하지 않는다.

실행 guard SHA-256은 `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`다. 원본 packet `5796fff3f78ad7fd915da99c7750d488c4ef82457dc877528658f26751a6e5c1`(11셀·코드 6개·내장 자산 9개)은 불변이다. Drive의 별도 새 실행본은 정상 UI에서 코드 6개와 안내 Markdown만 구성했고 코드 source 해시를 검증했다. packet 파일 해시와 실행본 코드 source 검증을 구분한다. 무료 계정·구독 없음·유료 CU 0을 UI에서 확인한 범위이며 유료 API 호출은 0회다. 공급자 청구서 감사 결과는 아니다. 실행용 확인·승인·세 허용값은 모두 True였고 자동 재시도는 false다.

증거 출처는 이번 실행의 `download-completed.private.json`, `watchdog-completed.private.json`, `phase-completed.private.json`, `file-result-check.private.json`, `runtime-ready.json`, `run-execution-flags-source.json`이다. 지정된 로컬 비공개 증거를 직접 읽어 아래 필드를 대조했다. 이 문서 갱신에서 원격 VM·OS 상태 또는 모델 바이트를 독립 재검사하거나 모델을 실행한 것은 아니다. helper의 `guard_clean_completion_evidence=true`만으로 판정하지 않고 실제 guard의 상태·사유·두 종료코드·남은 owned 수·cleanup 측정 오류와 phase/result 필드를 확인했다.

| 항목 | 새 실제 실행의 관측 |
|---|---|
| 다운로드 | 고정 모델 10파일·16,069,722,669 bytes, 전체 SHA-256 true·token_saved false |
| 컨텍스트·단계 | context·root·work 검증 모두 true, hash_begin → hash_complete → load_begin → load_complete → generate_begin → generate_end → done |
| 엔진 | `single_Llama_LLM_INT8_GPU_smoke_pass`, 생성 1회·입력 41토큰·새 출력 3토큰·EOS true·길이 상한 미도달 |
| 양자화·배치 | 8비트 Linear 224개·GPU parameter 텐서 291개, CPU·disk offload 없음 |
| 시간 | 로딩 70.153177724초·생성 2.018226058초 |
| GPU peak | allocated 10,087,137,280 bytes·reserved 10,412,359,680 bytes |
| guard 완료 | `completed / worker_exited`, gate true, worker_returncode 0·final_worker_returncode 0·remaining_owned_count 0·cleanup_measurement_error false |
| 종료 진단 | identity_observation `owned_zombie`·exit_poll_path `main_poll`·exit_confirmation_samples 1·exit_confirmation_seconds 0.201 |
| 감시 표본 | elapsed 186.037초·917 samples, automatic_retry false |
| 메모리 | 최소 cgroup 여유 2,807,578,624 bytes > 2 GiB, peak owned RSS 6,658,187,264 bytes < cap 7,340,994,560 bytes |
| stderr 허용 표식 | OOM false·traceback false |

이번에는 실제 `owned_zombie` 종료 확인 관측과 이후 정상 완료 필드가 함께 남았다. 해당 단일 실행에서 수정 guard의 완료 경로를 확인했으며 모든 종료 경쟁 분기나 OS 강제 메모리 제한을 검증했다는 뜻은 아니다. 메모리는 표본 감시이고 순간별 상한 보장이 아니다. 짧은 smoke는 장문·한국어 대화 품질·일반 성능·양자화 동등성·Ai Manager 앱 통합의 PASS가 아니다.

런타임은 Python 3.12.13·Torch 2.11.0+cu128·NumPy 2.0.2였다. 사용하지 않는 Gradio와 huggingface-hub의 요구 버전 충돌이 남아 있으므로 검증 범위는 격리 text API 실행이며 상속 환경 전체 `pip check` PASS가 아니다. 이번 문서 갱신은 기존 소스·미커밋 변경·원본 packet·증거를 보존하고 두 문서만 추가 갱신했다. 문서 변경에 코드 테스트·모델 실행·다운로드를 추가하지 않았다.

앱 manifest의 model revision·10파일 일치는 실행 프로필의 동등성 증거가 아니다. 기존 로컬 FP16(Torch 2.9.1·NumPy 2.2.6, GPU 3 GiB/CPU 4 GiB offload)과 이번 INT8 전량 GPU는 다른 계약이다. 별도 INT8 runtime/profile 연결·합성 검증·새 실제 앱 E2E 전 로컬 `execution_verified=true`로 자동 반영하지 않는다. 추가 다운로드 승인은 Colab 한정이며 D 드라이브 I/O는 보류하고 기존 모델·인증·DB를 보존한다. 직전 문서 갱신 시점에는 commit·push를 수행하지 않았다. 후속 검토·게시 단계는 별도 기록으로 구분한다.

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

독립 정적 검토는 GO이며 부모의 새 타깃 실행도 통과했다. 위 명령은 CPU 합성 watchdog 타깃 검증이며, 아래 전체 회귀와 구분한다.

### 병합 소스의 새 전체 오프라인 회귀

PR #2 병합 commit `6dce414b2cd46afba74e879e6237dab8edc0a109`와 동일 tree의 소스에서, 기존 격리 개발 venv의 Python 3.12.14와 Node 24.20.0으로 `python -m unittest discover -s tests -v`에 해당하는 전체 발견을 한 번 실행했다. 새 패키지 설치 없이 현재 저장소 `src`를 우선하고, 새 임시 폴더·실행 로그·전후 추적 소스 해시를 사용했다. 하위 프로세스에는 필수 OS 환경만 전달하고 이번 TEMP·PYTHONPATH를 설정했다.

507개 중 **500개 통과·7개 skip·실패/오류 0**, unittest 실행 71.789초다. skip은 격리 tracking CPU 의존성 미설치 4개, decode 의존성 미설치 2개, OS의 비특권 symlink 생성 불가 1개다. 보안 검사나 모델 결과를 성공으로 대체한 skip이 아니다. 실행 전후 추적 소스 해시는 동일했고 C 드라이브의 600,000,000,000 bytes 여유 조건을 전후 충족했다.

테스트는 합성 자료·모의 provider/Drive transport·loopback HTTP를 사용했다. Python 부모 프로세스의 audit가 비-loopback `socket.connect`를 거절하도록 했으며 해당 거절 기록은 0개였다. 이는 하위 프로세스나 OS 전체의 외부 통신 계측·차단 증거가 아니다. 모델·실제 provider API·Drive 또는 기존 개인 home을 실행 입력으로 사용하지 않았고 D 드라이브에는 접근하지 않았다. 이 결과는 수정된 watchdog의 실제 Colab 모델 실행이나 runtime 준비·모델 품질 검증이 아니다.

## 보존·미검증 범위

지정된 비공개 결과 요약만 문서 근거로 읽었고 개인 home·인증·키·DB·모델 자산을 조사하거나 변경하지 않았다. 기존 원본 worker·advisor·resume과 기존 실행 결과는 보존한다. 공개 문서는 입력·출력 원문, WAV, 모델, 로그 또는 실제 개인 경로를 포함하지 않는다.

장문·한국어 대화 품질·일반 성능·양자화 전후 동등성·모든 입력/환경·Ai Manager 실제 모델 통합·수정된 watchdog의 Colab 실제 모델 실행은 미검증이다. 현재 짧은 smoke 시간은 벤치마크나 성능 보장이 아니다. 이번 소스·문서 작업은 새 Release·설치 패키지 게시·원격 GPU 실행·추가 모델 실행 승인이 아니다.

## 2026-10-24 수정 감시기 노트북의 로컬 준비

`scripts/colab/build_llama_watchdog_notebook.py`는 명시된 동결 원본 notebook·r02 캐시 검증/주기 advisor/worker·수정 canonical watchdog의 해시를 확인해 별도 새 출력 폴더에 노트북을 만든다. 기존 출력은 덮어쓰지 않는다. 감시기 바이트는 canonical 소스와 동일하고, r02의 스트리밍 SHA·캐시 hint·단계 기록을 fresh ROOT 흐름에 연결했다. worker의 과거 재개 설명만 새 준비본 출처로 정정했으며 기존 원본은 변경하지 않았다.

새 노트북은 9개 셀·코드 5개·내장 payload 9개이며 저장 outputs는 비어 있고 execution count는 None이다. 무료 계정/CU 미사용·T4 확인, 새 실험 승인과 runtime/model 다운로드/실행의 세 허용값은 모두 기본 False다. stdlib 첫 검사와 기본 전체 셀 순차 실행에서 검증 표시 1개·실단계 SKIP 3개를 확인했다. live import·파일 I/O 거절 sentinel을 사용했고 새 합성 테스트 7개가 구현자 실행 0.120초·부모 독립 실행 0.085초에 통과했다. source 해시 변조 거절·기존 출력 보존·fresh 흐름·원 감시 한도도 검사했다. 이는 앞선 507개 전체 회귀 이후의 새 타깃 검증이며 이번 builder 추가 뒤 제품 전체 회귀는 반복하지 않았다.

이번에는 로컬 준비·정적/합성 검증만 승인됐다. 업로드·설치·GPU 연결·HF 토큰 입력·모델 다운로드/실행·브라우저 시각 검증은 하지 않았다. 향후 live 검증에는 별도 승인과 무료 UI 확인, 공개 런타임 패키지 및 고정 모델 10파일 16,069,722,669 B의 새 VM 다운로드, 사용자 직접 HF 읽기 토큰 입력이 필요하다. 과거 실행 승인을 자동 재사용하지 않는다. 기본 오프라인 실행의 완료와 live 전 단계 미검증을 구분한다.

## 2026-10-25 새 무료 T4 실행과 감시 후속 진단

아래는 앞선 2026-10-23 실행과 별개의 새 실행이다. 무료 계정·가용 유료 CU 없음·T4 연결을 UI에서 확인하고, 새 허용값을 설정한 뒤 런타임 준비·고정 모델 다운로드·단일 추론을 각각 한 번 수행한 관측이다. 모델은 위와 같은 revision이며 새 VM의 지정 10파일 합계 16,069,722,669 bytes 다운로드 완료·전체 SHA-256 검증 true·토큰 저장 false가 관측됐다. 실제 공급자 청구서는 확인하지 않았다.

### 컨텍스트 보호 준비와 증거 출처

이 실행 전 builder의 런타임 준비·다운로드·실행 셀에 상태 보호를 추가했다. 런타임 준비는 재준비 전 기존 컨텍스트를 무효화하고 준비 성공 후 새 컨텍스트를 확정한다. 다운로드 완료 컨텍스트와 실행 대상 root·model·work의 결합을 확인해 오래된 전역 상태로 후속 단계를 진행하지 않도록 한다. 당시 내장 payload 9개와 감시기 pin은 유지했다. 별도 로컬 합성 검증은 기존 7개에서 13개로 늘었고, 이전 소스의 2개 실패와 변경 소스의 13개 통과를 기록했다. 기본 순차 실행은 오프라인 검증 1개와 실제 단계 SKIP 3개를 유지했다. 이는 아래 실제 모델 결과와 별도 검증이며 이번 watchdog 후속 수정의 회귀 수치로 재사용하지 않는다.

추론 셀 종료 후 브라우저의 결과 JavaScript 로딩 오류로 처음에는 result·phase·watchdog 출력을 읽지 못했다. 이후 읽기 전용 결과 확인 셀에서도 reCAPTCHA 연결 오류와 도구 timeout을 관측했으며 해당 UI 오류의 원인은 확정하지 않았다. 최종 모델·감시 수치는 사용자가 직접 수행한 읽기 전용 `FILE_RESULT_CHECK` 출력의 허용 필드 요약에서 확인했다(`input_acquisition=user_manual_read_only_cell_output`). 이는 원격 파일 전체·원문 JSON·실제 VM 상태를 에이전트가 독립 재검사한 결과가 아니다. 결과 확인은 추가 모델 실행이 아니며, 앞선 출력불명을 추론 실패 또는 재실행 근거로 처리하지 않는다.

### 새 모델 엔진 결과와 감시 판정

| 항목 | 새 실행의 제공 증거 |
|---|---|
| 컨텍스트 | context·root·work 검증 모두 true |
| 엔진 | Llama LLM.int8 GPU 단일 smoke PASS, 생성 호출 1회 |
| 생성 | 입력 41토큰·새 출력 3토큰·EOS 도달 true·길이 상한 도달 false |
| 양자화·배치 | 8비트 Linear 224개·파라미터 텐서 291개 GPU, CPU·disk offload 없음 |
| 로딩·추론 | 각각 69.674526초·1.986636초 |
| GPU peak | allocated 10,087,137,280 bytes·reserved 10,412,359,680 bytes |
| phase | hash_begin → hash_complete → load_begin → load_complete → generate_begin → generate_end → done |
| 감시 | `stopped / worker_identity_changed`, gate 열림, elapsed 178.463초·880 samples |
| 종료·cleanup | `final_worker_returncode=0`, `worker_returncode` 없음, 남은 owned 0·cleanup 측정 오류 false |
| 메모리 | peak owned RSS 6,634,229,760 bytes < cap 7,347,048,448 bytes; 최소 cgroup 여유 2,835,795,968 bytes > 2 GiB |

새 단일 **엔진 smoke는 성공**이고 정확한 Popen 객체가 마지막 wait에서 보고한 종료코드 0도 이번 제공 증거에서 확인됐다. 이는 독립 OS 감사 결과가 아니다. 그러나 감시가 `worker_identity_changed`로 중단됐으므로 **전체 guard 완료 PASS는 아니다**. 최종 종료코드 0으로 기존 중단 사유를 소급해 덮어쓰지 않는다. stderr 요약의 OOM·traceback 표시는 false이며 제공 표본에서 메모리 floor나 RSS cap 중단은 관측되지 않았다. 감시 표본은 모든 순간의 메모리 상한 보장이 아니다.

코드와 제공 요약을 대조하면 이 중단 사유는 gate 전 검사가 아니라 주 감시 loop에서 identity가 None이고 재확인 poll도 None인 경우 또는 None이 아닌 identity가 달라진 경우로 좁혀진다. 이번 실제 실행이 이 두 분기 중 어느 경우였는지는 제공 요약으로 구분할 수 없다. 앞선 종료 경쟁 설명과 양립하지만 실제 원인이 확정됐다고 기록하지 않는다. 후속 오프라인 재현은 통제한 종료 순서의 코드 결함을 검증할 수 있을 뿐, 이 실제 실행의 미기록 identity 상태를 복원하지 못한다.

### 새 오프라인 재현·수정·검증

독립적으로 제어하는 FakePsutil 상태와 정확한 Popen 객체의 poll 결과로, identity가 None인 뒤 즉시 재확인한 poll도 None이지만 실제 상태는 같은 create_time의 소유 zombie 또는 process_absent인 두 순서를 재현했다. 수정 전 canonical 소스에서 이 두 테스트는 모두 실패했다. 기존 코드는 이 종료 중 상태를 계속 살아 있는 identity 변경과 함께 조기 STOP으로 처리했다. 이는 통제한 순서에서 확인한 코드 결함이며 이번 실제 Colab 실행의 identity 상태를 확정한 결과는 아니다.

수정은 같은 create_time의 소유 zombie와 NoSuchProcess로 확인한 process_absent에만 최대 1초의 종료 확인 창을 둔다. 각 표본에서 상태와 기존 메모리·deadline·로그 보호를 다시 확인하고 poll 전후에 확인 창 기한을 검사한다. sleep도 남은 기한으로 제한한다. 1초는 표본 기준 deadline 정책이며 OS가 호출을 반드시 그 시간 안에 반환한다는 보장은 아니다. 이 기한 전에 정확한 Popen의 종료코드가 확인돼야 기존 완료 조건을 적용한다. 확인 창을 넘긴 뒤의 poll 0이나 마지막 wait 0으로 timeout 또는 기존 중단을 소급 PASS로 바꾸지 않는다.

소유 zombie root의 RSS도 create_time·status를 측정 전후 확인해 알려진 자손의 RSS와 중복 없이 합산한다. 측정 오류·계속 살아 있는 소유권 불명·실제 PID 재사용/identity 변경은 fail closed를 유지한다. 남은 자손, gate 전 종료, nonzero 종료, OS/cgroup floor, RSS cap, 로그 오류와 원래 deadline 보호도 유지한다. 새 비식별 요약 필드는 `identity_observation`, `exit_poll_path`, `exit_confirmation_samples`, `exit_confirmation_seconds`다. 향후 실제 분기 진단에는 이 필드를 포함한 별도 새 읽기 전용 결과 helper가 필요하며 이번 동결 helper는 변경하지 않았다.

canonical 감시기의 SHA-256은 `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`다. builder의 `GUARD_SHA`를 같은 값에 맞추고 원본 입력 pin은 유지했다. `.gitattributes`는 감시기 한 파일에만 `text eol=lf`를 적용해 raw-byte pin을 유지하며 전역 `core.autocrlf` 설정은 바꾸지 않는다. 동결 원본·기존 notebook packet은 보존했고 새 live packet을 생성하지 않았다.

기존 `test_colab_watchdog.py` 30개와 새 `test_colab_watchdog_exit_confirmation.py` 15개를 합친 guard 45개, `test_colab_notebook_builder.py` 14개가 이번 타깃이다. 구현자 실행 전후 소스 해시는 동일했다.

| 새 실행 | 실제 결과 |
|---|---|
| 수정 전 canonical의 결정적 재현 | zombie·process_absent 두 사례 모두 실패, 오류 0 |
| 구현자 guard 타깃 | 45개 통과, 7.047초 |
| 구현자 builder 타깃 | 14개 통과, 0.140초 |
| 독립 검토자 관련 타깃 | 합계 59개 통과, 7.197초, exit 0 |
| 부모 독립 관련 타깃 | 합계 59개 통과, 7.219초, exit 0 |

통과 실행의 실패·오류·skip은 모두 0이다. 부모의 새 독립 명령은 저장소 루트에서 다음과 같았다.

```powershell
python -B -m unittest discover -s tests -p 'test_colab_*.py' -v
```

새 회귀는 independent poll/psutil 지연, 1초 경계 전후 종료, 미확인 live/reuse, 자손, zombie root RSS cap·측정 오류·중복 방지와 기존 보호 조건을 검증한다. 전체 제품 회귀는 이번에 반복하지 않았고 관련 타깃 59개만 실행했다. 실제 Colab 모델을 새 수정 소스로 실행하지 않았으므로 원래 guard STOP 판정은 그대로다.

### 후속 작업의 경계

이번 후속 조사는 로컬 소스·지정 증거·새 합성 테스트에 한정한다. 모델 재실행·다운로드·유료 API 호출·Drive 접근·브라우저 조작·인증/키/개인 DB 조회를 하지 않으며 기존 모델·원본 packet·동결 소스·실행 증거를 보존한다. 공개 문서에는 비식별 집계와 코드 식별자만 남기고 개인 URL·경로·PID·계정·토큰·원시 출력·로그·인벤토리를 포함하지 않는다. 후속 수정 소스의 실제 Colab 모델 실행은 수행하지 않았으며, 오프라인 수정 검증을 장문 품질·일반 성능·전체 guard 실환경 PASS로 확대하지 않는다.

## 2026-10-25 종료 확인 수정본 노트북의 새 오프라인 준비

위 감시 수정 후 별도 새 packet을 생성했다. canonical guard SHA-256 `218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b`를 정확히 내장하고 기존 컨텍스트 결합 보호를 유지한다. 새 읽기 전용 결과 helper를 마지막 셀에 추가했으며 SHA-256은 `7a43a8c2101c899236642e80a703e59ac2a17fd6e89c90c1476c49208d6b6311`이다. 앞선 packet·동결 원본·기존 읽기 전용 helper는 보존했다. 이 준비는 위 실제 실행의 guard STOP을 재분류하지 않는다.

| 새 준비물 | 확인값 |
|---|---|
| 전달 후보 | `Llama_Free_T4_INT8_Exit_Confirmation.ipynb` |
| notebook 크기·SHA-256 | 80,682 bytes·`5796fff3f78ad7fd915da99c7750d488c4ef82457dc877528658f26751a6e5c1` |
| 구조 | 11개 셀·코드 6개·내장 자산 9개 |
| 전체 packet | notebook·출처 기록·README 합계 83,880 bytes |
| 기본 상태 | 무료/T4 확인·새 실험 승인·세 live 허용값 6개 모두 False |

추가 helper는 현재 runtime·download 컨텍스트와 경로 결합을 확인한 뒤 현재 work의 크기를 제한한 phase·guard·result JSON과 제한된 stderr만 읽는다. 출력은 허용한 상태·숫자·불리언·enum으로 제한하고 생성 원문·로그 원문·개인 경로·PID·토큰은 출력하지 않는다. 새 `identity_observation`, `exit_poll_path`, `exit_confirmation_samples`, `exit_confirmation_seconds`와 종료 확인 timeout 사유를 whitelist에 포함했다. 유효한 live 컨텍스트가 없으면 파일을 읽지 않고 `not_ready / live_context_absent`를 출력한다. `guard_clean_completion_evidence`는 기존 네 필드의 보조 계약이며 완전한 OS cleanup 보장이 아니다. `final_worker_returncode=0`와 `cleanup_measurement_error=false`도 별도로 확인해야 한다.

### 소형 packet의 디스크 사전 검사

builder의 이전 600,000,000,000 bytes 기준을 이번 소형 코드 packet에 맞춰 조정했다. 쓰기 전에 notebook·출처 기록·README를 직렬화해 실제 합계에 1 MiB 파일시스템 여유분을 더하고, 이를 제외한 여유 공간이 최소 500,000,000,000 bytes인지 확인한다. 이번 출력 합계 83,880 bytes와 여유분의 합계는 1,132,456 bytes였다. 생성 후 C 여유 공간 표본은 598,362,329,088 bytes다. 동시 외부 디스크 사용을 예약하거나 전후 여유 공간 차이 전체를 이번 작업 사용량으로 단정하지 않는다. 이 정책은 소형 코드 산출물에만 적용하며 모델·런타임 설치의 공간 정책을 바꾸거나 기존 자료를 정리하지 않는다.

### 새 산출물과 관련 소스의 오프라인 검증

추가 도구나 nbformat/nbclient를 설치하지 않고 stdlib 구조·AST·해시 검사, 새 합성 테스트와 생성한 실제 notebook의 기본 전체 코드 실행을 수행했다.

| 새 검증 | 실제 결과 |
|---|---|
| 구현자 builder·helper 타깃 | 18+8개 합계 26개 통과, 0.250초 |
| 독립 검토자 관련 타깃 | guard 45+builder 18+helper 8, 합계 71개 통과, 7.330초 |
| 부모 독립 관련 타깃 | 같은 71개 통과, 7.224초, exit 0 |

통과 실행의 실패·오류·skip은 모두 0이다. 부모 명령은 `python -B -m unittest discover -s tests -p 'test_colab_*.py' -v`다. 앞선 59개는 감시 수정 시점 기록이고 이번 71개는 새 packet/helper를 포함한 후속 타깃이며 전체 제품 회귀는 반복하지 않았다.

부모는 생성된 실제 notebook의 6개 코드 셀을 새 빈 namespace에서 순서대로 실행했다. 파일 접근, 모델·네트워크·설치·subprocess·토큰 입력 관련 import를 거절하는 sentinel 아래 오프라인 검증 표시 1개·live 단계 SKIP 3개·결과 진단 SKIP JSON(`not_ready / live_context_absent`)을 확인했다. ROOT는 생성되지 않았고 파일시스템 호출은 0이었다. raw notebook·helper·복원한 내장 자산 9개에 대한 5종 개인정보 패턴 검사는 일치 0건이었으며 이는 모든 민감정보의 부재를 자동 보장하는 검사는 아니다.

새 packet은 로컬 준비·오프라인 검증까지다. Colab 업로드·실제 화면 표시·GPU 연결·런타임 설치·모델 다운로드·추론·토큰 입력·Drive·유료 API는 수행하지 않았다. 실제 Colab에서 수정 guard와 새 helper의 동작 및 시각 검증은 미검증이며 기존 모델·인증·키·개인 DB·원본 실행 증거는 보존한다.
