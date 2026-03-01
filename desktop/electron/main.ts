import { app, BrowserWindow } from "electron";
import * as path from "path";
import { spawnPython, killPython, waitForHealth } from "./python";

let mainWindow: BrowserWindow | null = null;

const isDev = !app.isPackaged;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    backgroundColor: "#0a0a0f",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: "kalsim Risk Desk",
    autoHideMenuBar: true,
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  spawnPython();

  try {
    console.log("Waiting for Python API...");
    await waitForHealth(60000);
    console.log("Python API ready");
  } catch (err) {
    console.error("Failed to start Python API:", err);
    killPython();
    app.quit();
    return;
  }

  createWindow();
});

app.on("window-all-closed", () => {
  killPython();
  app.quit();
  process.exit(0);
});

app.on("before-quit", () => {
  killPython();
});
