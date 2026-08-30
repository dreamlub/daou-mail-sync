# Daou Mail Sync

다우오피스 메일을 개인 Gmail 계정으로 비파괴 복사하는 도구입니다.

- 다우오피스는 IMAP SSL로 읽기만 합니다.
- Gmail에는 원문 메시지를 직접 삽입합니다. SMTP 자동 전달을 사용하지 않습니다.
- IMAP `UIDVALIDITY + UID`를 SQLite에 기록해 증분 실행합니다.
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

비밀번호는 화면에 표시되지 않는 프롬프트에서 한 번 입력합니다. 다우 IMAP 로그인이
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

## 15분마다 새 메일 동기화

소량 적용과 전체 복사를 확인한 뒤 아래 스크립트를 한 번 실행합니다.

```powershell
.\scripts\install-scheduled-task.ps1
```

Windows 작업 스케줄러에 `Daou Mail Sync to Gmail` 작업이 등록됩니다. 중복 실행은
허용하지 않으며 실행 결과에는 메일 내용 없이 건수와 성공 여부만 `data\sync.log`에
기록됩니다. 컴퓨터가 켜져 있고 현재 Windows 사용자가 로그인한 동안 15분마다 실행됩니다.
