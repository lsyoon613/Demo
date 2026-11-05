# 공개 GitHub 저장소 올리기

이 폴더가 **독립 저장소의 루트**입니다. 공개 저장소는 <https://github.com/lsyoon613/Demo>이며, 게시 뒤 수정할 때는 기존 저장소에 업데이트하세요.

1. 이 폴더의 게시 저장소는 <https://github.com/lsyoon613/Demo>입니다. 새 저장소를 다시 만들 필요는 없습니다.
2. 저장소를 새로 클론했다면 이후 수정 사항은 해당 클론에서 `git add`, `git commit`, `git push`로 갱신합니다. 브라우저에서 업로드할 때는 아래 모든 하위 폴더가 함께 올라갔는지 확인하세요.

```powershell
git clone https://github.com/lsyoon613/Demo.git
cd Demo
# 이 폴더의 변경 파일과 하위 폴더를 클론한 Demo 폴더로 복사한 뒤:
git add .
git status --short
git commit -m "Update standalone synthesis route review"
git push -u origin main
```

`git status --short`에서 `.venv`, `.admet-venv`, `models/`, 별도 원본 `catalog.sqlite`, 공급사 원본 SDF, `verified_reports/`, `__pycache__/`가 포함되지 않았는지 확인하세요. **`data/catalog_bundle/manifest.json`과 `part-001.bin`~`part-003.bin`은 반드시 포함**해야 합니다. 이 분할 파일 안에는 실행용 Enamine 전체 구조 인덱스와 확보된 포장별 연구용 견적이 들어 있으므로 공개 저장소에서 누구나 내려받을 수 있습니다.

Git 사용이 어렵다면 새 저장소의 **Add file → Upload files**에 저장소 루트의 파일과 `src/`, `tests/`, `scripts/`, `docs/`, `data/`, `price_db/`, `examples/` 디렉터리를 함께 끌어다 놓고 공개 커밋할 수 있습니다. 브라우저 직접 업로드에는 `.gitignore`의 자동 제외 규칙이 적용되지 않으므로 위의 제외 목록을 직접 확인하세요. 상위 `09_GitHub_업로드_준비` 폴더 자체를 한 단계 더 중첩하지 마세요. 숨김 파일 `.gitignore`도 포함하세요.

게시 후 다음 문장을 Codex에 그대로 전달할 수 있습니다.

> `https://github.com/lsyoon613/Demo`를 클론하고 README.md를 읽어 Windows 3.11 환경에서 `install.ps1`로 설치해 줘. 이 명령이 GitHub의 분할 Enamine 자료를 검증해 로컬 DB로 복원하는지 확인하고, `doctor.py`와 `tests/`의 단위 검사 및 Enamine/ZINC 아스피린 실시간 검색을 실행해 줘. ASKCOS와 ADMET-AI는 README의 선택 구성에 따라 설치해 줘.

**정확한 범위:** Enamine 1,173,509건 구조 인덱스와 ZINC 경로 검색·식별자·HTML 생성은 설치 후 각자의 PC에서 실행됩니다. 포장별 가격은 데이터베이스에 기록된 3,908건의 시점별 관측 견적만 확인할 수 있으며 나머지 제품의 가격은 미확인입니다. ASKCOS 전파/AMES는 각각 별도 백엔드/모델이 필요하고, NDMA 위험을 저장소만으로 검증할 수는 없습니다. 원본 2.34 GB Enamine SDF는 포함하지 않습니다.
