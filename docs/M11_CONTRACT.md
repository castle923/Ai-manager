# M11 자동 검수 원형 계약

상태: **비실행 원형 구현·검토 중**. 기존 v0.10.0 앱 API·UI·worker·runtime과 별도이며 모델 정상 작동을 확인한 기능이 아니다. 자동 발견·Drive 접근·파일 full hash·환경 설치·입력 생성·GPU/worker 실행·실결과 receipt 연결은 수행하지 않는다. M12–M15의 구현과 실환경 검증은 남는다.

## 실행과 입출력

Python 3.10 이상과 표준 라이브러리만 사용한다. 저장소 루트에서 다음과 같이 실행한다. 프로젝트 설치 없이 실행하려면 해당 shell에서 `PYTHONPATH=src`에 해당하는 환경을 설정한다. 이는 현재 shell 범위이며 시스템 설정 변경이 아니다.

```text
python -B -m ai_manager.validation_prototype catalog
python -B -m ai_manager.validation_prototype example --now 1800000000
python -B -m ai_manager.validation_prototype validate --root <새_원형_입력_폴더> --document example.json
python -B -m ai_manager.validation_prototype state --root <새_원형_입력_폴더> --document state.json
python -B -m ai_manager.validation_prototype transition --root <새_원형_입력_폴더> --document transition.json
```

`example`은 매번 새로운 batch/case/artifact ID의 **가상 메타데이터 선언**을 stdout으로 만든다. 모델·과거 WAV·이미지·실계정 자료를 입력하지 않는다. 예제의 0으로 채운 source/code/runtime proof는 실제 증거가 없는 synthetic sentinel이다. `--now`는 명시한 합성 epoch이며 실제 사용자 인증·동의가 아니다. `validate`는 현재 snapshot·approval·ledger·검사 시각을 포함하는 문서 하나를 읽고 계약을 대조한다. 미래의 실제 서비스는 신뢰할 수 있는 현재 시각·snapshot·마지막 ledger를 서버가 공급해야 한다. 사용자가 제출한 `now`·snapshot·ledger만으로 실제 권한을 보장하지 않는다.

[이번에 새로 만든 6개 case 예제](examples/m11/dry-run-bundle.json)는 입력 schema를 읽기 위한 합성 선언이다. 가상 epoch/ID/proof를 실제 검수 기록으로 사용하지 않는다.

성공 출력은 `dry_run_contract_valid`, `execution_authority=false`, `model_test_performed=false`, `quality=not_assessed`다. 거부는 exit 2와 값·경로를 포함하지 않는 고정 reason code다. 입력 오류를 실행 성공/모델 고장으로 번역하지 않는다. `state`/`transition`의 `succeeded` 선언도 `synthetic_contract`일 뿐 실추론 증거가 아니다.

## 6개 프로필과 snapshot

`validation_profiles`는 기존 공개 manifest 6개만 고정 SHA로 확인한다. 파일 자체의 ID/revision·필수 파일 수·bytes·license를 사용한다. 모델 폴더를 검색하거나 모델 코드를 import하지 않는다. 이 catalogue의 fingerprint가 달라지면 예전 snapshot을 거부한다. 후보 목록은 ID 기준 집합으로 정규화하며 case/DAG 순서는 의미 있는 순서로 보존한다. 같은 지원 프로필의 여러 후보는 서로 다른 candidate ID로 표현할 수 있다.

snapshot은 `schema_version`, `snapshot_id`, `registry_generation`, `source_proof_sha256`, `code_sha256`, `runtime_lock_sha256`, `catalog_sha256`, 후보별 `candidate_id/profile_id/revision/manifest_sha256`을 묶는다. 승인 이후 현재 snapshot이 달라지면 `snapshot_stale`; 계획 내용·version/hash·scope가 달라지면 `approval_stale`다. 이 원형은 해당 proof들의 **선언 형식과 동등성**만 확인하며 실제 코드·자산 바이트를 검증하지 않는다.

## 계획·승인·예산

