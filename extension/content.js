// GitHub 은 Turbo 네비게이션이라 이 스크립트는 full page load 에서만 재실행된다.
chrome.runtime.sendMessage({ trigger: "visit" });
