import { WSMessage } from "./types";

const WS_URL = "ws://127.0.0.1:8321/api/ws";
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_DELAY = 30000;

type Listener = (msg: WSMessage) => void;

class KalsimWS {
  private ws: WebSocket | null = null;
  private listeners: Set<Listener> = new Set();
  private reconnectDelay = RECONNECT_DELAY;
  private shouldReconnect = true;

  connect(): void {
    this.shouldReconnect = true;
    this._connect();
  }

  disconnect(): void {
    this.shouldReconnect = false;
    this.ws?.close();
    this.ws = null;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private _connect(): void {
    try {
      this.ws = new WebSocket(WS_URL);
    } catch {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelay = RECONNECT_DELAY;
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        this.listeners.forEach((fn) => fn(msg));
      } catch {}
    };

    this.ws.onclose = () => {
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private _scheduleReconnect(): void {
    if (!this.shouldReconnect) return;
    setTimeout(() => this._connect(), this.reconnectDelay);
    this.reconnectDelay = Math.min(
      this.reconnectDelay * 1.5,
      MAX_RECONNECT_DELAY
    );
  }
}

export const kalsimWS = new KalsimWS();
