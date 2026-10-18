# M10 Runpod 원격 검증 보고

최신 상태: 공식 권장 예시의 2048×2048·40 steps·guidance 1.0 설정으로 새 full-GPU Qwen-Image-2.1 profile에서 이미지 1장을 생성하고 회수·해시 검증을 완료했다. 한 번의 독립 검토 직후 새 Pod를 삭제했으며 404·목록 부재를 확인했다. 앞선 세 Secure Pod와 이번 HQ Pod의 총 네 새 Pod는 모두 삭제 확인했다. 이는 공식 권장 고품질 조건 1회 실행 성공이며 절대 최고 화질 보장·품질 점수·Windows 8GB·앱 원격 통합·실GPU 취소의 검증은 아니다. 아래 모든 과거 시도와 준비 기록은 당시의 판정으로 보존한다.

## 1차: Community Cloud 재고 조사

기록일: 2026-10-18. 판정: **Community Cloud A100 80GB 재고 BLOCK, 실제 GPU 실행 미수행**.

이 문서는 이번 원격 검증 시도의 읽기 전용 사전 확인 결과만 기록한다. M10 전체 완료, Windows 로컬 8GB GPU 성공, 앱의 원격 실행 통합 완료를 뜻하지 않는다.

### 승인 범위와 중단 조건

사용자가 승인한 범위는 새 Runpod Community Cloud A100 80GB Pod 한 개에서 같은 이미지 worker를 실제 실행하고, 결과를 회수해 해시를 비교한 뒤 해당 새 Pod를 종료하는 것이다. 상한은 생성·과금 시점부터 최대 2시간, GPU와 설치·다운로드 시간 및 선택한 스토리지를 합쳐 총 $5 이내다. 기존 Pod와 다른 작업, 기존 자료는 보존한다.

Community Cloud만 허용하며 Secure Cloud나 다른 GPU로 대체하지 않는다. 재고나 실배치 견적을 확인하지 못하면 생성하지 않는다. 예산·시간의 충분한 여유를 남겨 작업 중단, 회수, 종료를 수행하도록 사전 준비한다. API의 초 단위 사용료 계산은 계정 차원의 강제 지출 상한을 보장하지 않는다.

### 이번에 확인한 사실

Runpod 읽기 인증은 성공했다. 예산 확인에 필요한 잔액 조회도 성공했고 승인 예산을 충족했다. 잔액 금액과 계정 정보는 공개하지 않는다.

최종 조회는 **2026-10-18 14:48:09 KST (05:48:09 UTC)**에 수행했다. 공식 REST v2 GPU catalog에 `include=AVAILABILITY`, `product=POD`, `cloud=COMMUNITY`, `gpuCount=1`을 명시했다. 최소 CUDA 12.8 조건을 둔 조회와 CUDA 조건을 제거한 최종 조회에서 아래 두 GPU 모두 `availability: NONE`이었다. 지역·국가·최소 RAM·vCPU를 추가로 제한하지 않았다.

| GPU | VRAM | Community 카탈로그 가격 | 현재 조회의 가용성 |
| --- | --- | --- | --- |
| NVIDIA A100 80GB PCIe | 80 GB | $1.19/시간 | NONE |
| NVIDIA A100-SXM4-80GB | 80 GB | $1.39/시간 | NONE |

위 가격은 카탈로그 표시값이며 배치 가능한 호스트의 실견적이 아니다. 실제 호스트 RAM·디스크와 GPU·스토리지 합산 견적을 확정하지 않았다. 앞선 공식 GraphQL의 `secureCloud:false`, `gpuCount:1` 조회에서도 두 GPU의 `lowestPrice` 가격·재고 필드는 null이었다. null만으로 재고를 단정하지 않고 명시적인 Community REST v2 조회로 교차 확인했다. REST v2의 Cloud 필터를 생략하면 Secure가 기본이므로, 기본 Cloud 조회를 Community 재고 증거로 사용하지 않았다.

이 결과는 조회 시점의 재고 상태다. 실제 생성을 통한 용량 probe나 자동 반복 조회는 하지 않았다.

### 실행과 비용 상태

| 항목 | 이번 수행 결과 |
| --- | --- |
| 새 Pod 생성 | 0 |
| 새 스토리지·network volume 생성 | 0 |
| 기존 Pod 시작·중지·종료·변경 | 0 |
| 이번 시도로 발생한 추가 클라우드 비용 | $0 — 유료 자원 생성·실행 없음 |
| 모델 다운로드·전체 바이트 해시 검증 | 미수행 |
| 실제 CUDA·GPU 식별·메모리 측정 | 미수행 |
| 동일 worker의 이미지 추론 | 미수행 |
| 새 PNG 회수·원격/로컬 해시 비교 | 미수행 |
| 실제 Pod 종료·잔여 스토리지·과금 종결 검증 | 미수행 — 생성한 Pod가 없어 종료 대상 없음 |

종료 대상이 없다는 사실을 종료 검증 PASS로 판정하지 않는다. 실제 실행이 없으므로 결과 이미지나 성공 로그도 없다.

### 준비물과 검증 한계

같은 Ai-manager 프로젝트의 현재 이미지 worker를 변경 없이 Linux harness로 실행할 준비를 진행했다. 비공개 bundle 준비와 독립 검토 단계이며 Linux 실제 프로세스 그룹 취소 fixture, Linux 그룹 guardian 및 별도 시간·비용 watchdog의 실제 검증은 완료되지 않았다. guardian에 PID를 전달하기 전의 후손 프로세스 정리 보장도 잔여 검토 항목이다. 따라서 현재 bundle은 실행 준비 완료 상태가 아니며 실제 GPU 실행 성공 근거로 사용하지 않는다.

이번 준비에서 읽은 현재 소스의 SHA-256은 다음과 같다. 이 해시는 원격에 업로드하거나 실행한 코드의 검증 결과가 아니다.

| 파일 | SHA-256 |
| --- | --- |
| `image_worker.py` | `4bdeaa3113f6afc7aab77453d7cf067bc23d60034fa607c30ee9141a08b3b7dc` |
| `image_safe.py` | `c0d9233ea15ebdba83c18a05860d34f6edfa1cff624f540c8d554b46f17c63cb` |

예정 모델은 공식 `Qwen/Qwen-Image-2.1`의 고정 revision `d26bb61231c349cf6b7896fa83353113880e1ba3`이다. 이번에는 모델을 다운로드하지 않았다. Qwen Research License의 연구·평가 목적 비상업 조건을 전제로 하며, 필요한 동의는 사용자 직접행위다. 이번 시도의 원시 API 응답·계정·인증값·호스트·개인 경로·비공개 로그는 공개 저장소에 포함하지 않는다. 과거 생성 결과를 이번 성공 근거로 사용하지 않았다.

### 같은 승인 범위에서 재개할 조건

재개 시 Community A100 80GB 재고와 실제 배치 견적을 새로 확인하고, 호스트 RAM·디스크 및 선택 스토리지까지 합산해 2시간·$5 상한과 종료 여유를 검토해야 한다. 새 실행의 출처 기록, 고정 source·의존성·모델 해시 연결, Linux 취소 fixture, 시간·비용 deadline과 독립 watchdog, 새 Pod 식별값에만 고정된 회수·종료 경로를 생성 전에 검증해야 한다. 실제 결과를 회수해 해시를 확인한 다음 새 Pod의 종료, 목록 삭제, 새 잔여 스토리지 없음과 과금 종결 상태를 확인한다.

다른 GPU·Cloud 또는 비용·시간 상한 확대는 별도 승인 범위다. 현재 기록은 원격 검증 완료로 승격하지 않는다.

### 공식 출처

