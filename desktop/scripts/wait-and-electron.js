const http = require("http");
const { spawn } = require("child_process");

const VITE_URL = "http://localhost:5173";
const MAX_WAIT = 30000;

function checkVite() {
  return new Promise((resolve) => {
    const req = http.get(VITE_URL, (res) => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.setTimeout(1000, () => { req.destroy(); resolve(false); });
  });
}

async function main() {
  const start = Date.now();
  while (Date.now() - start < MAX_WAIT) {
    if (await checkVite()) {
      spawn(
        process.platform === "win32" ? "npx.cmd" : "npx",
        ["electron", "dist-electron/main.js"],
        { stdio: "inherit", shell: true }
      );
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  console.error("Timed out waiting for Vite");
  process.exit(1);
}

main();
