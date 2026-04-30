# Auraya — Web Frontend Specification (HF Spaces)

---

## Overview

The frontend is a **static HTML + Vanilla JS** single-page app served directly by FastAPI.  
No build step, no Node.js — just files FastAPI mounts as `StaticFiles` at `/`.

The user can:
1. Upload a jewelry photo from disk, **or** take a snapshot from their laptop webcam
2. Watch live progress while the backend segments + generates the 3D model
3. See the `.glb` model overlaid on their live webcam feed via Three.js + MediaPipe

---

## Tech Stack

| Component | Library / Approach | Notes |
|:----------|:------------------|:------|
| Layout | Plain HTML5 + CSS | No framework needed |
| Webcam access | `navigator.mediaDevices.getUserMedia` | Standard WebRTC |
| Pose tracking | MediaPipe Pose JS SDK (CDN) | In-browser WASM, no server call |
| 3D rendering | Three.js (CDN) + `GLTFLoader` | `.glb` overlay on video canvas |
| AR compositing | HTML5 Canvas 2D API | Draw video frame then Three.js render |
| API calls | `fetch()` (native) | No axios needed |
| WebSocket | Native `WebSocket` API | Progress updates from backend |
| State | Plain JS module (no Zustand) | Simple enough without a framework |

---

## Page Layout

```
┌──────────────────────────────────────────────────────────┐
│  ✨ Auraya  —  "Wear it before you buy it"               │
├───────────────────────────┬──────────────────────────────┤
│  STEP 1: Jewelry Photo    │  STEP 2: Try It On           │
│                           │                              │
│  [📁 Upload Image]        │  [▶ Start Webcam]            │
│  [📷 Use Webcam Snapshot] │                              │
│                           │  ┌────────────────────────┐ │
│  Preview:                 │  │  <video> + canvas AR   │ │
│  [img preview]            │  │   overlay (Three.js)   │ │
│                           │  └────────────────────────┘ │
│  [▶ Process Jewelry]      │                              │
│                           │  [📸 Save Screenshot]        │
├───────────────────────────┴──────────────────────────────┤
│  Progress:  [████████░░░░] 75%  ↻ Generating 3D model…  │
└──────────────────────────────────────────────────────────┘
```

---

## File Structure

```
frontend/
├── index.html          ← single page, all UI
├── js/
│   ├── main.js         ← wires everything together, handles UI state
│   ├── camera.js       ← getUserMedia, snapshot capture
│   ├── mediapipe.js    ← loads MediaPipe Pose, exposes computeNeckAnchor()
│   ├── ar_renderer.js  ← Three.js scene, GLTFLoader, per-frame compositing
│   └── api.js          ← fetch() wrappers for /api/v1/segment, /generate-3d, /ws
└── css/
    └── style.css
```

---

## Camera Module (`js/camera.js`)

```javascript
// camera.js
let stream = null;

export async function startWebcam(videoEl) {
  stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  videoEl.srcObject = stream;
  await videoEl.play();
}

export function stopWebcam() {
  stream?.getTracks().forEach(t => t.stop());
  stream = null;
}

/** Capture current video frame as a JPEG Blob */
export function captureSnapshot(videoEl) {
  const canvas = document.createElement('canvas');
  canvas.width  = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;
  canvas.getContext('2d').drawImage(videoEl, 0, 0);
  return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.9));
}
```

---

## MediaPipe Module (`js/mediapipe.js`)

```javascript
// mediapipe.js — loads MediaPipe Pose via CDN
// CDN: https://cdn.jsdelivr.net/npm/@mediapipe/pose

let poseLandmarker = null;

export async function initMediaPipe() {
  const { PoseLandmarker, FilesetResolver } = await import(
    'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/vision_bundle.js'
  );
  const vision = await FilesetResolver.forVisionTasks(
    'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm'
  );
  poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task' },
    runningMode: 'VIDEO',
    numPoses: 1,
  });
}

/** Returns { x, y } in 0–1 normalised coords, or null if no person detected */
export function computeNeckAnchor(videoEl, timestampMs) {
  if (!poseLandmarker) return null;
  const result = poseLandmarker.detectForVideo(videoEl, timestampMs);
  if (!result.landmarks?.length) return null;

  const lm = result.landmarks[0];
  const ls = lm[11];  // Left Shoulder
  const rs = lm[12];  // Right Shoulder

  const midX = (ls.x + rs.x) / 2;
  const midY = (ls.y + rs.y) / 2;
  const shoulderSpanY = Math.abs(ls.y - rs.y);
  return {
    x: midX,
    y: midY - shoulderSpanY * 0.20,   // offset upward to neck base
    shoulderWidthNorm: Math.abs(ls.x - rs.x),
  };
}
```

