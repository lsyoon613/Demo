# start.bat 전체 로컬 준비

`start.bat`은 기본 앱 설치 다음에 `setup_full.ps1`을 실행합니다. ASKCOS 5개 필수 모듈과 AMES 모델 준비가 확인돼야 앱을 엽니다. 설치 실패를 숨기고 완료로 표시하지 않습니다.

## 처음 실행 시

1. 기본 Python 3.11 환경, Enamine 자료, AiZynthFinder 모델을 준비합니다.
2. ASKCOS의 `127.0.0.1:9100/api/admin/get-backend-status`에서 QUARC, WLDN5, Impurity Predictor, Fast Filter, Indigo의 준비 상태를 각각 확인합니다. 이미 모두 준비됐다면 기존 로컬 서버를 재사용합니다.
3. 준비된 서버가 없다면 WSL의 Ubuntu를 찾아 사용합니다. 없다면 Windows 관리자 승인 창을 통해 WSL/Ubuntu 설치를 시작합니다. **Windows가 재부팅 또는 Ubuntu 초기 사용자 등록을 요구하면 해당 절차를 마친 뒤 start.bat을 다시 누릅니다.** 설치 프로그램이 재부팅을 강제로 실행하지 않습니다.
4. Ubuntu에 Docker Engine/Compose를 준비하고, 고정 커밋의 ASKCOS 공식 소스를 다운로드합니다. 원본 CPU Dockerfile을 사용해 컨테이너를 빌드합니다. QUARC 모델/사전은 기록된 SHA-256과 크기를 확인합니다.
5. localhost 9100에 gateway를 시작하고 필수 모델 5개가 준비될 때까지 기다립니다.
6. `.admet-venv`에 ADMET-AI 2.0.1을 설치하고 실제 AMES 한 구조 추론을 실행합니다. 이 추론이 성공해야 완료 표시를 기록합니다.
7. 앱 서버를 시작하거나 동일 앱의 기존 실행 주소를 브라우저에 엽니다.

## 설치 시간과 저장 공간

### 검증 범위 (2026-11-05)

- 기존 WSL2 Ubuntu가 있는 개발 PC에서 고정 커밋의 소스 6개를 새로 다운로드하고 CPU 이미지 6개를 빌드했습니다.
- 별도 포트 19100의 새 컨테이너에서 필수 5개 모듈 준비 상태 및 프로프라놀롤 예제의 QUARC/WLDN5/Impurity Predictor 실제 호출 성공을 확인했습니다. 검증용 컨테이너는 종료합니다.
- 새 `.admet-venv`에서 ADMET-AI 설치와 실제 AMES 추론을 확인했습니다. pip 캐시는 사용됐습니다.
- QUARC 모델은 기존 로컬 파일을 캐시로 복사한 뒤 배포 manifest의 크기/SHA-256을 검증했습니다. 전체 QUARC 모델의 새 네트워크 다운로드 검증은 포함하지 않습니다.
- **WSL/Python이 없는 별도 PC에서 관리자 승인·재부팅을 포함한 최초 설치 전체는 아직 검증하지 못했습니다.**
- `scripts/verify_backends.py`로 설치 후 세 API의 실제 호출을 재검사할 수 있습니다. 출력은 `verified_reports/backend-smoke.json`에 저장합니다. 모델 예측 성공은 실험적 합성 성공을 의미하지 않습니다.

전체 설치는 기본 앱보다 훨씬 큽니다. QUARC 체크포인트만 약 1.84 GB이고, Docker 이미지와 패키지·소스·나머지 모델을 위한 추가 저장 공간이 필요합니다. 네트워크와 CPU에 따라 최초 준비에 오래 걸릴 수 있습니다. 기본 앱의 775 MB 모델 다운로드 수치는 ASKCOS/AMES까지 합친 크기가 아닙니다.

모든 원본·다운로드·Dockerfile은 `backends/askcos/` 하위에 생성하고, Docker 이미지·볼륨은 WSL 내부에 보관합니다. 소스 커밋은 `local_sources.json`, QUARC 모델 출처·해시는 `quarc_assets.json`으로 고정합니다. 공식 소스의 라이선스 파일을 보존하며, 이 앱의 MIT 라이선스가 외부 모델/소스의 라이선스를 대체하지 않습니다.

## 재실행과 오류

- 설치 도중 다운로드가 실패하면 start.bat을 다시 누릅니다. 받은 부분 파일과 Docker 빌드 캐시를 재사용합니다.
- 이미 설치한 Ubuntu가 여러 개면 `SYNTHESIS_WSL_DISTRO` 환경 변수로 사용할 배포판 이름을 지정할 수 있습니다.
- WSL2 설치는 Windows 가상화 기능이 필요하며 관리자 승인/재부팅이 요구될 수 있습니다.
- Docker 또는 모델 빌드가 실패하면 실행 창에 실패 단계가 남습니다. 전부 설치됐다고 표시하지 않습니다.
- 서버 상태만으로 특정 반응의 예측 성공을 보장하지는 않습니다. 개별 모델 호출 결과는 앱에서 별도로 확인합니다.
- 개발 PC의 다른 ASKCOS가 이미 정상 작동하면 이를 재사용합니다. 다른 앱의 컨테이너를 삭제하지 않습니다.

## ASKCOS 컨테이너 로그/종료

앱 폴더 PowerShell에서 (Ubuntu 이름은 선택한 배포판에 맞게 변경):

```powershell
$backend = (wsl -d Ubuntu -u root -- wslpath -a -u "$PWD\backends\askcos").Trim()
wsl -d Ubuntu -u root -- docker compose -f "$backend/compose.local.yaml" logs --tail 80
wsl -d Ubuntu -u root -- docker compose -f "$backend/compose.local.yaml" stop
```

앱 실행 창을 닫아도 Docker 모델 서버는 백그라운드에 남을 수 있습니다. 이미 다른 위치의 ASKCOS를 재사용한 경우에는 해당 배포 구성의 종료 명령을 사용하세요.
