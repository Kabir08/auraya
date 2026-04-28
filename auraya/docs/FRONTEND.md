# Auraya — React Native Frontend Specification

---

## Overview

The frontend is a **React Native (TypeScript)** app that handles:
1. Camera capture and gallery upload
2. Sending images to the backend
3. Showing real-time processing progress (WebSocket)
4. Downloading and caching `.glb` assets
5. Running MediaPipe on-device for pose tracking
6. Rendering the 3D jewelry model in AR via ViroReact

---

## Tech Stack

| Component | Library | Notes |
|:----------|:--------|:------|
| Framework | React Native 0.74+ (TypeScript) | New Architecture (Fabric) enabled |
| Navigation | React Navigation v7 | Stack + Bottom Tabs |
| Camera | `react-native-vision-camera` v4 | Frame processors for MediaPipe |
| Gallery | `react-native-image-picker` | Photo/video library access |
| AR Rendering | `@viro-community/react-viro` | ARCore wrapper |
| Pose Tracking | `react-native-mediapipe` | On-device, GPU-accelerated |
| State | `zustand` | Lightweight, no boilerplate |
| API client | `axios` + `socket.io-client` | REST + WebSocket |
| Caching | `react-native-fs` | Local `.glb` asset cache |
| UI Components | `react-native-paper` | Material Design 3 |
| Animations | `react-native-reanimated` v3 | Loading states, transitions |

---

## Screen Map

```
App
├── SplashScreen           → brand logo, init check
├── HomeScreen             → mode selector (Camera / Gallery / Store Browse)
├── CameraScreen           → live camera with capture button
├── GalleryScreen          → system photo picker
├── ProcessingScreen       → upload progress + 3D gen progress (WebSocket)
├── ARScreen               → full-screen AR try-on view
└── SavedScreen            → saved try-on snapshots
```

---

## Screen Specifications

### HomeScreen
```
┌──────────────────────────┐
│  ✨ Auraya               │
│  "Wear it before you buy"│
│                          │
│  [📷 Use Camera]         │
│  [🖼 Upload from Gallery]│
│  [🛍 Browse Store Items] │  ← Phase 2 (partner jewelry catalog)
│                          │
│  [Recent Try-Ons ▼]      │
└──────────────────────────┘
```

### CameraScreen
- Full-screen camera preview via `VisionCamera`
- Bottom: large circular capture button
- Top-left: flash toggle, flip camera
- Instruction overlay: "Point at jewelry item and tap"
- Min recommended resolution: 1080×1080

### ProcessingScreen
```
┌──────────────────────────┐
│  Processing your jewelry │
│                          │
│  ✓ Image uploaded        │
│  ✓ Jewelry detected      │  ← classifier result shown
│  ↻ Generating 3D model   │  ← WebSocket live progress
│    [████████░░░] 75%     │
│                          │
│  Estimated: ~8 seconds   │
└──────────────────────────┘
```

### ARScreen
- Full-screen camera via ViroReact `ViroARSceneNavigator`
- Overlay UI (top): jewelry name + confidence badge
- Bottom toolbar: `[📸 Capture]` `[↔ Scale]` `[🔄 Rotate]` `[💾 Save]`
- Edge case overlays:
  - "Move closer" / "Move back" (shoulder distance check)
  - "Better lighting needed"
  - "Point camera at yourself"

---

## State Management (Zustand)

```typescript
// store/useARStore.ts
interface AurayanStore {
  // Processing state
  uploadedImageUri: string | null;
  segmentedPngUrl: string | null;
  glbFileUri: string | null;
  processingStatus: 'idle' | 'uploading' | 'segmenting' | 'generating' | 'ready' | 'error';
  processingProgress: number;   // 0-100

  // AR state
  neckAnchor: { x: number; y: number; z: number } | null;
  scaleFactor: number;
  rotationY: number;
  physicsEnabled: boolean;

  // Actions
  setImage: (uri: string) => void;
  setGlbUri: (uri: string) => void;
  setNeckAnchor: (coords: Coords) => void;
  resetSession: () => void;
}
```

---

## MediaPipe Integration

```typescript
// services/mediapipe.ts
import { PoseLandmarker } from 'react-native-mediapipe';

export function computeNeckAnchor(landmarks: PoseLandmark[]): Coords3D {
  const leftShoulder  = landmarks[11];   // MediaPipe index
  const rightShoulder = landmarks[12];

  const midX = (leftShoulder.x + rightShoulder.x) / 2;
  const midY = (leftShoulder.y + rightShoulder.y) / 2;
  const midZ = (leftShoulder.z + rightShoulder.z) / 2;

  const shoulderHeight = Math.abs(leftShoulder.y - rightShoulder.y);
  const neckOffset     = shoulderHeight * 0.20;  // shift upward

  return { x: midX, y: midY - neckOffset, z: midZ };
}

export function computeScaleFactor(landmarks: PoseLandmark[]): number {
  const shoulderWidthPx = euclidean2D(landmarks[11], landmarks[12]);
  const REFERENCE_PX    = 250;  // calibrated for average adult at ~60cm
  return shoulderWidthPx / REFERENCE_PX;
}
```

---

## API Service Layer

```typescript
// services/api.ts
const BASE_URL = process.env.BACKEND_URL ?? 'http://10.0.2.2:8000';  // Android emulator localhost

export const AurayaAPI = {
  async segmentImage(imageUri: string): Promise<SegmentResponse> {
    const form = new FormData();
    form.append('file', { uri: imageUri, type: 'image/jpeg', name: 'jewelry.jpg' });
    const res = await axios.post(`${BASE_URL}/api/v1/segment`, form, {
      headers: { 'Content-Type': 'multipart/form-data', 'X-Auraya-Key': API_KEY },
      timeout: 30000,
    });
    return res.data;
  },

  async generate3D(pngUrl: string, jewelryType: string): Promise<MeshResponse> {
    const res = await axios.post(`${BASE_URL}/api/v1/generate-3d`, {
      png_url: pngUrl, jewelry_type: jewelryType, quality: 'medium',
    });
    return res.data;
  },

  connectProgressSocket(taskId: string, onProgress: (p: ProgressEvent) => void) {
    const ws = new WebSocket(`${BASE_URL.replace('http', 'ws')}/ws/${taskId}`);
    ws.onmessage = (e) => onProgress(JSON.parse(e.data));
    return ws;
  },
};
```

---

## Android Permissions (AndroidManifest.xml)

```xml
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
<uses-permission android:name="android.permission.INTERNET" />

<!-- ARCore -->
<uses-feature android:name="android.hardware.camera.ar" android:required="true" />
<meta-data android:name="com.google.ar.core" android:value="required" />
```

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
