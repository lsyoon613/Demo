# Enamine 원격 서버 연결

GitHub에는 코드만 배포하고 Enamine SDF, `catalog.sqlite`, `enamine_inchikeys.txt`, 가격 CSV는 **서버 컴퓨터에만** 보관합니다. 원격 모드는 Enamine 경로 탐색(AiZynthFinder 재고 조회 포함)과 제품·포장 견적 조회를 서버에서 수행합니다. Streamlit 화면과 HTML 보고서 구성은 기존과 동일합니다. ZINC 탐색, PubChem/COCONUT, 로컬 ASKCOS/AMES는 기존 방식으로 실행합니다.

## 1. 서버 컴퓨터

서버에 이 프로젝트, AiZynthFinder 환경과 `models/`의 USPTO 모델, `price_db/enamine_inchikeys.txt`, `price_db/catalog.sqlite`를 준비합니다. Enamine SDF는 최초 DB 구축 뒤 요청마다 읽지 않습니다. 가격은 서버 DB에 실제 확인한 포장 견적만 나타납니다.

PowerShell에서 서버 전용 임의 비밀키를 설정하고 게이트웨이를 시작합니다. 시작 전 `python doctor.py`로 자산을 확인하세요.

```powershell
$env:SYNTHESIS_ENAMINE_SERVER_TOKEN = '<임의로 생성한 24자 이상의 비밀키>'
.\.venv\Scripts\python.exe -X utf8 src\remote_enamine.py
```

기본 주소는 `127.0.0.1:9200`이며 **노트북 외부에 공개되지 않습니다**. 다른 PC에서 쓰려면 HTTPS 역방향 프록시(또는 서버로 향하는 SSH 터널)를 구성하세요. 외부 접속 주소에는 HTTPS를 사용하고, 실제 DB·모델 파일을 프록시의 정적 파일 경로에 올리지 마세요. 동시 Enamine 경로 탐색은 서버 자원을 고려해 한 건으로 제한하며, 탐색 중 다른 탐색 요청은 HTTP 503을 돌려줍니다.

## 2. GitHub 클론 사용자

서버 운영자에게 **HTTPS 기본 주소와 접근용 토큰**을 별도로 받아 해당 PC의 PowerShell 세션에 설정합니다. 토큰을 GitHub, README, 공개 `.env`에 기록하지 않습니다.

```powershell
$env:SYNTHESIS_ENAMINE_API_URL = 'https://<실제-서버-도메인>'
$env:SYNTHESIS_ENAMINE_API_TOKEN = '<서버에서 받은 토큰>'
.\.venv\Scripts\python.exe -X utf8 doctor.py
.\start.bat
```

SSH 포트 포워딩으로 로컬 `127.0.0.1:9200`을 서버에 안전하게 연결했다면 `SYNTHESIS_ENAMINE_API_URL`에 `http://127.0.0.1:9200`도 사용할 수 있습니다. 일반 HTTP를 원격 호스트에 직접 사용하는 설정은 클라이언트에서 거부합니다.

클라이언트에는 Enamine SDF·DB·재고 파일이 없어도 **Enamine (2026-09)** 재고가 기존 선택 목록에 나타납니다. 목표물 입력→`새 경로 탐색`→경로·가격 비교는 기존 화면 그대로입니다. 서버가 내려가거나 인증에 실패하면 **미일치/0원으로 처리하지 않고 연결 오류**를 표시합니다. 환경 변수를 제거하면 기존 로컬 파일 기반 동작으로 돌아갑니다.

원격 API는 인증된 `POST /v1/search`와 `POST /v1/catalog` 두 기능만 제공하고, DB 파일 다운로드는 제공하지 않습니다. 응답으로 제품 ID·주소·해당 구조의 견적은 사용자에게 전달됩니다. 따라서 사용자 범위와 학부 비상업 연구용 가격 자료의 공유 가능 범위는 서버 운영 전에 확인해야 합니다. 공개 GitHub 저장소가 곧 누구나 접근할 수 있는 Enamine 서버를 뜻하지는 않습니다.
