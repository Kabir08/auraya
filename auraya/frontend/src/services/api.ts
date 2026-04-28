/**
 * Auraya API service layer.
 *
 * All network calls go through this module.
 * Backend URL is read from EXPO_PUBLIC_BACKEND_URL (set in .env).
 */
import axios, { AxiosInstance } from 'axios';

const BASE_URL =
  process.env.EXPO_PUBLIC_BACKEND_URL ?? 'http://10.0.2.2:8000';
const API_KEY  =
  process.env.EXPO_PUBLIC_AURAYA_API_KEY ?? '';

export interface SegmentResponse {
  png_url:               string;
  png_b64:               string;
  model_used:            string;
  jewelry_type:          string;
  classifier_confidence: number;
}

export interface Generate3DResponse {
  task_id:           string;
  status:            string;
  estimated_seconds: number;
  ws_channel:        string;
}

export interface MeshStatusResponse {
  task_id:  string;
  status:   string;
  progress: number;
  glb_url:  string | null;
  error:    string | null;
}

export type ProgressEvent =
  | { type: 'progress';  percent: number; message: string }
  | { type: 'completed'; glb_url: string }
  | { type: 'error';     code: string;    message: string };

// ─── Axios instance ────────────────────────────────────────────────────────────
const client: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 60_000,
  headers: { 'X-Auraya-Key': API_KEY },
});

// ─── Public API ────────────────────────────────────────────────────────────────

/**
 * Upload a jewelry photo for background removal.
 * `imageUri` is a local file:// URI from camera/gallery.
 */
export async function segmentImage(
  imageUri: string,
  useSam = false,
): Promise<SegmentResponse> {
  const formData = new FormData();
  formData.append('file', {
    uri:  imageUri,
    type: 'image/jpeg',
    name: 'jewelry.jpg',
  } as unknown as Blob);

  const { data } = await client.post<SegmentResponse>(
    `/segment?use_sam=${useSam}`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return data;
}

/**
 * Kick off 3D mesh generation.
 * Returns a task_id immediately; use connectProgressSocket for live progress.
 */
export async function generate3D(
  pngUrl:      string,
  jewelryType: string = 'necklace',
): Promise<Generate3DResponse> {
  const { data } = await client.post<Generate3DResponse>('/generate-3d', {
    png_url:      pngUrl,
    jewelry_type: jewelryType,
    quality:      'medium',
  });
  return data;
}

/**
 * Poll mesh status (use if WebSocket is unavailable).
 */
export async function getMeshStatus(taskId: string): Promise<MeshStatusResponse> {
  const { data } = await client.get<MeshStatusResponse>(`/mesh/${taskId}`);
  return data;
}

/**
 * Open a WebSocket that streams progress events for a Tripo AI task.
 * Returns the WebSocket instance so the caller can close it.
 */
export function connectProgressSocket(
  taskId:     string,
  onEvent:    (event: ProgressEvent) => void,
  onClose?:   () => void,
): WebSocket {
  const wsBase = BASE_URL.replace(/^http/, 'ws');
  const ws     = new WebSocket(`${wsBase}/ws/${taskId}`);

  ws.onmessage = (e) => {
    try {
      const event: ProgressEvent = JSON.parse(e.data);
      onEvent(event);
    } catch {
      // malformed frame — ignore
    }
  };

  ws.onclose = () => onClose?.();

  ws.onerror = (err) => {
    onEvent({ type: 'error', code: 'WS_ERROR', message: 'Connection error.' });
  };

  return ws;
}
