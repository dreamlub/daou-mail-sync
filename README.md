# Daou Mail Sync

다우오피스 메일을 개인 Gmail 계정으로 비파괴 복사하는 도구입니다. 현재 계정은
IMAP에서 빈 사서함을 반환하므로, 실제 받은메일을 제공하는 POP3를 기본 수집 경로로
사용합니다.

- 다우오피스는 POP3 SSL로 읽기만 하며 삭제 명령을 사용하지 않습니다.
- Gmail에는 원문 메시지를 직접 삽입합니다. SMTP 자동 전달을 사용하지 않습니다.
- POP3 `UIDL`을 SQLite에 기록해 증분 실행합니다.
- 동일한 원문은 SHA-256으로 감지해 중복 삽입하지 않습니다.
- 메일 제목, 발신자, 본문은 로그에 출력하지 않습니다.
- 휴지통과 스팸 폴더는 기본적으로 제외합니다.

## 설치

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Google 인증

OAuth 클라이언트에는 Gmail API가 활성화되어 있어야 합니다.

```powershell
.\.venv\Scripts\python.exe -m daou_mail_sync.cli auth-google `
  --client-secret C:\path\to\client-secret.json `
  --token-file data\google-token.json `
  --account tony.waldlust@gmail.com
```

인증 도중 반드시 `tony.waldlust@gmail.com` 계정을 선택합니다. 다른 계정으로 인증하면
토큰을 저장하지 않고 종료합니다.

## 드라이런

```powershell
$env:DAOU_IMAP_USER = "tony@waldlust.co.kr"
.\.venv\Scripts\python.exe -m daou_mail_sync.cli save-daou-password
.\.venv\Scripts\python.exe -m daou_mail_sync.cli sync
```

비밀번호는 화면에 표시되지 않는 프롬프트에서 한 번 입력합니다. 다우 POP3 로그인이
성공한 경우에만 Windows 자격 증명 저장소에 보관됩니다. 드라이런은 폴더별 UID만 읽고
메일 본문이나 첨부파일을 가져오지 않으며 Gmail도 변경하지 않습니다.

## 소량 적용과 전체 복사

```powershell
# 먼저 3개만 복사
.\.venv\Scripts\python.exe -m daou_mail_sync.cli sync --apply --yes --limit 3

# 확인 후 나머지 전체 복사
.\.venv\Scripts\python.exe -m daou_mail_sync.cli sync --apply --yes
```

다우오피스 원본 메일은 삭제하거나 플래그를 변경하지 않습니다.

POP3에서는 기존 읽음 상태를 제공하지 않으므로 최초 412개는 모두 읽음으로 복사합니다.
자동 동기화에서는 `--pop-mark-unread`를 사용해 이후 새 메일을 Gmail에서 안읽음으로
복사하고, POP3와 IMAP의 Message-ID가 일치하는지 확인한 뒤 다우오피스 원본에서도
읽음 표시를 제거합니다.

## 10분마다 새 메일 동기화

소량 적용과 전체 복사를 확인한 뒤 아래 스크립트를 한 번 실행합니다.

```powershell
.\scripts\install-scheduled-task.ps1
```

Windows 작업 스케줄러에 `Daou Mail Sync to Gmail` 작업이 등록됩니다. 중복 실행은
허용하지 않으며 실행 결과에는 메일 내용 없이 건수와 성공 여부만 `data\sync.log`에
기록됩니다. 컴퓨터가 켜져 있고 현재 Windows 사용자가 로그인한 동안 10분마다 PowerShell
창을 표시하지 않고 실행됩니다.

## 결재 내역 수집 (초과근무명령서)

메일과 달리 결재에는 표준 프로토콜이 없어 다우오피스 웹 세션을 사용합니다. 다만 화면을
파싱하지는 않고, 결재 화면이 스스로 호출하는 JSON API를 그대로 씁니다. HTML을 읽는 곳은
문서 본문 한 군데뿐입니다.

| 용도 | 엔드포인트 |
| --- | --- |
| 로그인 | `POST /api/portal/public/auth/login` |
| 문서함 목록 | `GET /gw/api/approval/doclist/<타입>/<탭>` |
| 부서 문서함 | `GET /gw/api/approval/deptfolder/<타입>/<부서ID>` |
| 문서 상세 | `GET /gw/api/approval/document/<문서ID>` |

문서함마다 정렬 키(`property`)가 달라서 다른 값을 보내면 HTTP 500이 돌아옵니다. 확인된
조합은 `folders.py`에 있습니다. 임시 저장함은 제출되지 않은 초안만 있어 제외했습니다.

### 비밀번호 저장

메일용 POP3 비밀번호와 별개로 웹 로그인 자격 증명을 저장합니다.

```powershell
$env:DAOU_LOGIN_ID = "<다우오피스 로그인 ID>"
.\.venv\Scripts\python.exe -m daou_approval.cli save-password
```

로그인에 성공한 경우에만 Windows 자격 증명 저장소에 보관합니다. 로그인 실패가 누적되면
다우오피스가 캡차를 요구하며, 그 시점부터 자동 실행은 멈춥니다. 브라우저에서 한 번
로그인해 캡차를 해제한 뒤 다시 실행해야 합니다.

### 수집과 내보내기

```powershell
# 어떤 문서함에 몇 건이 있는지만 확인 (본문을 내려받지 않음)
.\.venv\Scripts\python.exe -m daou_approval.cli sync --dry-run

