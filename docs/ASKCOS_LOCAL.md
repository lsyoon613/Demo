# ASKCOS 연결 실패 (127.0.0.1:9100)

앱 화면이 열리지만 QUARC / WLDN5 / Impurity Predictor 모두 `WinError 10061`이라면 **해당 사용자의 PC에서 ASKCOS 계산 서버가 실행되지 않은 상태**입니다. 앱 포트 8502와 계산 서버 포트 9100은 별개입니다. Enamine 자료만으로 이 예측 모델들을 실행할 수는 없습니다.

`start.bat`은 앱, AiZynthFinder와 Enamine 자료를 준비합니다. **Docker/WSL2와 ASKCOS 모델 설치는 자동으로 수행하지 않습니다.** AMES도 `.admet-venv` 별도 설치가 필요합니다.

## 새 PC

1. WSL2 및 Docker 환경을 설치합니다.
2. [ASKCOS 공식 로컬 배포 안내](https://askcos-docs.mit.edu/guide/4-Deployment/4.1-Customizing-local-deployment.html) 또는 [개별 모듈 배포 안내](https://askcos-docs.mit.edu/guide/4-Deployment/4.2-Standalone-deployment-of-individual-modules.html)를 따라 API gateway, QUARC, WLDN5, Impurity Predictor, Fast Filter 및 필요한 의존 서비스/모델을 설치합니다.
3. gateway를 호스트 `127.0.0.1:9100`에 연결합니다. 컨테이너 내부의 모델 서버 주소는 배포 구성에 맞춰 연결해야 합니다.
4. `http://127.0.0.1:9100/docs`를 열어 gateway 동작을 확인하고, 각 예측 모듈이 준비된 후 앱에서 다시 실행합니다. docs 응답만으로 개별 모델 준비가 보장되지는 않습니다.

이 저장소에는 ASKCOS 컨테이너 이미지/모델과 새 PC용 완전 자동 설치 프로그램이 포함되어 있지 않습니다. 위 공식 배포 과정이 필요합니다.

## 이미 ASKCOS를 설치한 개발 PC

`C:\AI_Drug_Discovery\2026\2026-여름\학술제\tools\synthesis\askcos`의 PowerShell에서:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\local.ps1 -Action Start
```

이 명령은 **해당 폴더와 ASKCOS 환경이 이미 있는 개발 PC 전용**입니다. GitHub 클론만 받은 새 PC에서는 사용할 수 없습니다.