- [Runpod 공식 GPU 선택 안내](https://github.com/runpod/runpod-plugins-official/blob/main/plugins/runpod/skills/runpod-usage/reference/gpu-selection.md)
- [Runpod REST v2 OpenAPI](https://docs.runpod.io/api-reference-v2/openapi.json) — `GpuCloudFilter` 및 GPU catalog 정의
- [Runpod Pod 과금·스토리지 가격](https://docs.runpod.io/pods/pricing)
- [Runpod GraphQL GPU 가격·재고 조회](https://docs.runpod.io/sdks/graphql/manage-pods)
- [Qwen-Image-2.1 고정 revision 모델 문서](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/README.md)
- [같은 revision의 LICENSE](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/LICENSE)

## 2차: 승인된 Secure Cloud 단일 실행과 조기 안전 종료

최신 판정: **전용 SSH 호스트 인증·GPU 하드웨어 확인과 관측 실패 시 자동 종료는 확인했다. 실제 이미지 worker 실행은 미수행이며 원격 이미지 검증은 미완료다.**

사용자는 Community Cloud 대신 **Secure Cloud의 NVIDIA A100-SXM4-80GB 한 개**, 생성부터 최대 2시간·GPU/설치/다운로드/스토리지 총 $5 이내의 실행을 명시 승인했다. 다른 GPU나 Cloud로 대체하거나 새 Pod를 추가하지 않았다. 아래 결과는 앞선 Community 읽기 조사와 분리한 새 실행의 기록이다.

### 실제 배치와 새 실행 출처

생성 직전 2026-10-18 15:06:33 KST(06:06:33 UTC), 명시적인 `cloud=SECURE`, `gpuCount=1`, `minCudaVersion=12.8` 조회에서 지정 GPU 재고 HIGH·$1.79/시간을 확인했다. 잔액 확인은 승인 예산을 충족했으며 금액은 공개하지 않는다.

새 Pod 생성 응답은 **15:06:42 KST(06:06:42.006 UTC)**이며, 실제 scope는 Secure·지정 SXM4 80GB·GPU 한 개, 컨테이너 20GB·Pod 볼륨 150GB, 할당 host RAM 250GB·vCPU 16이었다. 새 network volume은 만들지 않았다. 실제 응답의 현재 Pod 단가는 **$1.79/시간**이었다. 이 필드의 storage 포함 여부를 단정하지 않고 별도 디스크 170GB 비용을 보수적으로 더했다. 공식 실행 중 $0.10/GB/월을 28일로 환산하면 추가 $0.025298/시간, 합계 $1.815298/시간·2시간 $3.630596로 계산했다. 이는 사용료 추정이며 확정 청구 금액이 아니다.

동일 이미지 worker·helper·requirements의 로컬 SHA-256은 1차 기록의 worker/helper 값 및 아래 requirements 값과 같았다. 새 Linux bundle manifest와 제어 코드의 해시를 이번 실행에 연결했다. worker를 다른 pipeline으로 교체하거나 수정하지 않았다. 모델은 같은 고정 Qwen-Image-2.1 revision을 예정했으나 다운로드하지 않았다.

| 준비물 | SHA-256 |
| --- | --- |
| `requirements_image.lock` | `0453755e743e46b4a5b57040732c93fe63c115732ced61b7acadc1874889bee0` |
| 새 Linux bundle manifest | `220370623bd43204c0b54f9a58c4dfc57430ff2ce92b31dd9c284f441b967c3b` |
| 실행한 cloud controller | `38d4508b2711716ed9f850cbe1515f350cdc4190febb94a48b7fa17e6dcd91e8` |
| 정수 시간·비용 정책 | `584b36f42591e1e698a4827938e91e17fb5336229c5b51d5c6296d2c4e70481d` |

새 bundle은 소형 파일로 업로드했지만 원격 추출·해시 readback 단계에 도달하지 못했다. 위 bundle 해시는 로컬 준비물 식별값이며 원격 실행 검증 해시로 대신하지 않는다. 현재 공식 template catalog에서 확인한 Python 3.11 base 이미지 `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04`를 사용했다. base의 기존 torch를 모델 실행 근거로 사용하지 않았고, 별도 cu128 fresh venv 설치도 시작하지 않았다.

### 먼저 검증한 안전 제어

생성 전에 정수 시간·비용 정책 10개, 로컬 fake HTTP 생성/삭제 실패 처리, 경계 조건 6개와 독립 프로세스 생존을 새로 검증하고 독립 리뷰를 받았다. 생성 응답 유실 후 중복 POST 금지, 고유 nonce·Cloud·GPU·생성 시각에 의한 식별, 새 ID 고정 삭제, 로그/heartbeat 쓰기 실패가 정리를 막지 않는 경로를 확인했다. detached controller core는 원래 launcher 종료 후에도 합성 HTTP 대상으로 동작하고 종료했다. 이들은 로컬 제어 검증이며 클라우드 이미지 실행을 뜻하지 않는다.

실제 controller는 생성 전 06:06:40.380 UTC부터 UTC와 monotonic elapsed 중 보수적인 값을 사용했다. 정책은 작업 중단 90분, terminate 시작 95분, 최대 120분과 240초 operator lease였다. 응답 단가에 보수적 storage를 더한 값이 $2/시간을 넘거나 관측을 잃으면 조기 정리하도록 했다. 계정 API key는 로컬 controller 메모리에만 두었으며 PIN은 controller·Pod에 전달하지 않았다.

최신 공식 API에서 provider 강제 TTL의 작동을 확인하지 못했으며, 공식 runpodctl의 `--stop-after`·`--terminate-after` 제거 이력도 확인했다. 따라서 해당 플래그를 비용 보호 근거로 사용하지 않았다. 로컬 독립 감시와 충분한 종료 마진을 적용했으며 PC 전체 전원·인터넷·API의 장기 동시 단절까지 강제 상한을 보장한다고 주장하지 않는다.

### 실제로 확인한 단계와 중단 원인

새 client/host ED25519 키를 이번 Pod에만 사용하고, 사전에 정한 host public key를 전용 known_hosts에 고정했다. `StrictHostKeyChecking=yes`와 ED25519 host key 제한을 적용한 직접 SSH가 성공했다. 기존 계정 SSH 설정은 바꾸지 않았고 client private key도 원격에 보내지 않았다. 새 컨테이너는 SSH만 노출하며 원격 startup에서 task host private key 환경변수를 지웠다.

**15:08:28 KST(06:08:28 UTC)**의 성공한 SSH 명령에서 Python 3.11.10, 실제 `NVIDIA A100-SXM4-80GB`, VRAM 81,920 MiB, driver 580.126.16을 확인했다. 해당 SSH 세션에서 계정 Runpod API key와 task host private key 환경변수가 없음을 확인했다. 이 결과는 현재 실행의 로컬 명령 출력 기록으로 남겼으며, 원격 preflight JSON 원본의 회수·해시 비교는 종료 전에 수행하지 못했다. 커널의 전체 host RAM·filesystem free 출력은 Pod 할당 한도와 다르므로 quota 증거로 사용하지 않는다. cgroup 한도 readback도 미수행이다.

**15:08:44.732 KST(06:08:44.732 UTC)**에 controller가 control-plane 관측 실패를 `observation_network_failure`로 분류해 보수 정책에 따라 즉시 terminate를 시작했다. 상세 전송 오류나 HTTP 상태는 그 관측 실패 기록에 남지 않아 구체적인 원인은 미확정이다. 이를 Runpod 장애나 SSH·GPU 고장으로 단정하지 않는다. 뒤이은 CPU fixture용 SSH는 연결 거부로 끝났다.

| 단계 | 이번 Secure 실행 결과 |
| --- | --- |
| 정확한 새 Pod scope·응답 단가·독립 controller 생존 | 확인 |
| 사전 host key 고정 strict SSH·Python·GPU 이름/VRAM/driver | 확인 |
| 새 bundle 업로드 | 소형 파일 전송 완료, 원격 추출·해시 readback 미수행 |
| 대상 Linux CPU 취소·후손 정리 8개 fixture | 미수행 — 실행 명령의 SSH 연결 거부 |
| fresh venv·고정 의존성 설치·runtime audit | 미수행 |
| 모델 24개 파일 다운로드·바이트 해시 | 미수행, 다운로드 0 |
| 실제 CUDA runtime·동일 worker 이미지 추론 | 미수행 |
| 실제 worker 오류·취소 검증 | 미수행 |
| 새 PNG 생성·회수·원격/로컬 해시 비교 | 미수행 |

CPU 안전 fixture PASS 전에는 의존성·모델 다운로드와 GPU 추론을 시작하지 않는 gate를 지켰다. WSL fixture 성공이나 SSH/GPU 식별 결과를 이 미수행 단계들의 성공으로 대체하지 않았다. 자동 재시도 Pod를 생성하지 않았다.

### 종료·스토리지·비용 확인

- **15:08:45.767 KST(06:08:45.767 UTC)**: 해당 새 Pod의 DELETE가 204를 반환했다.
- 후속 확인 GET timeout 뒤 같은 ID만 재확인·정리했다. **15:09:08.508 KST(06:09:08.508 UTC)**에 GET 404와 목록 부재를 확인했다. controller는 정리 완료 후 종료했다.
- **15:09:54 KST(06:09:54 UTC)**의 별도 읽기 재확인에서 v2 대상 GET 404, v2 목록 HTTP 200에서 대상 부재, REST v1 목록 HTTP 200에서 대상 부재를 확인했다.
- 새 network volume·다른 독립 storage 생성은 0이다. 생성한 Pod 볼륨은 Pod 종료에 따라 삭제되는 형태이며 해당 Pod가 삭제됐다. 독립적으로 남는 새 network storage는 없다. 기존 Pod·기존 스토리지는 제어하지 않았다.
- 동일 시각의 해당 Pod 전용 billing 조회는 HTTP 200이나 아직 청구 record가 없었다. 따라서 **확정 청구 금액은 미집계**이며 비용 $0으로 보고하지 않는다. 생성 전 controller 시계부터 종료 확인까지 약 2분 28초, 마지막 별도 확인까지도 3분 15초 미만이다. 보수 합산 단가로 마지막 확인 시각까지 계산한 **상한 추정은 $0.10 미만**이다. 다른 기존 자원의 계정 사용료를 이번 비용으로 합치거나 0으로 판정하지 않는다.

이 새 Pod의 실행·저장 비용을 발생시키는 리소스는 삭제 확인 범위에서 남아 있지 않다. 안전 조기 종료는 검증했지만 원래 목적의 실제 이미지 생성 검증은 미완료다. Windows 로컬 8GB GPU 성공, 앱 원격 통합, 새 모델 검증 또는 모든 환경 PASS를 뜻하지 않는다.

추가 공식 근거: [runpodctl 자동 stop/terminate 플래그 제거 PR](https://github.com/runpod/runpodctl/pull/330), [Pod 볼륨과 독립 network volume 수명](https://docs.runpod.io/pods/storage/types), [Secure/Community 및 network volume 비교](https://docs.runpod.io/pods/choose-a-pod). 원시 응답·개인 경로·키·계정·Pod 식별값·호스트는 공개하지 않는다.

## 3차: 안전 제어 보완 후 승인된 Qwen 검증 재개와 실패 종료

최종 판정: **실제 환경·모델 무결성·CPU 안전 제어·실패 후 정리는 확인했으나, Qwen-Image-2.1 이미지 생성은 실패했다. PNG는 0개이며 이미지 검증 완료가 아니다.** 현재 진행하던 Qwen 검증만 수행했고 다른 모델 검수는 추후로 보류했다.

### 재개 전 보완과 한도

2차 관측의 마지막 heartbeat와 종료 시작 사이 간격은 15,002ms로 기존 15초 request timeout과 일치했다. 그러나 원래 catch가 예외 타입·전송 cause code·HTTP status를 버려 정확한 원인은 소급 확정할 수 없다. timeout 가능성은 추정으로만 남긴다.

부모·독립 리뷰 후 관측 GET만 최대 3회·누적 35초, 요청당 최대 8초·대기 2/5초로 제한한 재시도와 안전한 원인 분류를 별도 controller에 통합했다. timeout·허용된 전송 code·408/429/500/502/503/504만 재시도하고 인증·scope/schema·불명 오류는 정리한다. 원오류 kind·status·허용 code·요청 기간·시도 횟수·결정만 기록하며 응답 body·URL query·키·PIN은 기록하지 않는다. 생성 POST 한 번과 새 ID 고정 삭제 정책은 유지했다. 로컬 합성 10개, 실제 로컬 HTTP의 8초 timeout 후 GET 회복을 포함한 통합 6개 및 기존 생성/정리 경계 회귀를 검증했다. 합성 검증을 실제 클라우드 회복 증거로 대체하지 않는다.

최초 controller의 **06:06:40.380 UTC**를 계속 사용해 작업 중단 **07:36:40.380 UTC**, terminate 시작 **07:41:40.380 UTC**, 외부 최대 **08:06:40.380 UTC**를 고정했다. 새 Pod에서 시간을 리셋하지 않았고 앞선 비용 상한 추정 **$0.096825**를 새 사용료에 합산했다. 240초 operator lease, 보수 단가 $2/시간 상한과 비용 마진을 유지했다.

| 새 제어 코드 | SHA-256 |
| --- | --- |
| 재개 controller | `4e1dbecc7356b76565280cbf54b8d99662f8ca70ddf5c53e50746a8ed9244c49` |
| 원 절대시각·누적 비용 정책 | `578a77a05d692a79d7267a6960f969cc63d94582b0467993bb452873a4414ddb` |
| 제한 관측 재시도 helper | `d9387e0534458f27a13e6b43891dd8553ce0c56441eaa5ba9c53b68aacf6b18d` |

### 실제 새 환경과 모델 준비

명시 승인된 새 재개 Pod 한 개를 **15:19:59 KST(06:19:59.161 UTC)**에 생성했다. 정확한 scope는 Secure Cloud·NVIDIA A100-SXM4-80GB 한 개, 컨테이너 20GB·Pod 볼륨 150GB·network volume 0개다. 실제 응답은 $1.79/시간, 할당 RAM 250GB·vCPU 32였다. 보수 디스크 비용을 더한 감시 단가는 $1.815298/시간이었다. 이전에 종료한 Pod나 다른 자원은 변경하지 않았다.

전용 사전 host key와 strict SSH로 새 연결을 확인했다. Python 3.11.10, 실제 A100-SXM4-80GB·81,920 MiB, driver 595.91.07을 확인했고 cgroup RAM 한도는 249,999,998,976 bytes였다. 같은 source manifest 해시와 10개 bundle 파일 SHA가 원격 readback과 일치했다. 원격 CPU stdlib 안전 fixture 8개가 새로 PASS했다. 취소·timeout·guardian 죽음·실패 후손 정리·부모 SIGTERM/SIGKILL·arming 전 부모 죽음·정상 gate release를 포함한다. 회수한 fixture/preflight/source-readback 원본 3개는 원격 size·전체 SHA와 일치했다.

새 Linux Python 3.11 venv에 설치하고 실제 runtime audit·pip check를 통과했다. 직접 버전은 torch 2.9.1+cu128, transformers 5.17.0, accelerate 1.12.0, safetensors 0.8.0, Pillow 11.3.0, psutil 7.2.2다. diffusers는 고정 revision `b800f828f3951c4d206e154411bcbfa693cd322e`이며 실제 pipeline SHA는 앞선 `e75e4ce38d38e194edaac818bba99b2115b4bb2bfdbd15ce03a2813b0fe8856c`와 일치했다. CUDA runtime 12.8·bfloat16 지원과 58개 설치 archive의 해시를 기록했다. 직접 pin과 실제 해결된 버전 기록이며 완전한 사전 transitive lock으로 주장하지 않는다.

공식 Hugging Face 고정 revision에서 새 메타데이터를 조회하고 인증 없이 **24개·33,131,601,593 bytes**를 원격에 직접 다운로드했다. 중복 HF cache 없이 regular file로 저장하고 각 파일의 크기·스트림 SHA·전체 readback SHA, 공식 LFS SHA 또는 Git blob 식별값을 확인했다. **15:25:18 KST(06:25:18 UTC)**에 완료했다. 로컬에는 모델·venv를 회수하지 않았다.

| 이번 원본 기록 | SHA-256 |
| --- | --- |
| 실제 runtime audit | `8d97430ce8c08f8a8133e1e9777e860850af8ed0a6a9302b4b31f1277fada45e` |
| 새 모델 24개 전체 해시 검증 manifest | `2179e331ecb509d669ae1c5ea8f6c392799e47e15fb8cb8d1373490bdbaa0a29` |

### 이번 실제 입력과 worker 결과

이번 새 run의 실제 `input.txt`는 다음과 같다.

> A small yellow ceramic teapot on a blue wooden table beside a single white flower, soft daylight, simple studio photograph, no text.

파란 나무 탁자 위의 작은 노란 도자기 찻주전자와 흰 꽃 한 송이를 부드러운 자연광의 단순한 스튜디오 사진으로 표현하고 글자는 넣지 않는 장면이다. 실제 request는 seed 0, 512×512, 4 steps, guidance scale 4.0이다. worker에 설정된 negative prompt는 빈 문자열, `true_cfg_scale=4.0`, 이미지 한 장, `use_kv_cache=False`다. 4 steps는 기본 연결·작동을 확인하려던 smoke 조건이며 품질 평가용 조건이 아니다. 입력 SHA-256은 `6368dc479347370182a0521c7be3a0c64d20cc5457b30f9a7136183e4aed7b9a`다.

같은 worker·helper·placement를 변경 없이 한 번 실행했다. 그러나 기록된 단계는 **loading뿐**이며 running/이미지 생성 호출 도달은 확인되지 않았다. worker는 `failed / inference_failed`를 반환했다. harness의 실패 기록은 `worker_did_not_generate:inference_failed`, duration 약 106.954초다. 외부 18GiB RSS guard는 유지됐고 211개 표본의 RSS peak는 **10,860,793,856 bytes**로 guard를 넘지 않았다. 이는 표본 합계이며 OS hard quota나 모든 순간의 peak는 아니다.

worker 로그에는 checkpoint shard 2/2와 weights 750/750 로딩, CPU/disk offload에 따른 meta-device 안내 후 generic `inference_failed`만 남았다. harness의 `ValueError`는 실패 결과 검증용 wrapper이며 모델 내부 원예외 타입이 아니다. 원예외 타입·안전 스택이 보존되지 않아 정확한 원인은 미확정이다. 이 안내만으로 OOM·GPU 고장·placement 오류·모델 호환성 문제를 확정하지 않는다. 다음 재실행을 검토하기 전에 비밀값 없는 원예외 분류·진단 보강이 필요하다. 이번에는 추가 코드 수정이나 원인 추적용 실행을 하지 않았다.

| 항목 | 재개 실행 판정 |
| --- | --- |
| 실제 환경·고정 runtime·CUDA 준비 | 확인 |
| 공식 모델 24개 새 다운로드·전체 바이트 해시 | 확인 |
| 실제 Pod CPU 안전 fixture 8개 | PASS |
| 동일 worker 로딩 | 실제 수행 후 실패 |
| 실제 이미지 추론 성공 | 실패, running 도달 증거 없음 |
| 새 PNG·이미지 metadata | 0개 |
| 의도적인 잘못된 입력 오류 case | 미수행 — 이번 실제 로딩 실패와 구분 |
| 실GPU worker loading 취소 | 미수행 — CPU fixture 취소와 구분 |
| 실패 worker의 process group 정리 | `group_terminated=true`, live 후손 0 |

### 회수·한 번의 검토·즉시 종료

사용자의 비용 절약 지시에 따라 실패 확정 후 추가 시도 없이 소형 오류·출처·리소스·runtime·모델 해시 기록만 회수했다. 아카이브는 **181,306 bytes**, SHA-256 `09b57425b2fdca4cd6fdc4bee76ef4d77905431e4b31a227f9dc91923f9033ff`다. 포함한 **17개 파일 모두** 원격 manifest와 로컬 size·전체 SHA가 일치했다. 모델·offload·venv·인증 자료는 회수하지 않았다. 독립 검토자가 실패·PNG 0·후손 0과 회수 해시를 한 번 확인한 직후 종료를 요청했다.

- **15:33:34.916 KST(06:33:34.916 UTC)**: 현재 새 immutable Pod에만 종료 요청.
- **15:33:36.079 KST(06:33:36.079 UTC)**: DELETE 204.
- **15:33:36.951 KST(06:33:36.951 UTC)**: GET 404·목록 부재 확인, controller 종료. 별도 감독도 확인했다.
- **15:33:58 KST(06:33:58 UTC)**: 별도 읽기 재확인에서 v2 대상 GET 404, v2·REST v1 목록 HTTP 200 및 대상 부재.
- 새 network volume·다른 독립 storage 생성 0. Pod 수명에 묶인 볼륨은 해당 Pod 삭제에 따라 종료되는 형태다. 이번 재개에 의해 과금 중인 새 Pod·독립 storage가 남아 있다는 증거는 없다. 기존 자원은 변경하지 않았다.

마지막 해당 Pod 전용 billing 조회는 HTTP 200이나 record가 아직 없어 **확정 청구 금액은 미집계**다. 마지막 별도 확인 시각까지 보수적으로 계산한 새 재개 비용 상한 추정은 **$0.423334**, 앞선 $0.096825를 합친 **누적 추정은 $0.520159**다. 이를 최종 invoice나 실제 비용 $0으로 표현하지 않는다. 최초 origin부터 약 27분 이내에 종료 확인을 마쳤으며, 남은 시간은 사용하지 않았다.

최종적으로 기반 환경과 모델 준비는 확인했고 실패 근거를 보존·검토한 뒤 새 Pod를 삭제했다. 실제 Qwen 이미지 생성 검증은 미완료이며 다른 모델·Windows 로컬 8GB·앱 원격 통합·일반 품질에 대한 성공 판정으로 확대하지 않는다. 원시 로그·계정·개인 경로·Pod/호스트 식별값·키는 공개하지 않는다.

## 2026-10-18 로딩 실패 진단과 로컬 수정 후보

이 절은 앞선 실패 기록을 진단 입력으로 읽어 조사하고, 새 로컬 수정 후보를 검증한 결과다. 이 변경을 위해 새 Pod, 원격 실행, 모델 다운로드 또는 GPU 추론을 수행하지 않았다. 앞선 `loading` 실패가 실제 GPU에서 해결됐다는 판정은 아니다. 다른 모델 검수는 보류한다.

### 확인된 결함과 원인 확정의 한계

원래 worker는 허용된 오류 코드 외의 예외를 `inference_failed`로 바꾸면서 원예외의 타입·원인·스택을 보존하지 않았다. 회수 로그의 transformer/text encoder 가중치 진행 뒤에 VAE 로드·offload, processor 로드, scheduler/pipeline 생성과 첫 CUDA 동기화가 남아 있어 정확한 과거 실패 위치는 확정할 수 없다. CPU/disk offload의 meta 안내 자체는 오류 증거가 아니다.

다만 **필수 processor 의존성 누락**은 확인했다. 지정된 fresh venv 설치 보고서에 `torchvision`이 없지만, 고정 모델의 processor 구성은 `Qwen3VLVideoProcessor`를 포함한다. Transformers 5.17은 텍스트 이미지 생성 요청에서도 processor의 기본 모달리티 구성요소를 로드하며, AutoVideoProcessor는 vision/torchvision backend를 요구한다. 이미지 processor만의 PIL 대체 가능성은 이 video processor 계약을 없애지 않는다. [고정 모달리티 로딩 코드](https://github.com/huggingface/transformers/blob/v5.17.0/src/transformers/processing_utils.py#L1820-L1878), [AutoVideoProcessor backend guard](https://github.com/huggingface/transformers/blob/v5.17.0/src/transformers/models/auto/video_processing_auto.py#L229).

공식 고정 revision에서 다시 읽은 image/video processor 구성의 SHA-256은 회수된 모델 검증 기록과 각각 일치했다.

- image 구성: `93585062a80db5e8ca038efc7726a3e6411d9db948472d81d63c6303993be8c5`
- video 구성: `59c5c9eb52182eb14c06ffb10ca9effd29adce5f238a95de23ca14a38dbd2cb1`

[모델 processor 고정 원본](https://huggingface.co/Qwen/Qwen-Image-2.1/tree/d26bb61231c349cf6b7896fa83353113880e1ba3/processor). 이 누락은 관측된 실패 구간과 일치하는 준비 결함이며, 앞선 실행의 유일한 원인이라고 단정하지 않는다. 다른 offload·메모리·호환성 오류의 존재도 아직 배제하지 않았다.

### 검토 중인 최소 수정

- 공식 호환 조합인 `torchvision==0.24.1+cu128`을 `torch==2.9.1+cu128` 옆에 고정하고 정확한 버전·누락 검사를 추가했다. [PyTorch 공식 버전 표](https://pytorch.org/get-started/previous-versions/#v291).
- 작은 local-only processor를 가중치보다 먼저 로드해 backend 실패를 일찍 확인한다. 모델 revision, placement, VAE offload 및 생성 조건은 유지한다. 로드 실패 시 `tempfile.tempdir`도 복구한다.
- 명시적 opt-in `AI_MANAGER_IMAGE_DIAGNOSTICS=1`에서만 private 구조화 진단을 남긴다. 세부 로딩 단계·고정 라이브러리 버전·자원 카운터·device map 범주·제한된 예외 체인과 스택 구조를 수집한다. 예외 message, 소스 코드, 함수명, locals, 입력, 경로, URL, 환경 변수 원문은 저장하지 않는다. 최대 64개 이벤트·128 KiB이며 기존 파일은 덮어쓰지 않는다. 진단 쓰기 실패가 원래 결과와 오류를 바꾸지 않게 한다.
- 새 private Linux harness는 실제 worker 자식 환경에 opt-in을 명시하고 성공·실패 모두에서 bounded 진단과 failure 기록을 회수 목록에 넣는다. 원래 번들과 회수 증거는 보존했다.

현재 소스 후보 해시:

| 항목 | SHA-256 |
| --- | --- |
| worker | `7f5569e85c0d6a5d7da3fdd75c0303fd92e9872001b29c6fa6c85eff6e9573f8` |
| 진단 모듈 | `3038ac948ea56426bd445fc7cdd916a7dcdc1235ba26212c5adafcc5621007b8` |
| image runtime lock | `cdf8c00ba403be82320063558555706e284df67de2cd9d814c625d26a7290392` |
| 새 private bundle manifest | `9ebb9d17ec74e752250e1c4668c5187f272d264a3c946edf142c0d759e6776b5` |

### 새 로컬 검증과 범위

- 구현 담당의 변경 관련 4개 모듈 focused CPU 테스트 27개가 통과했다. 전체 기능 회귀 suite는 이번에 실행하지 않았다. 모의 구성요소의 단계별 실패, 체인 구조, 개인정보 sentinel, opt-in·크기·파일 보존·쓰기 실패를 확인했다.
- 같은 새 missing-backend stub을 원본 worker와 후보에 주입한 CPU 순서 비교에서, 원본은 transformer/text encoder/VAE 호출 뒤 실패했지만 후보는 processor 단계에서 가중치 호출 없이 실패했다. 임시 디렉터리 설정의 복구도 확인했다. 실제 Transformers processor나 모델 가중치를 로드한 실험은 아니다.
- 고정 upstream의 실제 backend guard 함수를 AST로 추출한 소형 CPU 실험은 torchvision 가용성 stub이 없으면 `ImportError`, 있으면 guard 통과를 확인했다. 전체 processor의 before/after 실환경 성공을 뜻하지 않는다.
- 새 wheel의 모듈 포함·격리 import·합성 invalid request 실패 동작을 확인했다. 새 private bundle은 11개 파일 해시와 worker/진단 import·compile·placement 보존 등 10개 검사를 통과했다. harness 환경·회수·원실패 보존 8개 검사와 WSL의 Linux stdlib guardian 8개 검사도 통과했다.

이 테스트들은 GPU 로딩·이미지 생성·실GPU 취소·화질·Windows 8GB 또는 앱 원격 통합을 검증하지 않았다. 변경된 runtime의 실제 설치 보고서와 wheel 해시는 향후 새 환경에서 다시 수집해야 한다. 공개 main에는 M10 제품 코드의 전체 의존 구성이 아직 없으므로 이번 코드는 검토된 로컬 후보이며, 이 문서만으로 실행 가능한 새 공개 릴리스가 제공된다고 해석하지 않는다.

### 새 Pod 생성 전 제시할 재실행 계획

1. 진단 privacy·의존성·새 source/bundle 해시의 독립 검토 결과와 실행 계획을 사용자에게 먼저 보고한다. 이 조사·로컬 검증은 새 Pod 생성 승인이 아니다.
2. 재실행이 승인되면 지정 Secure A100 SXM4 80GB/GPU 1개 범위에서 새 견적·잔액·시간 및 총비용 한도를 확인하고, 기존 비용·종료 이력을 보존한다. 작업 중단·회수·삭제 deadline과 lease/controller를 먼저 검증하며 다른 GPU·Cloud로 임의 대체하지 않는다.
3. 엄격한 SSH 신원 확인 및 해당 Pod의 CPU fixture를 먼저 통과시킨 뒤 새 runtime을 격리 설치한다. torchvision을 포함한 실제 설치 보고서·해시, 고정 pipeline·processor config를 확인한다. 가중치 로드 전 **실제 local-only processor 로드**가 통과해야 한다.
4. 그다음 동일 placement와 조건으로 한 번의 bounded Qwen smoke를 진행한다. 실패하면 새 세부 단계와 bounded 오류 구조·자원 기록을 회수하고 반복하지 않는다. 성공하면 새 PNG·metadata와 원격/로컬 full SHA를 확인한다.
5. 필수 결과를 회수하고 한 번 검토한 직후 신규 immutable Pod만 삭제하며, 404·목록 부재·신규 잔여 스토리지·비용 근거를 확인한다. 이전 실패나 CPU mock을 새 GPU 성공 근거로 사용하지 않는다.

## 4차: 수정본 Secure Cloud 실제 단일 이미지 생성과 즉시 종료

판정: **확인한 Secure A100 SXM4 80GB 환경에서 수정 worker의 로딩·단일 smoke·PNG 무결성 회수 PASS**. 이미지 내용의 시각적 품질 평가, 다른 모델의 대체 검수, Windows 8GB 로컬 성공, 앱 원격 통합 또는 전체 M10 완료 판정은 아니다. 과거 로딩 실패의 원예외가 사후 확정된 것도 아니다.

### 승인과 시간·비용 통제

사용자가 수정본의 동일 Qwen 검증 재개를 명시 승인했다. 기존 사용분을 포함한 총 $5 한도, 성공·실패 근거 회수와 한 번의 검토 직후 즉시 삭제, 기존 자료·보안 설정 보존을 적용했다. 다른 모델은 보류했다.

최초 origin `06:06:40.380 UTC`와 기존 절대 work-stop `07:36:40.380 UTC`, terminate 시작 `07:41:40.380 UTC`, hard-policy `08:06:40.380 UTC`를 유지했다. 시계를 새로 시작하지 않았다. 생성 전 work-stop까지 20분 이상 남아 있어야 한다는 추가 gate를 통과했다. 이전 비용은 청구 미집계 상태여서 보수 추정 **$0.520159**를 합산했다. 240초 operator lease, detached controller, UTC/monotonic 중 보수 경과 시간, 관측 GET의 제한된 transient retry, 신규 immutable ID 고정 삭제와 단일 POST 원칙을 유지했다.

생성 전 새 조회는 Secure SXM4 재고 `MEDIUM`, GPU `$1.79/시간`, 예산 충족을 확인했다. 새 Pod의 실제 응답도 `cloud=SECURE`, `NVIDIA A100-SXM4-80GB ×1`, container 20GB + Pod volume 150GB였다. 새 network volume은 만들지 않았다. GPU 실제 단가에 storage를 보수적으로 추가한 계산 요율은 **$1.815298/시간**으로 $2/시간 방어 상한 아래였다. 카탈로그만으로 실제 배치 성공을 주장하지 않았으며 이번에는 실제 응답을 확인했다.

| 사건 | UTC | KST |
| --- | --- | --- |
| 새 Pod 생성 | 2026-10-18 07:11:01.518 | 2026-10-18 16:11:01.518 |
| 실제 processor gate 통과, 가중치 0개 | 07:14:45 | 16:14:45 |
| 모델 24개 파일 해시 확인 완료 | 07:15:59.796 | 16:15:59.796 |
| 새 worker run 출처 기록 | 07:16:56 | 16:16:56 |
| 필수 결과 회수·검토 후 삭제 요청 | 07:19:31.954 | 16:19:31.954 |
| controller의 404·목록 부재 확인 | 07:19:40.467 | 16:19:40.467 |
| 별도 최종 읽기 확인 | 07:19:47.576 | 16:19:47.576 |

### 새 환경과 로딩 검증

새 task 전용 SSH client/host key를 사용하고 사전에 고정한 host public key와 `StrictHostKeyChecking=yes`로 연결했다. 계정 global SSH 설정은 바꾸지 않았다. 계정 API key는 로컬 controller 메모리에만 두었고 PIN은 controller·Pod에 전달하지 않았다. 원격에서 API key와 임시 host-private-key 환경 변수의 잔류가 없음을 확인했다.

Python 3.11.10, A100 SXM4 80GB, driver 570.172.08과 새 disk를 확인했다. 해당 Pod에서 bundle manifest와 11개 파일 해시를 확인하고 Linux stdlib 프로세스 fixture 8개를 실제 실행해 통과했다. 해당 호스트의 cgroup 경계는 이번 표본에서 노출되지 않았으므로 host RAM 수치를 Pod의 강제 메모리 quota로 주장하지 않는다. worker의 18GiB sampled RSS guard와 최소 3GiB available guard는 그대로 유지했다.

고정 runtime을 새 venv에 설치하고 `pip check` 및 runtime audit를 통과했다. 주요 pins는 torch `2.9.1+cu128`, torchvision `0.24.1+cu128`, Transformers `5.17.0`, Accelerate `1.12.0`, safetensors `0.8.0`, Pillow `11.3.0`, psutil `7.2.2`다. diffusers commit과 pipeline SHA는 앞 절의 고정값과 일치했다. 이번 설치 보고서와 wheel/source archive 해시를 새로 회수했으며, 이전 설치 보고서로 변경 runtime을 대신 검증하지 않았다.

먼저 processor 구성·tokenizer **9개 파일 / 15,884,996 bytes**만 공개 고정 revision에서 직접 준비했다. 가중치 safetensors가 **0개**인 상태에서 `Qwen3VLProcessor`와 image/video processor의 실제 `local_files_only=True`, `trust_remote_code=False` 로드가 통과했다. 그 뒤에만 동일 모델 24개 파일 **33,131,601,593 bytes**를 다운로드했다. 공식 revision·size·LFS SHA 또는 Git blob을 대조하고 stream/readback full SHA-256 및 regular file을 전수 확인했다. 이전 Pod나 모델 캐시를 연결하지 않았다.

현재 실행 source/bundle 해시는 앞 절의 후보와 그대로 일치한다. worker `7f5569e85c0d6a5d7da3fdd75c0303fd92e9872001b29c6fa6c85eff6e9573f8`, 진단 모듈 `3038ac948ea56426bd445fc7cdd916a7dcdc1235ba26212c5adafcc5621007b8`, lock `cdf8c00ba403be82320063558555706e284df67de2cd9d814c625d26a7290392`, bundle manifest `9ebb9d17ec74e752250e1c4668c5187f272d264a3c946edf142c0d759e6776b5`다. 원래 GPU/CPU placement와 모델·pipeline은 바꾸지 않았다.

### 실제 생성 조건과 결과

이번 새 run은 `image-success-59ab9bce3c94412ea025f5f20a0cba4d`다. 승인된 고정 harness의 smoke 입력 상수를 이번 새 run 디렉터리의 새 요청·입력 파일에 기록했다. 아래 문구는 이전 시도와 동일한 고정 주전자 prompt이며 새로 고안한 장면이라는 뜻은 아니다. 이전 input 파일이나 생성 이미지를 복사하지 않았고, 실제 입력은 아래와 같다.

> A small yellow ceramic teapot on a blue wooden table beside a single white flower, soft daylight, simple studio photograph, no text.

파란 나무 탁자 위의 작은 노란 도자기 주전자와 흰 꽃 한 송이를 자연광의 단순한 스튜디오 사진처럼 생성하는 요청이다. 입력 SHA-256은 `6368dc479347370182a0521c7be3a0c64d20cc5457b30f9a7136183e4aed7b9a`다.

| 조건 | 실제 값 |
| --- | --- |
| 크기 / 이미지 수 | 512×512 / 1개 |
| seed / dtype | 0 / bfloat16 |
| steps | 4, 기본 동작 확인용 smoke |
| true_cfg_scale / negative prompt | 4.0 / 빈 문자열 |
| use_kv_cache | false |
| 모델·코드 | 고정 Qwen-Image-2.1 revision / QwenImage21Pipeline |
| 실행 결과 | loading → running → validating, worker exit 0, `generated` |
| 구조 검증 | `generated_verified`, 512×512 RGBA, 8-bit, non-interlaced |
| PNG | 185,256 bytes |
| PNG SHA-256 | `6977f1ac24974f7bc00400314de337619a5c1b27359699862e334e71727d1462` |

4 steps는 품질 평가용 설정이 아니다. 공식 예시의 40 steps·2048 크기와 같은 품질이나 공식 권장 VRAM 달성을 뜻하지 않는다. PNG 내용을 시각적으로 열어보지 않고 정규 파일·PNG CRC/decode·구조·메타데이터·run ID·입력 및 출력 hash를 검증했다.

| 측정 항목 | 값과 한계 |
| --- | --- |
| worker 콜드 로딩 | 16.176초 |
| worker 추론 | 49.072초 |
| 전체 harness 실행 | 71.631초 |
| GPU peak allocated | 4,197,161,984 bytes |
| GPU peak reserved | 4,938,792,960 bytes |
| 외부 sampled RSS 최대 | 13,801,709,568 bytes, 142개 표본의 소유 프로세스 그룹 RSS 합 |
| 프로세스 정리 | group terminated=true, live members after=0 |
| opt-in 진단 | 24개 이벤트 / 7,612 bytes, failure 이벤트 0개 |

GPU allocated/reserved는 CUDA context나 시스템 전체 VRAM과 같지 않으며, sampled RSS는 강제 OS quota나 연속 최대치가 아니다. 이 수치로 8GB GPU·32GB RAM의 Windows 로컬 성공을 추론하지 않는다.

### 회수·한 번의 검토·즉시 삭제

PNG·metadata·request·provenance·resource·diagnostic·runtime·processor·model hash·프로세스 정리 근거를 포함한 소형 원본 **25개**를 회수했다. archive는 **371,155 bytes**, SHA-256 `e50516fd3c67b710403add45c9beae3abc9c38bea13c5b0e3dc1cc6d8d708add`다. 원격 manifest와 로컬의 파일 크기·full SHA-256이 25개 모두 일치했다.

독립 reviewer가 회수 원본과 PNG 구조·metadata·조건·모델 SHA·후손 0을 한 번 검토해 필수 결과를 확인했다. 별도 감독도 정상 실행과 종료를 읽기 전용으로 확인했다. 추가 실험·오류 재현·GPU 취소 실행·반복 추론 없이 즉시 삭제 요청했다.

삭제 후 controller가 대상 `GET 404`와 v2 목록 부재를 확인했으며 별도 읽기 조회에서도 `GET 404`, v2/v1 목록의 대상 부재를 확인했다. 새 network volume은 0개이고 새 Pod volume은 해당 Pod 종료 수명을 따른다. 종료 뒤 남겨둔 별도 신규 storage는 없다. 다른 기존 Pod·storage와 Windows 앱·자료·인증·DB는 제어하지 않았다.

마지막 Pod별 billing 조회는 HTTP 200이지만 기록 0개로 **청구 미집계**였다. 확정 비용이 0이라는 뜻이 아니다. 최종 읽기 시점까지의 보수 추정은 이번 **$0.265265**, 이전 **$0.520159**, 합계 **$0.785424**다. 제공자 청구가 집계되면 그 값이 우선하며 이 수치는 확정 invoice가 아니다. Pod는 최대 2시간을 채우지 않고 약 8분 39초 만에 삭제 확인했다.

이번에 실제 수정본의 processor·모델 로딩과 단일 GPU 생성은 검증했지만, 원래 실패 예외가 보존되지 않았으므로 과거 실패의 유일 원인 확정, 실제 GPU 오류·취소, 장시간 안정성·품질 평가, Windows 8GB 또는 앱 원격 통합은 미검증으로 유지한다. 제품 코드·태그·Release를 이번 결과 보고와 함께 게시하지 않는다.

## 5차: 공식 권장 2K·40 steps 고품질 1장과 즉시 종료

판정: **공식 권장 예시 조건을 적용한 새 full-GPU HQ profile의 실제 단일 이미지 생성·회수 PASS**. “모델이 낼 수 있는 최대”라는 요청은 전역적인 최고 품질을 증명한다는 뜻으로 해석하지 않고, 고정 공식 문서의 고품질 예시를 실제 실행하는 범위로 구체화했다. 한 장만 생성했으며 다른 seed·해상도·설정의 탐색이나 실패 후 낮은 품질 재시도는 하지 않았다.

### 공식 설정과 별도 profile

고정 model card의 text-to-image 예시는 bfloat16 pipeline을 새로 로드해 `.to('cuda')`로 이동하고 **2048×2048, 40 steps, seed 42**를 사용한다. 고정 pipeline의 guidance 기본값은 1.0이며 Qwen-Image 2.1을 guidance 없이 sampling하도록 설명한다. 이번에는 **true_cfg_scale=1.0, negative_prompt=None, use_kv_cache=True, num_images_per_prompt=1**로 실행했다. 고정 model index에는 steps를 덮어쓰는 `sample_sigmas`가 없었다. [고정 모델 공식 예시](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/README.md), [고정 pipeline 설정과 설명](https://github.com/huggingface/diffusers/blob/b800f828f3951c4d206e154411bcbfa693cd322e/src/diffusers/pipelines/qwenimage21/pipeline_qwenimage21.py#L511-L571).

512×512·4 steps·CFG 4의 기존 smoke 계약을 바꾸지 않고 별도 HQ worker/profile을 만들었다. 기존 device-map/offload 객체에 GPU 이동을 추가하지 않았다. 공식 경로대로 **새 no-device-map·no-offload-hook pipeline**을 로드한 뒤 CUDA로 옮기고, 모델 파라미터·buffer의 실제 CUDA 배치와 부동소수 파라미터의 bfloat16을 확인했다. 양자화·compile·CPU/disk offload fallback은 사용하지 않았다.

가중치 파일은 총 33,115,613,408 bytes, 약 30.84GiB다. 이것만으로 고해상도 활성값·KV cache·VAE 피크가 맞는다고 단정하지 않았다. 실행 전 GPU total≥78GiB/free≥70GiB, RAM available≥64GiB 등 실제 preflight를 확인했다. 외부 sampled guard는 소유 프로세스 그룹 RSS 64GiB, host available 8GiB, GPU free 4GiB 기준을 적용했다. 이는 OS 강제 quota가 아니며 allocation 사이 OOM을 원천 보장하지 않는다.

소스 준비 단계에서는 HQ 관련 focused CPU 테스트 9개와 기존 관련 테스트 18개, harness 계약 27개, bundle readback/import 검사 8개, 별도 WSL guardian 검사 8개를 확인했다. GPU 첫 표본이 `None`으로 들어가는 실제 루프 반례를 고친 뒤 subsecond 첫 관측 양성·관측 실패 시 정리 음성을 추가 검증했다. 이 로컬 검증을 실제 2K 성공 근거로 대신하지 않았고, 아래 새 실행을 따로 수집했다.

| 실행 source | SHA-256 |
| --- | --- |
| HQ worker | `aa8975f2f2f5447f4d425bfdd101fbb8d6cf6fb97f4b3dcbe3085edcac2f716d` |
| HQ helper | `b5f6f98ca08c08d33258da88badffa8e5ce5fdbbc033e7c82e0311d17527a5e3` |
| HQ harness | `5857e2ddb55a0a42908e79f3dde25e85e47816224b12f864db2f8571336ffb73` |
| HQ bundle manifest, 12개 파일 | `eb457f83ba0165011bd34d3459abd49aea339835f76b7cc5aad8180268494568` |

기존 smoke worker `7f5569e85c0d6a5d7da3fdd75c0303fd92e9872001b29c6fa6c85eff6e9573f8`, 진단 모듈과 runtime lock은 그대로 유지했다. 공용 PNG 검증 helper는 기존 기본 2MiB 상한을 유지하고 HQ만 명시적 32MiB 상한을 선택하도록 했다. 이 변경을 제품 코드·새 앱 릴리스로 공개한 것은 아니다.

### 추가 시간의 명시 승인과 새 실행 경계

기존 절대 작업 시각을 임의로 연장하지 않았다. 07:33:18 UTC 조사 때 기존 work-stop까지 약 3분만 남아 새 생성이 차단된 사실을 먼저 보고했다. 사용자에게 공식 HQ 계획·수정/검증 결과·비용안을 알린 뒤 **이번 1장에 한해 추가 최대 45분**을 명시 승인받았다.

새 window는 실제 create intent부터 작업 30분, 삭제 시작 35분, 정리 상한 45분으로 별도 고정했다. 기존 비용은 그대로 합산했다. 새 controller는 UTC/monotonic 중 보수 경과 시간, 240초 lease, GET 한정 bounded transient retry, POST 1회와 신규 immutable ID 고정 정리를 적용했다. 총요율 $2/시간 초과 또는 scope 불일치 시 작업 없이 정리하는 조건도 유지했다. 이 정책은 provider의 계정 hard spending cap을 뜻하지 않는다.

생성 전 fresh Secure 조회는 SXM4 재고 `HIGH`, GPU $1.79/시간, 예산 충족을 확인했다. 과거 첫 두 Pod의 billing에는 각각 약 $0.064954246와 $0.415575722가 집계됐으나 나머지가 미집계여서 정책에는 기존의 더 보수적인 누적 **$0.785424**를 적용했다. 45분 전부를 $2/시간 상한으로 사용해도 누적 추정 $2.285424로 총 $5 아래였지만 남은 시간을 채우기 위해 Pod를 유지하지 않았다.

| 사건 | UTC | KST |
| --- | --- | --- |
| 새 create intent | 2026-10-18 07:48:43.071 | 2026-10-18 16:48:43.071 |
| 실제 새 Pod 생성 | 07:48:44.253 | 16:48:44.253 |
| 실제 processor gate, 가중치 0개 | 07:56:16 | 16:56:16 |
| 24개 모델 full SHA 완료 | 07:58:37.709 | 16:58:37.709 |
| 새 HQ run 출처 기록 | 07:59:32 | 16:59:32 |
| 결과 회수·1회 검토 뒤 삭제 요청 | 08:03:12.762 | 17:03:12.762 |
| controller의 삭제 확인 | 08:03:18.288 | 17:03:18.288 |
| 별도 최종 읽기 확인 | 08:03:31.242 | 17:03:31.242 |

고정한 work-stop은 **08:18:43.071 UTC**, terminate 시작은 **08:23:43.071 UTC**, hard-policy는 **08:33:43.071 UTC**였다. 원격 harness에 create intent+30분의 동일 UTC 값을 전달해 readback했고, 그 UTC와 monotonic deadline을 모델 재해시·spawn 전·실행 루프에서 확인했다. 실제 worker timeout은 남은 시간에서 회수 여유를 뺀 **1,086초**로 선택해 1,500초 고정 상한보다 짧게 적용했다.

### 해당 Pod의 실제 준비와 단일 생성

실제 응답은 Secure Cloud A100 SXM4 80GB 1개, container 20GB + Pod volume 150GB였다. 새 network volume은 0개다. 실제 GPU 단가 $1.79/시간에 storage를 보수적으로 추가한 계산 요율은 **$1.815298/시간**이었다. 새 task 전용 SSH key와 사전 host pin으로 연결했고 계정 global SSH 설정은 바꾸지 않았다. API key는 원격에 보내지 않았으며 PIN은 controller·Pod에 전달하지 않았다.

Python 3.11.10, driver 580.126.16, 실제 A100 SXM4를 확인했다. 해당 Pod에서 source manifest 12개 파일의 SHA와 Linux stdlib CPU fixture 8개를 확인했다. 노출된 cgroup memory limit은 285,999,996,928 bytes였다. Host RAM/df 표본을 Pod quota와 혼동하지 않았고 GPU·RSS·host available guard를 별도로 적용했다.

새 runtime 설치 보고서·wheel/source archive hash와 `pip check`를 회수했다. torch 2.9.1+cu128, torchvision 0.24.1+cu128 및 앞선 고정 라이브러리/pipeline pins가 일치했다. 먼저 processor 9개 파일 15,884,996 bytes를 준비해 가중치 0개 상태의 실제 local-only processor gate를 통과했고, 이후 고정 모델 24개 파일 33,131,601,593 bytes를 공개 공식 endpoint에서 새로 받아 regular file·공식 revision/size/LFS 또는 Git blob·stream/readback full SHA를 전수 확인했다. 이전 Pod·모델 cache·이미지는 연결하지 않았다.

이번 새 run은 `image-hq-8fb47c2124c94614b6e86ab86ad83349`다. 이전 주전자 문구를 반복하지 않고 이번에 새로 작성한 prompt를 HQ 요청·메타데이터에 기록했다.

> A monumental stone observatory on a rugged coastal cliff at sunrise, waves breaking far below, intricate weathered stone carvings, copper instruments and clear glass lenses, wild grasses moving in the sea breeze, luminous clouds, rich natural textures, cinematic yet physically plausible lighting, balanced composition, extraordinary fine detail, no text, no logo, no watermark.

일출 무렵 거친 해안 절벽의 석조 관측소, 부서지는 파도, 풍화된 돌 조각과 구리 관측 도구·유리 렌즈, 풀과 구름의 질감을 자세하게 그리는 요청이다. 새 입력 SHA-256은 `71b8a114e83b14978266c13a70a1ba846c00b4054971e7335a6a4e46268c1485`다.

| 실제 생성 결과 | 값 |
| --- | --- |
| Profile / 호출 수 | `qwen-image-2.1-official-hq-single-v1` / pipeline 1회 |
| 설정 | 2048×2048, 40 steps, seed 42, CFG 1.0, negative=None, KV cache=True |
| 이미지 수 / 자동 재시도 | 1 / 0 |
| 실행 | `generated`, worker exit 0, 구조 검증 `generated_verified` |
| PNG 구조 | 2048×2048 RGBA, 8-bit, non-interlaced |
| PNG 크기 | 8,483,741 bytes |
| PNG SHA-256 | `02e13fcf4a47139a1b54010f1961897c568f9b1f6fa3055d642db5a6c8d509c1` |
| Worker 로딩 | 15.072초 |
| Worker 추론 | 80.667초 |
| Harness 실행 | 118.367초 |
| GPU peak allocated | 60,691,260,416 bytes |
| GPU peak reserved | 68,467,818,496 bytes |
| 외부 sampled RSS 최대 | 11,487,084,544 bytes / 227개 표본 |
| 외부 표본의 최소 GPU free | 16,077,815,808 bytes |
| 프로세스 정리 | group terminated=true, live members after=0 |
| 진단 | 14개 이벤트 / 4,356 bytes, failure 0개 |

GPU allocated/reserved, sampled device free와 RSS는 각기 다른 관측값이다. 모든 메모리·성능 환경의 최대치를 뜻하지 않는다. per-step callback은 자원 guard만 수행했으므로 중간 step 번호의 독립 로그는 없으며, 진행률 숫자를 추정하지 않았다. 40 steps 요청·고정 pipeline의 정상 반환·최종 출력과 metadata의 정합을 확인했다.

### 회수·검토·종료·비용과 한계

PNG, metadata, request, provenance, resource/diagnostic, runtime/processor/model 무결성·프로세스 정리 근거의 소형 원본 **25개**를 회수했다. archive는 **8,674,329 bytes**, SHA-256 `3c791a91cd118b8d89460feadb2d845cf9de64f810dd7c60ca53abeb255e6e70`다. 25개 파일의 원격/로컬 크기와 full SHA-256이 모두 일치했다.

독립 reviewer가 정규 파일·PNG CRC/decode·2048 RGBA 구조·metadata/ID/조건/prompt hash·full-GPU source 계약·모델 SHA·후손 0을 한 번 확인했고, 즉시 신규 Pod 삭제를 요청했다. 별도 감독도 읽기 전용으로 실행과 종료를 확인했다. 결과를 사용자에게 표시할 원본으로 보존했지만 주관적 품질 점수나 절대 최고 화질 판정은 부여하지 않았다. 추가 생성·다른 seed·낮은 해상도 fallback·재현 실험은 하지 않았다.

삭제 후 controller와 별도 읽기 확인에서 대상 **GET 404**, v2/v1 목록 부재를 확인했다. 신규 network volume 0개이며 별도 잔류 신규 storage를 만들지 않았다. Pod volume은 삭제된 해당 Pod의 수명을 따른다. Controller도 종료됐고, 이전 Pod·다른 storage·기존 자료·Windows 앱·인증·DB는 제어하지 않았다.

이번 Pod의 최종 billing 조회는 HTTP 200이지만 기록 0개로 **청구 미집계**다. 확정 비용이 0이라는 뜻은 아니다. 최종 읽기 시각까지의 보수 추정은 이번 **$0.447264**, 이전 **$0.785424**, 누적 **$1.232688**이다. 일부 과거 청구는 집계됐지만 이 누적값은 아직 확정 invoice가 아니다. 실제 새 Pod는 약 **14분 34초** 만에 삭제 확인했으며 승인된 45분을 채우지 않았다.

이번 완료 범위는 확인한 A100 80GB·공식 권장 고품질 예시·새 prompt의 단일 이미지 생성과 회수다. 절대 최고 품질, 다양한 prompt 일반화, 주관적 우열, 전체 기능 회귀, 장시간 안정성, 실제 GPU 취소, Windows 8GB 로컬 성공 또는 앱의 원격 통합으로 확대하지 않는다. 제품 코드·PNG·태그·Release를 이 보고와 함께 공개하지 않는다.
