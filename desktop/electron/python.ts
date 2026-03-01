import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as http from "http";

const API_PORT = 8321;
const API_HOST = "127.0.0.1";
const HEALTH_URL = `http://${API_HOST}:${API_PORT}/api/status`;

let pythonProcess: ChildProcess | null = null;

function getProjectRoot(): string {
  return path.resolve(__dirname, "..", "..");
}

function getPythonExe(): string {
  const root = getProjectRoot();
  return path.join(root, "venv", "Scripts", "python.exe");
}

export function spawnPython(): void {
  const root = getProjectRoot();
  const pythonExe = getPythonExe();

  console.log(`Starting Python API server from ${root}`);
  console.log(`Python: ${pythonExe}`);

  pythonProcess = spawn(
    pythonExe,
    [
      "-m",
      "uvicorn",
      "src.api.server:app",
      "--host",
      API_HOST,
      "--port",
      String(API_PORT),
      "--log-level",
      "warning",
    ],
    {
      cwd: root,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env },
    }
  );

  pythonProcess.stdout?.on("data", (data: Buffer) => {
    console.log(`[python] ${data.toString().trim()}`);
  });

  pythonProcess.stderr?.on("data", (data: Buffer) => {
    console.error(`[python] ${data.toString().trim()}`);
  });

  pythonProcess.on("exit", (code) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });
}

export function killPython(): void {
  if (!pythonProcess) return;

  const pid = pythonProcess.pid;
  console.log(`Killing Python process tree (PID ${pid})...`);
  pythonProcess = null;

  if (pid === undefined) return;

  try {
    require("child_process").execSync(
      `taskkill /PID ${pid} /T /F`,
      { stdio: "ignore" }
    );
  } catch {}
}

export function waitForHealth(
  timeoutMs: number = 60000
): Promise<void> {
  const start = Date.now();

  return new Promise((resolve, reject) => {
    const check = () => {
      if (Date.now() - start > timeoutMs) {
        reject(new Error("Python health check timed out"));
        return;
      }

      const req = http.get(HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          setTimeout(check, 500);
        }
      });

      req.on("error", () => {
        setTimeout(check, 500);
      });

      req.setTimeout(2000, () => {
        req.destroy();
        setTimeout(check, 500);
      });
    };

    check();
  });
}

export const API_BASE = `http://${API_HOST}:${API_PORT}`;
export const WS_BASE = `ws://${API_HOST}:${API_PORT}`;
