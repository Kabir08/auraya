# Auraya — AR Jewelry Try-On App
### "Wear it before you buy it."

---

## App Identity

| Field        | Value |
|:-------------|:------|
| **Name**     | Auraya |
| **Tagline**  | Wear it before you buy it |
| **Platform** | Web — Hugging Face Spaces (Phase 1), Android (Phase 2) |
| **Stack**    | HTML/JS + Three.js + Python FastAPI (Docker on HF Spaces) |
| **Core Tech**| SAM · Meshy.ai · MediaPipe.js · Three.js · WebRTC |
| **Scope**    | Jewelry only (necklace, ring, bracelet, earring) |

> **Etymology:** *Aura* (glow/presence) + *-ya* (jewel suffix in Sanskrit). Sounds like a luxury jewelry brand and signals AR in the name.

> **Current deployment target:** Hugging Face Spaces (Docker). The web interface lets users either upload a jewelry image or use their laptop webcam. Android is planned for after the web version is validated.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          AURAYA SYSTEM                               │
│                    (Hugging Face Spaces — Docker)                    │
│                                                                      │
│  ┌───────────────────────┐   REST/WS   ┌──────────────────────────┐ │
│  │  Web Browser (Laptop) │◄───────────►│  FastAPI Backend         │ │
│  │                       │             │                          │ │
│  │  [Webcam / Upload]    │  image/blob │  ┌─────────┐ ┌────────┐ │ │
│  │  [MediaPipe.js Pose]  │────────────►│  │   SAM   │ │ Meshy  │ │ │
│  │  [Three.js AR View]   │             │  │  Seg.   │ │  3D API│ │ │
│  │  [Canvas Compositor]  │◄────────────│  └────┬────┘ └────┬───┘ │ │
│  └───────────────────────┘  .glb file  │       │           │     │ │
│                                         │  ┌────▼───────────▼───┐ │ │
│                                         │  │   Asset Pipeline   │ │ │
│                                         │  └───────────────────┘ │ │
│                                         └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Four-Stage Pipeline (The Core Logic)

### Stage A — Segmentation & Extraction
- Input: raw photo (webcam capture or file upload from browser)
- Model: **Segment Anything Model (SAM)** or **RMBG-1.4** (fallback)
- Output: transparent PNG with only the jewelry isolated
- Guard: a lightweight **jewelry classifier** (MobileNetV3) rejects non-jewelry images before burning SAM compute

### Stage B — 3D Reconstruction
- Input: transparent PNG from Stage A
- Model: **Meshy.ai Image-to-3D API** (primary) or **TripoSR** (self-hosted fallback)
- Output: `.glb` file
- Math: `3D_Object = G(I_2D)` where G is the generative mesh model

### Stage C — Anatomical Tracking
- Framework: **MediaPipe Pose** (JS SDK, runs in-browser via WebAssembly — no server round-trip)
- Anchor points: midpoint of landmarks **#11 (Left Shoulder)** and **#12 (Right Shoulder)** → "Neck Base"
- Depth estimation: shoulder width in pixels → scale factor for the 3D model
- Input source: `getUserMedia` (WebRTC webcam stream)

### Stage D — AR Overlay & Rendering
- Engine: **Three.js** + WebGL canvas overlaid on the webcam `<video>` element
- Asset format: `.glb` loaded via `GLTFLoader` and anchored to neck coordinates from Stage C
- Compositing: Canvas 2D API composites the webcam frame + Three.js render each frame
- Physics (future): Add necklace swing via Cannon-es once core loop is solid

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
├── Dockerfile              ← HF Spaces Docker config
├── docs/
│   ├── PIPELINE.md         ← CV/AR pipeline detail
│   ├── BACKEND.md          ← FastAPI service spec
│   ├── FRONTEND.md         ← Web frontend spec
│   └── ROADMAP.md          ← Phased development plan
├── backend/                ← Python FastAPI service
│   ├── app/
│   │   ├── main.py         ← also serves static frontend files
│   │   ├── routers/
│   │   │   ├── segmentation.py
│   │   │   └── mesh.py
│   │   ├── services/
│   │   │   ├── sam_service.py
│   │   │   ├── meshy_service.py
│   │   │   └── classifier_service.py
│   │   └── models/
│   └── requirements.txt
└── frontend/               ← Static web app (HTML/JS, no build step needed)
    ├── index.html          ← Single-page app entry point
    ├── js/
    │   ├── main.js         ← App bootstrap
    │   ├── camera.js       ← WebRTC webcam + capture
    │   ├── mediapipe.js    ← MediaPipe Pose landmark detection
    │   ├── ar_renderer.js  ← Three.js .glb overlay on video canvas
    │   └── api.js          ← fetch() wrapper for FastAPI endpoints
    └── css/
        └── style.css
```

> **Android (Phase 2):** Once the web version is validated on HF Spaces, build a React Native app that reuses the same FastAPI backend. Use BrowserStack for device testing.
