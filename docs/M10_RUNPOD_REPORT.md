# M10 Runpod 원격 검증 준비와 재고 차단 보고

기록일: 2026-10-18. 판정: **Community Cloud A100 80GB 재고 BLOCK, 실제 GPU 실행 미수행**.

이 문서는 이번 원격 검증 시도의 읽기 전용 사전 확인 결과만 기록한다. M10 전체 완료, Windows 로컬 8GB GPU 성공, 앱의 원격 실행 통합 완료를 뜻하지 않는다.

## 승인 범위와 중단 조건

사용자가 승인한 범위는 새 Runpod Community Cloud A100 80GB Pod 한 개에서 같은 이미지 worker를 실제 실행하고, 결과를 회수해 해시를 비교한 뒤 해당 새 Pod를 종료하는 것이다. 상한은 생성·과금 시점부터 최대 2시간, GPU와 설치·다운로드 시간 및 선택한 스토리지를 합쳐 총 $5 이내다. 기존 Pod와 다른 작업, 기존 자료는 보존한다.

Community Cloud만 허용하며 Secure Cloud나 다른 GPU로 대체하지 않는다. 재고나 실배치 견적을 확인하지 못하면 생성하지 않는다. 예산·시간의 충분한 여유를 남겨 작업 중단, 회수, 종료를 수행하도록 사전 준비한다. API의 초 단위 사용료 계산은 계정 차원의 강제 지출 상한을 보장하지 않는다.

## 이번에 확인한 사실

Runpod 읽기 인증은 성공했다. 예산 확인에 필요한 잔액 조회도 성공했고 승인 예산을 충족했다. 잔액 금액과 계정 정보는 공개하지 않는다.

최종 조회는 **2026-10-18 14:48:09 KST (05:48:09 UTC)**에 수행했다. 공식 REST v2 GPU catalog에 `include=AVAILABILITY`, `product=POD`, `cloud=COMMUNITY`, `gpuCount=1`을 명시했다. 최소 CUDA 12.8 조건을 둔 조회와 CUDA 조건을 제거한 최종 조회에서 아래 두 GPU 모두 `availability: NONE`이었다. 지역·국가·최소 RAM·vCPU를 추가로 제한하지 않았다.

| GPU | VRAM | Community 카탈로그 가격 | 현재 조회의 가용성 |
| --- | --- | --- | --- |
| NVIDIA A100 80GB PCIe | 80 GB | $1.19/시간 | NONE |
| NVIDIA A100-SXM4-80GB | 80 GB | $1.39/시간 | NONE |

위 가격은 카탈로그 표시값이며 배치 가능한 호스트의 실견적이 아니다. 실제 호스트 RAM·디스크와 GPU·스토리지 합산 견적을 확정하지 않았다. 앞선 공식 GraphQL의 `secureCloud:false`, `gpuCount:1` 조회에서도 두 GPU의 `lowestPrice` 가격·재고 필드는 null이었다. null만으로 재고를 단정하지 않고 명시적인 Community REST v2 조회로 교차 확인했다. REST v2의 Cloud 필터를 생략하면 Secure가 기본이므로, 기본 Cloud 조회를 Community 재고 증거로 사용하지 않았다.

이 결과는 조회 시점의 재고 상태다. 실제 생성을 통한 용량 probe나 자동 반복 조회는 하지 않았다.

## 실행과 비용 상태

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

## 준비물과 검증 한계

같은 Ai-manager 프로젝트의 현재 이미지 worker를 변경 없이 Linux harness로 실행할 준비를 진행했다. 비공개 bundle 준비와 독립 검토 단계이며 Linux 실제 프로세스 그룹 취소 fixture, Linux 그룹 guardian 및 별도 시간·비용 watchdog의 실제 검증은 완료되지 않았다. guardian에 PID를 전달하기 전의 후손 프로세스 정리 보장도 잔여 검토 항목이다. 따라서 현재 bundle은 실행 준비 완료 상태가 아니며 실제 GPU 실행 성공 근거로 사용하지 않는다.

이번 준비에서 읽은 현재 소스의 SHA-256은 다음과 같다. 이 해시는 원격에 업로드하거나 실행한 코드의 검증 결과가 아니다.

| 파일 | SHA-256 |
| --- | --- |
| `image_worker.py` | `4bdeaa3113f6afc7aab77453d7cf067bc23d60034fa607c30ee9141a08b3b7dc` |
| `image_safe.py` | `c0d9233ea15ebdba83c18a05860d34f6edfa1cff624f540c8d554b46f17c63cb` |

예정 모델은 공식 `Qwen/Qwen-Image-2.1`의 고정 revision `d26bb61231c349cf6b7896fa83353113880e1ba3`이다. 이번에는 모델을 다운로드하지 않았다. Qwen Research License의 연구·평가 목적 비상업 조건을 전제로 하며, 필요한 동의는 사용자 직접행위다. 이번 시도의 원시 API 응답·계정·인증값·호스트·개인 경로·비공개 로그는 공개 저장소에 포함하지 않는다. 과거 생성 결과를 이번 성공 근거로 사용하지 않았다.

## 같은 승인 범위에서 재개할 조건

재개 시 Community A100 80GB 재고와 실제 배치 견적을 새로 확인하고, 호스트 RAM·디스크 및 선택 스토리지까지 합산해 2시간·$5 상한과 종료 여유를 검토해야 한다. 새 실행의 출처 기록, 고정 source·의존성·모델 해시 연결, Linux 취소 fixture, 시간·비용 deadline과 독립 watchdog, 새 Pod 식별값에만 고정된 회수·종료 경로를 생성 전에 검증해야 한다. 실제 결과를 회수해 해시를 확인한 다음 새 Pod의 종료, 목록 삭제, 새 잔여 스토리지 없음과 과금 종결 상태를 확인한다.

다른 GPU·Cloud 또는 비용·시간 상한 확대는 별도 승인 범위다. 현재 기록은 원격 검증 완료로 승격하지 않는다.

## 공식 출처

- [Runpod 공식 GPU 선택 안내](https://github.com/runpod/runpod-plugins-official/blob/main/plugins/runpod/skills/runpod-usage/reference/gpu-selection.md)
- [Runpod REST v2 OpenAPI](https://docs.runpod.io/api-reference-v2/openapi.json) — `GpuCloudFilter` 및 GPU catalog 정의
- [Runpod Pod 과금·스토리지 가격](https://docs.runpod.io/pods/pricing)
- [Runpod GraphQL GPU 가격·재고 조회](https://docs.runpod.io/sdks/graphql/manage-pods)
- [Qwen-Image-2.1 고정 revision 모델 문서](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/README.md)
- [같은 revision의 LICENSE](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/d26bb61231c349cf6b7896fa83353113880e1ba3/LICENSE)
