#!/usr/bin/env python3
"""Chrome Native Messaging host: Renovate/Dependabot PR 알림을 Done 처리한다.

확장이 {"run": true} 를 보내면 GitHub 알림을 스캔해 봇이 만든 PR 알림만
DELETE /notifications/threads/{id} (mark as done) 하고 {"done", "scanned"} 를 응답한다.
`--dry` 로 직접 실행하면 판정 결과만 출력하고 아무것도 지우지 않는다.
"""
import sys, os, json, struct, subprocess, urllib.request, urllib.error, re
from concurrent.futures import ThreadPoolExecutor

# Chrome 이 spawn 하는 프로세스는 PATH 가 최소라 gh 를 못 찾음 → 보강
os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "/usr/bin:/bin")

BOTS = {"renovate[bot]", "dependabot[bot]"}
API = "https://api.github.com"
CACHE_PATH = os.path.expanduser("~/.cache/bot-notif-cleaner/authors.json")
SCOPE_HINT = "gh auth refresh -h github.com -s notifications 실행 필요"
WORKERS = 8
TIMEOUT = 20


def logv(*a):
    print(*a, file=sys.stderr, flush=True)  # stdout 은 NM 프로토콜 전용


def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))  # 4바이트 LE 길이 = NM 프로토콜
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def read_exactly(fd, n):
    buf = b""
    while len(buf) < n:
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            return None  # EOF
        buf += chunk
    return buf


def read_message(fd):
    head = read_exactly(fd, 4)
    if head is None:
        return None
    data = read_exactly(fd, struct.unpack("<I", head)[0])
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return {}


class ApiError(Exception):
    pass


def get_token():
    r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
    if r.returncode != 0 or not r.stdout.strip():
        raise ApiError("gh auth token 실패 — gh auth login 필요")
    return r.stdout.strip()


def request(token, method, url):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            body = res.read()
            payload = json.loads(body) if body and method == "GET" else None
            return res.status, res.headers, payload
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ApiError(SCOPE_HINT)
        raise


def next_link(headers):
    m = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("Link", "") or "")
    return m.group(1) if m else None


def list_notifications(token):
    # all=true 는 이미 Done 처리한 과거 알림까지 반환하는데 응답에 Done 여부 필드가 없어
    # 구분이 불가능하다 → 인박스와 어긋나고 같은 스레드를 매번 재처리하게 된다.
    url = f"{API}/notifications?per_page=100"
    threads = []
    while url:
        _, headers, page = request(token, "GET", url)
        threads.extend(page or [])
        url = next_link(headers)
    return threads


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logv("cache 저장 실패:", e)


def run(dry=False):
    token = get_token()
    threads = list_notifications(token)
    prs = [t for t in threads if (t.get("subject") or {}).get("type") == "PullRequest"]
    logv(f"알림 {len(threads)}건 중 PR {len(prs)}건")

    cache = load_cache()  # PR 작성자는 불변 → URL 로 영구 캐시 가능

    def author_of(pr_url):
        if pr_url in cache:
            return cache[pr_url]
        try:
            _, _, pr = request(token, "GET", pr_url)
        except ApiError:
            raise
        except Exception as e:
            logv("PR 조회 실패:", pr_url, e)
            return None  # 판정 불가 → Done 하지 않는다
        login = ((pr or {}).get("user") or {}).get("login")
        if login:
            cache[pr_url] = login
        return login

    urls = [t["subject"]["url"] for t in prs if t.get("subject", {}).get("url")]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        authors = dict(zip(urls, pool.map(author_of, urls)))
    save_cache(cache)

    targets = [t for t in prs if authors.get(t.get("subject", {}).get("url")) in BOTS]
    for t in targets:
        logv(f"  {'[dry] ' if dry else ''}done: {t['repository']['full_name']} — {t['subject']['title']}")

    if dry:
        return {"done": 0, "scanned": len(prs), "would_done": len(targets)}

    def mark(t):
        try:
            status, _, _ = request(token, "DELETE", f"{API}/notifications/threads/{t['id']}")
            return 200 <= status < 300
        except ApiError:
            raise
        except Exception as e:
            logv("done 실패:", t["id"], e)
            return False

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        done = sum(1 for ok in pool.map(mark, targets) if ok)

    return {"done": done, "scanned": len(prs)}


def main():
    if "--dry" in sys.argv:
        try:
            r = run(dry=True)
            print(f"\nPR 알림 {r['scanned']}건 중 봇 {r['would_done']}건 (dry — 아무것도 지우지 않음)")
        except ApiError as e:
            print(f"오류: {e}", file=sys.stderr)
            sys.exit(1)
        return

    fd = sys.stdin.fileno()
    while True:
        msg = read_message(fd)
        if msg is None:
            return  # port 닫힘
        if not msg.get("run"):
            continue
        try:
            send_message(run())
        except ApiError as e:
            send_message({"error": str(e)})
        except Exception as e:
            logv("run 실패:", repr(e))
            send_message({"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