- schema 1만 허용한다. `mode=dry_run`, `action=validate_plan`만 가능하다. 미래 install/download/inference 액션은 승인하지 않는다.
- hash는 canonical JSON의 SHA-256이며 **인증서명·변조방지 저장소가 아니다**. `actor`는 simulation label이고 인증된 실제 사용자를 뜻하지 않는다.
- 승인에는 정확한 plan SHA/version, snapshot SHA, catalogue SHA, batch, 발급·만료 시각, 동일한 limits가 필요하다. expiry는 생성 후 최대 24시간과 wall limit 이내다. 만료 경계 시각은 거부한다.
- limits는 wall seconds·문서 read bytes를 포함하고 transfer/install/worker 한도는 모두 0이다. wall은 생성 시각부터의 경과와 누적 ledger 중 보수적인 값을 쓴다. 같은 batch의 재개가 시간·bytes·설치·실행 예산을 reset하지 않는다.
- ledger는 알려진 상태만 받으며 초기 sequence 0/zero previous hash/누적 0, 이후 정확한 이전 hash·증가 sequence·단조 시간/카운터를 요구한다. 이전 ledger와 관찰된 예산을 넘거나 줄이는 요청은 거부한다. **현재 원형에는 영속 ledger 저장소나 동시성 잠금이 없다.** 호출자가 마지막 신뢰 기록을 제공해야 하므로 CLI 파일을 초기화해 제출하는 공격에 대한 실제 재사용 방지는 M12/M15의 서버 소유 저장·락 gate가 필요하다.

## 미래 입력과 계보

계획 시점에는 아직 생성하지 않은 input/output SHA를 알 수 없다. 미래 output과 fresh/derived input의 `sha256`은 반드시 `null`이다. 가짜 digest를 알려진 값처럼 강제하지 않는다. 현재 지정 원본 `designated_current`인 Whisper 입력만 known digest를 요구하며 이 역시 선언이지 실파일 검사가 아니다.

계획은 input/output ID, kind, 고정 recipe, parent case/output 참조와 변환 정책을 고정한다. 모든 input/output ID는 교차 집합에서도 중복을 거부한다. TTS→Whisper는 같은 batch의 앞선 TTS WAV output을 참조하고, `pcm24k_to_pcm16k_mono-v1`·24000→16000Hz·mono·PCM16·`max_duration_ms<=30000`을 선언한다. 길이는 실제 TTS 길이가 아닌 허용 상한이다. parent output SHA도 미래 값이므로 `null`이다. 다른 batch/과거 WAV fallback은 허용하지 않는다. parent가 실행 불가하면 이후 조정기는 dependency blocked/deferred를 기록해야 하며 이 원형은 이를 실행하지 않는다.

M13은 계획을 고쳐 쓰지 않고 **별도 actual receipt**에서 plan/case/output ID·source actual SHA·변환 actual SHA·실측 형식을 대조해야 한다. 그 receipt 수집·실파일 hashing·생성 실행·음성 내용 검증은 이번 구현에 없다. 침묵/noise를 정상 전사 검수 입력으로 인정하지 않는다.

## 다축 상태와 중단

identity(불명/모호/미지원/일치/revision 차이), artifact(미검사/불완전/hash 차이/일치), environment(미검사/미준비/준비), resource(미검사/차단/준비), execution, output을 따로 보존한다. 실행의 deferred·run_failed·cancelled·timed_out·interrupted는 succeeded와 다르다. running 이상은 사전 조건 네 축이 충족돼야 하고 succeeded는 output validated가 필요하다. quality는 항상 not_assessed다. 환경 차단은 모델 고장 판정이 아니다.

상태 전이는 같은 batch/case/attempt와 단조 시각만 허용한다. terminal attempt는 수정할 수 없다. 재시작/부분 재개 시 원 attempt를 보존하고 새 attempt·현재 증거·누적 예산·필요 재승인을 확인하는 실제 coordinator는 M12/M15에 남는다. 단일 home 슬롯·bounded dispatcher·중복 job lock·child 정리도 이번 원형의 실증거가 아니다.

## 입력 방어와 보존 범위

문서는 최대 256KiB·깊이 24·노드 8192이며 duplicate key, float/NaN/Infinity, bool-as-int, unknown field, 잘못된 enum/길이/범위·중복 ID를 거부한다. 정수만 쓰고 key sort와 compact UTF-8 JSON으로 hash를 고정한다. path는 root 아래 제한된 상대 구성요소만 받고 `..`, 절대 경로, ADS, backslash, symlink/reparse, 비정규 파일을 거부한다. 열린 파일 ID와 전후 크기·mtime을 대조한다. OS의 공격적 동시 변경을 완전히 막는 디렉터리 handle sandbox를 구현했다고 주장하지 않으며 실제 자산 접근은 M12의 별도 gate다.

README/config 명령·pickle·torch.load·custom decoder는 이 코드에서 실행하지 않는다. packaged 공개 manifest와 사용자가 명시한 문서만 읽는다. 폴더 스캔, 네트워크, subprocess, 사용자 home/DB 접근 기능을 제공하지 않는다. 부분/실패 scan의 관찰 누락으로 기존 참조/proof를 지우는 기능도 없다.
