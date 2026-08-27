const HOST = "com.forky.notifcleaner";
const COOLDOWN_MS = 30_000;
const TIMEOUT_MS = 120_000;

const log = (...a) => console.log("[NotifCleaner]", ...a);
const warn = (...a) => console.warn("[NotifCleaner]", ...a);
const err = (...a) => console.error("[NotifCleaner]", ...a);

let running = false;

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg?.trigger !== "visit") return;
  log("트리거: github.com 방문", sender.tab?.url);
  runIfDue();
});

chrome.action.onClicked.addListener(() => {
  log("트리거: 아이콘 클릭 (쿨다운 무시)");
  run();
});

async function runIfDue() {
  const { lastRun = 0 } = await chrome.storage.local.get("lastRun");
  const elapsed = Date.now() - lastRun;
  if (elapsed < COOLDOWN_MS) {
    log(`쿨다운 중 — skip (${Math.round((COOLDOWN_MS - elapsed) / 1000)}s 남음)`);
    return;
  }
  run();
}

// 요청-응답 1회로 끝내고 port 를 닫는다 — host 는 stdin EOF 로 종료된다.
function run() {
  if (running) { log("이미 실행 중 — skip"); return; }
  running = true;
  chrome.storage.local.set({ lastRun: Date.now() });

  setBadge("…", "#8c959f");

  let port;
  try {
    port = chrome.runtime.connectNative(HOST);
  } catch (e) {
    running = false;
    err("connectNative 실패:", e.message);
    showError("native host 연결 실패 — install.sh 를 실행했는지 확인");
    return;
  }

  const timer = setTimeout(() => {
    warn("응답 타임아웃");
    finish(port, () => showError("host 응답 타임아웃"));
  }, TIMEOUT_MS);

  port.onMessage.addListener((res) => {
    clearTimeout(timer);
    log("응답:", JSON.stringify(res));
    finish(port, () => {
      if (res?.error) showError(res.error);
      else flashBadge(res?.done ?? 0, res?.scanned ?? 0);
    });
  });

  port.onDisconnect.addListener(() => {
    const e = chrome.runtime.lastError;
    if (running) {
      clearTimeout(timer);
      running = false;
      warn("응답 전 disconnect:", e && e.message);
      showError(e?.message || "host 가 응답 없이 종료됨");
    }
  });

  log("postMessage → run");
  port.postMessage({ run: true });
}

function finish(port, after) {
  running = false;
  after();
  try { port.disconnect(); } catch (_) {}
}

function flashBadge(done, scanned) {
  const text = done > 0 ? `-${done}` : "✓";
  log(`결과: ${done}건 Done (PR 알림 ${scanned}건 스캔)`);
  chrome.action.setTitle({ title: `봇 PR 알림 정리 — ${done}건 Done / ${scanned}건 스캔` });
  setBadge(text, done > 0 ? "#1a7f37" : "#8c959f");
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 4000);
}

// 오류 배지는 지우지 않는다 — 스코프 부족처럼 사용자 조치가 필요한 상태를 계속 보이게 한다.
function showError(message) {
  err(message);
  chrome.action.setTitle({ title: `봇 PR 알림 정리 — 오류: ${message}` });
  setBadge("⚠", "#cf222e");
}

function setBadge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
}
