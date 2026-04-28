/**
 * Global Zustand store for Auraya.
 *
 * Tracks the full pipeline state from image capture through AR rendering.
 */
import { create } from 'zustand';
import type { Coords3D } from '../services/mediapipe';

export type ProcessingStatus =
  | 'idle'
  | 'uploading'
  | 'segmenting'
  | 'generating'
  | 'ready'
  | 'error';

interface AurayaState {
  // ── Pipeline ───────────────────────────────────────────────────────────────
  rawImageUri:          string | null;
  segmentedPngUrl:      string | null;
  glbUri:               string | null;
  meshTaskId:           string | null;
  processingStatus:     ProcessingStatus;
  processingProgress:   number;           // 0-100
  processingError:      string | null;
  jewelryType:          string;

  // ── AR tracking ────────────────────────────────────────────────────────────
  neckAnchor:           Coords3D | null;
  scaleFactor:          number;
  rotationY:            number;           // manual rotation offset (degrees)
  poseReliable:         boolean;

  // ── Actions ────────────────────────────────────────────────────────────────
  setRawImage:          (uri: string) => void;
  setSegmentedPng:      (url: string, jewelryType?: string) => void;
  setMeshTask:          (taskId: string) => void;
  setProgress:          (percent: number) => void;
  setGlbUri:            (uri: string) => void;
  setStatus:            (status: ProcessingStatus) => void;
  setError:             (msg: string) => void;
  setNeckAnchor:        (anchor: Coords3D, scale: number, reliable: boolean) => void;
  setRotationY:         (deg: number) => void;
  resetSession:         () => void;
}

const INITIAL: Omit<AurayaState, keyof {
  setRawImage: unknown; setSegmentedPng: unknown; setMeshTask: unknown;
  setProgress: unknown; setGlbUri: unknown; setStatus: unknown;
  setError: unknown; setNeckAnchor: unknown; setRotationY: unknown;
  resetSession: unknown;
}> = {
  rawImageUri:        null,
  segmentedPngUrl:    null,
  glbUri:             null,
  meshTaskId:         null,
  processingStatus:   'idle',
  processingProgress: 0,
  processingError:    null,
  jewelryType:        'necklace',
  neckAnchor:         null,
  scaleFactor:        1.0,
  rotationY:          0,
  poseReliable:       false,
};

export const useARStore = create<AurayaState>((set) => ({
  ...INITIAL,

  setRawImage:     (uri)  => set({ rawImageUri: uri, processingStatus: 'uploading', processingError: null }),
  setSegmentedPng: (url, jewelryType = 'necklace') =>
    set({ segmentedPngUrl: url, jewelryType, processingStatus: 'generating' }),
  setMeshTask:     (taskId) => set({ meshTaskId: taskId }),
  setProgress:     (percent) => set({ processingProgress: percent }),
  setGlbUri:       (uri)  => set({ glbUri: uri, processingStatus: 'ready', processingProgress: 100 }),
  setStatus:       (status) => set({ processingStatus: status }),
  setError:        (msg)  => set({ processingStatus: 'error', processingError: msg }),

  setNeckAnchor: (anchor, scale, reliable) =>
    set({ neckAnchor: anchor, scaleFactor: scale, poseReliable: reliable }),

  setRotationY: (deg) => set({ rotationY: deg }),

  resetSession: () => set({ ...INITIAL }),
}));