# 먼저 5건만
.\.venv\Scripts\python.exe -m daou_approval.cli sync --limit 5

# 확인 후 전체
.\.venv\Scripts\python.exe -m daou_approval.cli sync

# 엑셀로 내보내기
.\.venv\Scripts\python.exe -m daou_approval.cli export --out data\overtime.xlsx

# CSV가 필요하면 (UTF-8 BOM, Excel에서 바로 열림)
.\.venv\Scripts\python.exe -m daou_approval.cli export --out data\overtime.csv
```

출력 형식은 확장자를 따릅니다. `.xlsx`는 머리글 고정과 필터가 붙은 실제 엑셀 표(`OvertimeOrders`)로,
분 단위 컬럼은 숫자로 들어가 바로 합산됩니다. 사유가 `=`로 시작해도 수식으로 해석되지 않습니다.

기본값은 결재양식에 `초과근무명령서`가 포함된 문서만 수집합니다. `--form`으로 다른 양식을,
`--all-forms`로 전체를 받을 수 있습니다. `--since 2026-01-01`은 그 이전 기안 문서를 건너뜁니다.

### 동작 방식

- 볼 수 있는 문서함을 모두 돌고 `documentId`로 중복을 제거합니다. 같은 문서가 여러 문서함에
  나타나면 본문은 한 번만 내려받고, 어느 문서함에서 나왔는지는 `document_folders`에 모두
  기록합니다.
- 이미 저장한 문서는 결재 상태가 바뀐 경우에만 다시 내려받습니다.
- 목록에는 보이지만 열람 권한이 없는 문서가 있습니다. 목록 응답의 `readable` 플래그가 이를
  정확히 예고하므로(확인 시점 기준 17건 전부 일치) 요청을 낭비하지 않고 건너뛰고, 목록
  메타데이터만 `body_available = 0`으로 저장합니다.
- 초과근무명령서 양식은 두 세대가 섞여 있습니다. 2025년 양식은 `일시`/`사유` 한 쌍이고,
  현행 양식은 연장근로(A)와 야간근로(B)를 분리해 총 시간(C)을 따로 둡니다. 파서가 둘 다
  처리하며 어느 쪽인지 `form_layout`에 남깁니다.
- 읽기 전용입니다. 문서를 열람 처리하거나 결재하거나 수정하지 않습니다.

### 파서를 고친 뒤 다시 파싱하기

본문은 그대로 보관하므로, 파서를 고쳤을 때 다우오피스에 다시 접속하지 않고 저장된 본문만
다시 훑을 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m daou_approval.cli reparse
```

### 구글 시트로 올리기

SQLite는 증분 실행용 캐시이고, 보는 곳은 구글 시트입니다. Gmail과 별도의 토큰과 스코프
(`spreadsheets`)를 씁니다. **Google Cloud 프로젝트에서 Google Sheets API를 켜 두어야
합니다.** Gmail API만 켜져 있으면 첫 실행에서 거부됩니다.

```powershell
.\.venv\Scripts\python.exe -m daou_approval.cli auth-sheets `
  --client-secret C:\path	o\client-secret.json

.\.venv\Scripts\python.exe -m daou_approval.cli push-sheets
```

동의 화면에서 고른 구글 계정에 시트가 생성됩니다. 생성된 스프레드시트 ID는 `meta`
테이블에 기록되어, 이후 `push-sheets`는 **같은 시트를 제자리에서 갱신**합니다. URL이
바뀌지 않으므로 북마크나 다른 시트의 참조가 끊기지 않습니다.

- 머리글 행은 고정되고 필터가 걸립니다.
- 분 단위 컬럼은 숫자로 들어가 시트에서 바로 합산할 수 있습니다.
- 값은 `RAW`로 씁니다. 사유가 `-`나 `=`로 시작해도 수식으로 해석되지 않습니다.
- 다른 시트에 올리려면 `--spreadsheet-id`를, 제목을 바꾸려면 `--title`을 씁니다.
