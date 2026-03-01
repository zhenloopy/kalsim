import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("kalsim", {
  apiBase: "http://127.0.0.1:8321",
  wsBase: "ws://127.0.0.1:8321",
});
