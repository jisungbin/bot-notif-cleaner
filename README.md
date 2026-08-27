# Bot Notification Cleaner

github.com 에 접속할 때마다 **Renovate·Dependabot 이 만든 PR 알림을 자동으로 Done 처리**하는 크롬 확장.
알림함에는 사람이 만든 PR·리뷰 요청만 남는다.

## 구조

```
content script (github.com/*)  ──sendMessage──▶  background.js (MV3 SW)
                                                      │ 쿨다운(30s) 통과 시
                                                      ▼ connectNative
                                                 host/notif-host.py
                                                      │ gh auth token → REST 직접 호출
                                                      ▼
                              GET /notifications → PR 작성자 조회 → DELETE /threads/{id}
                                                      │
   배지 (-N / ✓ / ⚠)  ◀────── {done, scanned, error?} ─────┘
```

- **Extension**: 트리거와 결과 표시만 담당. github.com full page load 마다 host 를 깨우되 30초 쿨다운을 둔다(탭 여러 개·연속 새로고침 중복 방지). 툴바 아이콘 클릭은 쿨다운을 무시하고 즉시 실행.
- **호스트(`notif-host.py`)**: 판정과 API 호출 전부. `gh auth token` 으로 토큰만 얻고 이후는 `urllib` 로 직접 호출한다(알림 수만큼 `gh` 를 spawn 하면 프로세스 생성 비용이 몇 초로 불어난다). PR 작성자 조회는 8-way 병렬 + `~/.cache/bot-notif-cleaner/authors.json` 캐시.

판정은 **PR 작성자**로만 한다 — `subject.url` 을 조회해 `user.login` 이 `renovate[bot]`/`dependabot[bot]` 인 것만 Done. 제목 휴리스틱을 쓰지 않으므로 사람 PR 을 오탐하지 않는다. 조회 실패·타임아웃은 건너뛰고 지우지 않는다.

## 설치

**준비**: `brew install gh`, `gh auth login`

### 1. Extension 로드 (→ Extension ID 확정)

1. `chrome://extensions` → 우상단 **개발자 모드** ON
2. **압축해제된 확장 프로그램을 로드** → `extension/` 폴더 선택
3. 카드에 표시되는 **ID** 복사

### 2. 네이티브 호스트 설치

```bash
./install.sh <복사한_EXTENSION_ID>
```

### 3. gh 토큰 스코프 확인

```bash
gh api /notifications --jq 'length'   # 숫자가 나오면 OK
```

403 이면 `notifications` 스코프를 추가한다. (`repo` 스코프가 있으면 대개 그대로 통과한다.)

```bash
gh auth refresh -h github.com -s notifications
```

### 4. 확장 reload

`chrome://extensions` 에서 reload → github.com 접속.

## 배지

| 배지 | 의미 |
|------|------|
| `…` (회색) | 스캔 중 |
| `-N` (초록) | N건 Done 처리 (4초 후 사라짐) |
| `✓` (회색) | 대상 없음 (4초 후 사라짐) |
| `⚠` (빨강) | 오류 — 아이콘에 마우스를 올리면 사유 표시. 조치할 때까지 남아있다 |

## 디버깅

```bash
python3 host/notif-host.py --dry    # 판정 결과만 출력, 아무것도 지우지 않음
```

확장 쪽 로그는 `chrome://extensions` → 카드의 **서비스 워커** 링크 → 콘솔에서 `[NotifCleaner]` prefix 로 확인.