---

## AR Renderer (`js/ar_renderer.js`)

```javascript
// ar_renderer.js — Three.js overlay on webcam canvas
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.165/build/three.module.js';
import { GLTFLoader } from 'https://cdn.jsdelivr.net/npm/three@0.165/examples/jsm/loaders/GLTFLoader.js';

let renderer, scene, camera, model;

export function initRenderer(canvas) {
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true });
  renderer.setSize(canvas.width, canvas.height);
  renderer.setClearColor(0x000000, 0);  // transparent background

  scene  = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(45, canvas.width / canvas.height, 0.01, 100);
  camera.position.z = 1;

  scene.add(new THREE.AmbientLight(0xffffff, 1.2));
}

export async function loadModel(glbUrl) {
  if (model) scene.remove(model);
  const gltf = await new GLTFLoader().loadAsync(glbUrl);
  model = gltf.scene;
  scene.add(model);
}

/**
 * Called each animation frame.
 * anchor: { x, y, shoulderWidthNorm } in 0–1 coords from MediaPipe
 */
export function renderFrame(videoEl, canvas, anchor) {
  // Draw webcam frame underneath
  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

  if (model && anchor) {
    // Map normalised coords to Three.js NDC (-1 to 1)
    model.position.x = (anchor.x - 0.5) * 2;
    model.position.y = -(anchor.y - 0.5) * 2;

    const scaleFactor = anchor.shoulderWidthNorm / 0.35;  // 0.35 ≈ avg normalised shoulder width
    model.scale.setScalar(scaleFactor * 0.25);
  }

  renderer.render(scene, camera);
}
```

---

## API Module (`js/api.js`)

```javascript
// api.js
const BASE = '';  // same origin — FastAPI serves frontend and API

export async function segmentJewelry(imageBlob) {
  const form = new FormData();
  form.append('file', imageBlob, 'jewelry.jpg');
  const res = await fetch('/api/v1/segment', { method: 'POST', body: form });
  if (!res.ok) throw await res.json();
  return res.json();   // { task_id, png_url, jewelry_type }
}

export async function generate3D(pngUrl, jewelryType) {
  const res = await fetch('/api/v1/generate-3d', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ png_url: pngUrl, jewelry_type: jewelryType, quality: 'medium' }),
  });
  if (!res.ok) throw await res.json();
  return res.json();   // { task_id }
}

export function connectProgress(taskId, onProgress) {
  const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${wsProto}://${location.host}/ws/${taskId}`);
  ws.onmessage = e => onProgress(JSON.parse(e.data));
  return ws;
}
```

---

## State Flow

```
idle
  │  user picks file OR takes webcam snapshot
  ▼
uploading    → POST /api/v1/segment
  │
  ▼
segmenting   → response with png_url
  │
  ▼
generating   → POST /api/v1/generate-3d → WebSocket progress 0→100%
  │
  ▼
ready        → loadModel(glb_url) → start renderFrame() loop
  │
  ▼
[AR view active — MediaPipe tracking + Three.js overlay running at ~30fps]
```

---

## Android (Future — Phase 3)

> Do not build the Android app until the HF Spaces web version is working end-to-end.
> When ready: React Native app pointing at the same FastAPI backend. Use BrowserStack for device testing across Android versions.


**Runtime permission requests:** camera + media library on first launch with clear explanation dialog.

---

## Performance Targets (Android Mid-Range Device)

| Feature | Target |
|:--------|:-------|
| App cold start | < 3 seconds |
| Camera → upload | < 2 seconds |
| Segmentation (server) | < 4 seconds |
| 3D generation (Meshy.ai) | 15–30 seconds |
| AR first render | < 1.5 seconds after .glb download |
| AR frame rate | ≥ 30 FPS (targeting 60) |
| `.glb` cache hit load | < 500ms |

---

## Minimum Device Requirements

| Requirement | Minimum |
|:------------|:--------|
| Android version | 9.0 (API 28) |
| ARCore support | Required |
| RAM | 3GB |
| GPU | Adreno 505 / Mali-G52 or equivalent |
| Camera | 8MP, autofocus |
