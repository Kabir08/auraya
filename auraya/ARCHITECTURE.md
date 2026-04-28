# Auraya — AR Jewelry Try-On App
### "Wear it before you buy it."

---

## App Identity

| Field        | Value |
|:-------------|:------|
| **Name**     | Auraya |
| **Tagline**  | Wear it before you buy it |
| **Platform** | Android (Phase 1), iOS (Phase 2) |
| **Stack**    | React Native + Python FastAPI |
| **Core Tech**| SAM · Meshy.ai · MediaPipe · ARCore |

> **Etymology:** *Aura* (glow/presence) + *-ya* (jewel suffix in Sanskrit). Sounds like a luxury jewelry brand and signals AR in the name.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AURAYA SYSTEM                            │
│                                                                 │
│  ┌──────────────┐    REST/WS    ┌──────────────────────────┐   │
│  │   React      │◄────────────►│   FastAPI Backend         │   │
│  │   Native     │              │                           │   │
│  │   App        │              │  ┌─────────┐ ┌─────────┐ │   │
│  │              │              │  │   SAM   │ │ Meshy   │ │   │
│  │  [Camera]    │  image/blob  │  │  Seg.   │ │  3D API │ │   │
│  │  [Gallery]   │─────────────►│  └────┬────┘ └────┬────┘ │   │
│  │  [AR View]   │              │       │            │      │   │
│  │  [Try-On]    │◄─────────────│  ┌────▼────────────▼────┐ │   │
│  └──────────────┘   .glb file  │  │  Asset Pipeline      │ │   │
│                                │  └──────────────────────┘ │   │
│                                └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Four-Stage Pipeline (The Core Logic)

### Stage A — Segmentation & Extraction
- Input: raw photo (camera snap or gallery upload)
- Model: **Segment Anything Model (SAM)** or **RMBG-1.4** (fallback)
- Output: transparent PNG with only the jewelry isolated
- Guard: a lightweight **jewelry classifier** (MobileNetV3) rejects non-jewelry images before burning SAM compute

### Stage B — 3D Reconstruction
- Input: transparent PNG from Stage A
- Model: **Meshy.ai Text-to-3D / Image-to-3D API** (primary) or **TripoSR** (self-hosted fallback)
- Output: `.glb` file (cross-platform) + `.usdz` (iOS Phase 2)
- Math: `3D_Object = G(I_2D)` where G is the generative mesh model

### Stage C — Anatomical Tracking
- Framework: **MediaPipe Holistic** (runs on-device, no server round-trip)
- Anchor points: midpoint of landmarks **#11 (Left Shoulder)** and **#12 (Right Shoulder)** → "Neck Base"
- Depth estimation: shoulder width in pixels → scale factor for the 3D model
- Platform: **ARCore** for depth API and motion tracking on Android

### Stage D — AR Overlay & Rendering
- Engine: **ViroReact** (wraps ARCore/ARKit) or **react-three-fiber + expo-gl**
- Asset format: `.glb` loaded via `ViroNode` anchored to neck coordinates
- Z-buffering: enabled by default in ViroReact for occlusion (chin over necklace)
- Physics (Phase 2): **Cannon.js** applied to the 3D mesh for necklace swing

---

## High-Level Data Flow

```
User Action
    │
    ▼
[Camera / Gallery]
    │
    │  raw image (JPEG/PNG)
    ▼
[Upload to Backend]  ──── validation (size < 10MB, format check)
    │
    ▼
[Stage A: SAM Segmentation]
    │
    │  transparent PNG
    ▼
[Jewelry Classifier]  ──── reject if not jewelry → return error
    │
    ▼
[Stage B: Meshy.ai 3D Gen]  ──── async job, WebSocket progress updates
    │
    │  .glb file URL
    ▼
[Frontend: Download .glb]
    │
    ▼
[Stage C: MediaPipe Tracking]  ──── runs on-device, 30fps
    │
    │  (x, y, z) neck anchor + scale
    ▼
[Stage D: ViroReact AR Render]
    │
    ▼
[User sees jewelry on themselves in real-time]
```

---

## Security & Privacy

| Concern | Mitigation |
|:--------|:-----------|
| Image data privacy | Images processed in-memory; never stored permanently unless user opts in |
| API key exposure | All third-party keys (Meshy, SAM) stay server-side only |
| Input validation | File size cap 10MB, MIME type whitelist (jpg/png/webp), virus scan stub |
| Rate limiting | FastAPI `slowapi` middleware: 10 requests/min per IP |
| HTTPS only | All API traffic over TLS; certificate pinning in React Native |

---

## Folder Structure (Monorepo)

```
auraya/
├── ARCHITECTURE.md         ← this file
├── docs/
│   ├── PIPELINE.md         ← CV/AR pipeline detail
│   ├── BACKEND.md          ← FastAPI service spec
│   ├── FRONTEND.md         ← React Native app spec
│   └── ROADMAP.md          ← Phased development plan
├── backend/                ← Python FastAPI service (to be built)
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── segmentation.py
│   │   │   └── mesh.py
│   │   ├── services/
│   │   │   ├── sam_service.py
│   │   │   ├── meshy_service.py
│   │   │   └── classifier_service.py
│   │   └── models/
│   └── requirements.txt
└── frontend/               ← React Native app (to be built)
    ├── src/
    │   ├── screens/
    │   │   ├── HomeScreen.tsx
    │   │   ├── CameraScreen.tsx
    │   │   ├── ProcessingScreen.tsx
    │   │   └── ARScreen.tsx
    │   ├── components/
    │   │   ├── ARViewer.tsx
    │   │   ├── JewelryCard.tsx
    │   │   └── UploadButton.tsx
    │   ├── services/
    │   │   ├── api.ts
    │   │   └── mediapipe.ts
    │   └── store/
    │       └── useARStore.ts
    └── package.json
```
