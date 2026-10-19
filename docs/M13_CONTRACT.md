# M13 — 전체 가중치·현재 환경·새 입력·실제 출력 연결

M13은 source-only 검수 CLI와 순차 조정기에 고정 6프로필의 기존 worker를 연결한다. M12의 `validate_control_plan`·`run_cpu_probe` 승인은 모델 실행으로 승격되지 않는다. 새 `run_models` action의 새 plan·정확한 SHA 확인·한 번 소비하는 승인만 모델 실행을 허용한다. M14 대시보드와 M15 부분 재개, 새 패키지·Release는 포함하지 않는다.

## 명시 로컬 범위

기존 `scan-local`·Drive metadata의 기본 정책은 유지한다. M13 `scan-models --root <모델원본1> --root <모델원본2>`는 명시한 1–6개 로컬 root를 각각 depth 2·작은 JSON 256KiB·metadata 본문 512KiB로 관찰하고 하나의 batch에 결속한다. 계정 전체나 다른 프로젝트를 자동 검색하지 않는다. 물리 root 중복·동일 프로필 중복·부분 관찰은 계획하지 않는다. 각 후보는 원래 source observation과 index에 묶이며 승인·소비·case 실행 직전 동일 범위를 한 번씩 다시 관찰한다. metadata 읽기 범위는 재관찰 전에 보수 예약하며 실제 측정치와 구분한다.

이 명시 M13 관찰의 `metadata_anchors_only=true`는 식별용 `config.json`·`model_index.json`만 제한 파싱한다. 큰 tokenizer config를 파싱 한도 밖으로 읽거나 허용 크기를 늘리지 않는다. 다른 정규 파일은 stat으로만 관찰하고 필수 자산 전체 bytes·SHA는 후속 full-hash gate에서 확인한다. 이 옵션의 bounded complete는 전체 파일 내용 확인이 아니다. M12 기본 관찰의 큰 JSON 오류·partial 판단은 바뀌지 않는다.

TAPIR처럼 anchor가 없는 단일 정확 파일명·크기 힌트는 `manifest_hash_required`로만 계획할 수 있다. 이는 `supported_metadata`나 revision 검증 완료가 아니다. 실행은 공식 고정 manifest의 전체 checkpoint SHA가 맞아야 하며 식별 단계에서 pickle·torch.load·임의 코드를 실행하지 않는다.

## 승인 계획과 예산

모델 spec은 사용할 기존 Python·runtime lock의 절대 경로, 각 raw SHA, 기대 packaged lock raw SHA, canonical lock SHA, 현재 package 계약, 공유 app-home, 고정 fixture recipe, case timeout·full-hash timeout과 총 필수 bytes를 담는다. 공개 문서에는 별칭만 쓰며 실제 경로는 private plan·receipt에만 저장한다.

Windows의 기존 adapter lock이 CRLF를 사용할 수 있어 lock 내용의 동치는 **CRLF→LF만** 허용한다. 실제 파일 byte 동일성이라고 표현하지 않는다. 공백·버전·패키지 행·일반 CR은 무시하지 않는다. 승인 binding은 실제 raw lock·Python SHA에 묶이며 EOL만 바뀌어도 새 plan이 필요하다. 코드 identity는 모든 shipped Python·JSON manifest·lock 및 TTS source lock을 포함한다. 이는 설치한 모든 라이브러리 파일의 전체 바이트 attestation이나 OS 보안 sandbox는 아니다.

모델 다운로드 bytes와 설치 권한은 0이다. 별도 full-hash 읽기 예산은 manifest 필수 bytes 합계(최대128GiB)이며 case 전에 전량 예약하고 실패에도 환급하지 않는다. 기존 metadata 누적 예약도 보존한다. 현재 환경/자원 gate가 먼저 차단하면 가중치를 읽지 않는다. 계획 만료는 최대1,800초이며 case timeout 최대900초·full-hash timeout 최대600초다. 취소/만료/시간 한도는 해시 chunk마다 확인한다. 이미 소비한 batch를 재요청해 새 모델 worker를 만들거나 실패를 자동 재시도하지 않는다.

## 실행과 보존

조정기는 최대 queued3·active1이며 spec의 명시 공유 app-home에서 기존 execution slot을 단 한 번 소유한다. bridge가 기존 고정 worker를 직접 실행하므로 TaskInference/Inference 큐에서 slot을 다시 획득하지 않는다. 해당 home의 협조 lock만 보장하며 다른 home/다른 앱의 GPU 독점은 아니다.

각 case는 새 run ID·독립 input/output/cache directory를 사용한다. 기존 원본·모델·runtime·인증·개인 DB·이전 출력은 수정·이동·삭제하지 않는다. 모델은 offline·local_files_only·trust_remote_code=false인 기존 worker 계약을 따른다. 네트워크 방화벽 격리를 구현했다고 주장하지 않는다.

