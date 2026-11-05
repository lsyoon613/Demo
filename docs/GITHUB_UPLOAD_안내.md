# 공개 GitHub 저장소 올리기

이 폴더가 **독립 저장소의 루트**입니다. 아직 GitHub 계정에 게시하지 않았습니다. `gh` CLI/인증이 이 PC에 없어 공개 저장소를 자동 생성할 수 없었습니다.

1. 이 폴더의 게시 저장소는 <https://github.com/lsyoon613/Demo>입니다. 새 저장소를 다시 만들 필요는 없습니다.
2. Windows PowerShell에서 이 폴더로 이동한 다음, 아래 명령을 실행합니다. GitHub 인증은 사용자가 Git Credential Manager 브라우저 창에서 완료합니다.

```powershell
git init -b main
git remote add origin https://github.com/lsyoon613/Demo.git
git add .
git status --short
git commit -m "Release standalone synthesis route review"
git push -u origin main
```

`git status --short`에서 `.venv`, `.admet-venv`, `models/`, `catalog.sqlite`, 공급사 SDF, 개별 견적 CSV, `verified_reports/`, `__pycache__/`, 접근 토큰이 포함되지 않았는지 확인하세요. 이 업로드용 폴더에는 해당 대형/사적 파일이 들어 있지 않습니다.

Git 사용이 어렵다면 새 저장소의 **Add file → Upload files**에 저장소 루트의 파일과 `src/`, `tests/`, `scripts/`, `docs/`, `data/`, `price_db/`, `examples/` 디렉터리를 함께 끌어다 놓고 공개 커밋할 수 있습니다. 브라우저 직접 업로드에는 `.gitignore`의 자동 제외 규칙이 적용되지 않으므로 위의 제외 목록을 직접 확인하세요. 상위 `09_GitHub_업로드_준비` 폴더 자체를 한 단계 더 중첩하지 마세요. 숨김 파일 `.gitignore`도 포함하세요.

게시 후 다음 문장을 Codex에 그대로 전달할 수 있습니다.

> `https://github.com/lsyoon613/Demo`를 클론하고 README.md를 읽어 Windows 3.11 환경에서 `install.ps1`로 설치해 줘. `doctor.py`와 `tests/`의 단위 검사를 실행하고 ZINC 아스피린 검색을 확인해 줘. Enamine 기능은 `docs/REMOTE_ENAMINE_설정.md`에 따라 서버 주소·접근 토큰을 별도로 받아 사용하거나, 허가받은 SDF로 개인용 DB를 만들어 줘. ASKCOS와 ADMET-AI는 README의 선택 구성에 따라 설치해 줘.

**정확한 범위:** 핵심 ZINC 경로 검색·식별자·HTML 생성은 공개 모델 다운로드 후 사용 가능합니다. ASKCOS 전파/AMES는 각각 별도 백엔드/모델이 필요합니다. Enamine 경로 탐색과 제품 일치·견적은 **운영 중인 인증된 원격 서버** 또는 각자의 SDF·가격 자료가 있어야 동작합니다. GitHub 저장소에는 서버 주소·토큰·원본 자료가 들어 있지 않으며 저장소 게시만으로 Enamine 기능이 자동 연결되지는 않습니다. 공개 저장소만으로 완전한 공급사 가격이나 NDMA 위험을 검증할 수는 없습니다.
