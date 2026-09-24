/** Offline evidence queue — capture locally when offline, sync on reconnect.
 *  Each entry carries a unique client_ref so server retries are idempotent. */
import { uploadEvidence } from "./api";

export interface QueuedEvidence {
  client_ref: string;
  inspection_id: number;
  kind: "photo" | "video";
  captured_at: string;
  lat?: number | null;
  lng?: number | null;
  bytesB64: string; // demo scope: small photos only
  createdAt: number;
}

const QUEUE_KEY = "ow_offline_queue";

export function uid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `ref-${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

export function loadQueue(): QueuedEvidence[] {
  try {
    const raw = localStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as QueuedEvidence[]) : [];
  } catch {
    return [];
  }
}

async function fileToB64(file: File): Promise<string> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("read failed"));
    reader.readAsDataURL(file);
  });
  return dataUrl.split(",")[1] ?? "";
}

export async function enqueueItem(
  kind: "photo" | "video",
  file: File,
  inspectionId: number,
  extra?: { lat?: number | null; lng?: number | null },
): Promise<QueuedEvidence> {
  const bytesB64 = await fileToB64(file);
  const entry: QueuedEvidence = {
    client_ref: uid(),
    inspection_id: inspectionId,
    kind,
    captured_at: new Date().toISOString(),
    lat: extra?.lat ?? null,
    lng: extra?.lng ?? null,
    bytesB64,
    createdAt: Date.now(),
  };
  const queue = loadQueue();
  queue.push(entry);
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  return entry;
}

export function dropEntry(clientRef: string): void {
  localStorage.setItem(
    QUEUE_KEY,
    JSON.stringify(loadQueue().filter((q) => q.client_ref !== clientRef)),
  );
}

export async function syncQueue(inspectionId?: number): Promise<{ ok: number; failed: number }> {
  const pending = inspectionId
    ? loadQueue().filter((q) => q.inspection_id === inspectionId)
    : loadQueue();
  let ok = 0;
  let failed = 0;
  for (const entry of pending) {
    try {
      const binary = atob(entry.bytesB64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const file = new File([bytes], `offline-${entry.client_ref}.jpg`, { type: "image/jpeg" });
      const form = new FormData();
      form.append("file", file);
      form.append("kind", "photo");
      form.append("source", "offline_synced");
      form.append("captured_at", entry.captured_at);
      if (entry.lat != null) form.append("lat", String(entry.lat));
      if (entry.lng != null) form.append("lng", String(entry.lng));
      form.append("client_ref", entry.client_ref);
      const resp = await uploadEvidence(entry.inspection_id, form);
      if (resp.ok) {
        dropEntry(entry.client_ref);
        ok += 1;
      } else {
        failed += 1;
      }
    } catch {
      failed += 1;
    }
  }
  return { ok, failed };
}