실행 순서는 현재 runtime/package/CUDA/RAM/VRAM/disk 관측 → manifest 모든 필수 경로·크기·전체 SHA → 새 입력·계보 → dispatch 직전 다시 자원 관측·runtime/code/source stat·ancestor pin 확인 → 고정 worker → owned Job 종료 관측 → 독립 출력 검사 → actual receipt다. 해시 open 전후 fd·현재 경로·부모 identity를 대조하고 파일별 bytes/SHA 진행 event를 남긴다. OS 관리자가 stat을 정교하게 복원하는 동시 변경이나 라이브러리 내부 모든 파일을 보안 격리했다고 주장하지 않는다.

자원 정책은 최소 available RAM3GiB·출력 디스크512MiB, free VRAM은 TTS3GiB/Whisper2GiB/TAPIR2GiB/Llama18GiB/Image24GiB다. 이 보수적 admission은 모델 고장·최소 하드웨어 사양 판정이 아니다. image/LLM에는 기존 owned Job RSS 합계·available RAM live guard(각18/12GiB RSS상한·3GiB 여유)를 유지한다. 메모리 관측은 OS hard quota가 아니다.

모든 새 subprocess는 기존 suspended Windows start·kill-on-close Job 소유권을 사용한다. 정상·오류·취소·timeout 모두 정확한 Job을 종료하고 `ActiveProcesses=0`을 관측한 뒤 slot을 반환한다. 관측 실패는 `child_cleanup_unverified`로 batch를 정지해 다음 case dispatch를 막는다. 확인한 지원 경로는 Windows이며 다른 OS는 cleanup 증명 실패로 안전하게 멈춘다.

## 새 fixture와 receipt

- 두 TTS는 이번 batch에서 새로 쓴 같은 한국어 문장·seed0·기존 bounded recipe로 cold 순차 실행한다. 과거 WAV를 입력이나 성공 근거로 쓰지 않는다.
- Whisper는 **같은 batch의 성공 TTS** 출력 SHA·case/run을 확인하고 새 16kHz mono PCM16로 선형 보간한다. source SHA→변환 recipe→input SHA를 기록한다. 의존 TTS 실패/30초 입력 계약 초과/침묵·손상은 deferred/실패이며 과거 WAV·noise fallback을 사용하지 않는다.
- Image는 새 prompt·512×512/4steps/seed0/CFG4, LLM은 새 짧은 한국어 질문·기존 입력/출력 token 제한을 사용한다.
- TAPIR는 기존 tracking runtime의 av/numpy로 새 8frame·256²·8fps 합성 MP4·정규화 점을 생성하고 새 SHA를 고정한다.

종료코드0·파일 존재·runtime import만으로 성공하지 않는다. WAV decode/PCM/유한 신호, 전사 schema/입력시간, response token·parameters/TXT 일치, tracks shape/유한값/점·run·model·vendor 일치, image decode/metadata·run·prompt·recipe 일치를 기존 독립 출력 계약으로 확인한다. 모든 출력 full SHA와 input·model full SHA·runtime binding·현재 code·plan SHA·owned PID/Job active0을 private receipt에 연결한다.

dispatch 전 미준비·자원·무결성 차단은 `deferred`이며 모델 테스트 미수행이다. 실제 model dispatch 뒤 worker/출력 검사 실패는 `run_failed`와 실제 시도 여부를 보존한다. `model_test_performed=true`는 시도 여부이며 성공 또는 품질 우수 판정이 아니다. `models_completed`는 계획의 처리가 끝났다는 의미이고 개별 case의 성공/차단/실패를 덮어쓰지 않는다. 새 UI와 6프로필 실제 성공을 이 상태만으로 선언하지 않는다.

## 사용

```text
python -B -m ai_manager.validation_cli --home <새home> init
python -B -m ai_manager.validation_cli --home <새home> scan-models --root <명시모델root1> --root <명시모델root2>
python -B -m ai_manager.validation_cli --home <새home> plan --observation <관찰ID> --model-spec <명시runtime설정.json> --wall-seconds 1800
python -B -m ai_manager.validation_cli --home <새home> approve --plan <ID> --sha256 <정확SHA> --confirm
python -B -m ai_manager.validation_cli --home <새home> dispatch --plan <ID> --approval <승인ID>
python -B -m ai_manager.validation_cli --home <새home> run --batch <batchID>
```

runtime 설정 JSON은 `runtimes`(프로필별 `python`·`lock`), `shared_home`, 선택적 `timeout_seconds`·`hash_seconds`만 받는다. 기존 runtime이 없거나 lock/package가 다르면 자동 설치/다른 runtime fallback을 하지 않는다. 기존 status/cancel을 사용하며 case receipt와 원시 로그는 새 private home 아래에만 둔다.
