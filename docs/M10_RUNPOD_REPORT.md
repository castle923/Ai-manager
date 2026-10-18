# M10 Runpod 원격 검증 보고

최신 상태: Secure 단일 Pod의 strict SSH·GPU 식별·자동 안전 종료 확인, 실제 이미지 검증 미완료. 아래 두 시도는 분리한 기록이다.

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
