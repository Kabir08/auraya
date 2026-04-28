# Auraya — Development Roadmap

---

## Phase 1 — Foundation (Weeks 1–3)
**Goal:** Backend pipeline working end-to-end, flat PNG overlay on AR (no 3D yet).

### Backend
- [ ] FastAPI scaffold with health check endpoint
- [ ] Image upload endpoint with validation (size, MIME, blur)
- [ ] Jewelry classifier (MobileNetV3, fine-tuned on jewelry dataset)
- [ ] `rembg` (RMBG-1.4) integration for background removal (CPU-only, no GPU needed)
- [ ] Basic asset serving endpoint

### Frontend
- [ ] React Native project init (TypeScript, New Architecture)
- [ ] Camera capture screen (`react-native-vision-camera`)
- [ ] Gallery upload screen (`react-native-image-picker`)
- [ ] API service layer (axios)
- [ ] Processing screen (simple progress indicator)
- [ ] Flat PNG try-on: overlay transparent jewelry PNG on live camera feed (no 3D)

### Milestone
> User can photograph a necklace, backend removes background, app overlays flat PNG on camera feed. Not 3D yet, but proves the core loop.

---

## Phase 2 — 3D Generation (Weeks 4–5)
**Goal:** Replace flat PNG overlay with a real 3D `.glb` model.

### Backend
- [ ] Meshy.ai API integration (`/api/v1/generate-3d`)
- [ ] Celery + Redis task queue for async 3D generation
- [ ] WebSocket progress endpoint (`/ws/{task_id}`)
- [ ] TripoSR self-hosted fallback (if GPU available)
- [ ] `gltfpack` Draco compression on generated `.glb`
- [ ] Asset TTL cleanup (cron job, 24h)

### Frontend
- [ ] Processing screen: WebSocket-driven live progress bar
- [ ] `.glb` download and local file cache (`react-native-fs`)
- [ ] ViroReact integration: load `.glb` in AR scene
- [ ] Basic placement: model at fixed center of screen

### Milestone
> User photographs jewelry → 3D model generated in ~20s → model renders in AR.

---

## Phase 3 — Smart Tracking (Weeks 6–7)
**Goal:** Model automatically anchors to the user's neck/chest.

### Frontend
- [ ] MediaPipe Holistic integration (`react-native-mediapipe`)
- [ ] `computeNeckAnchor()` and `computeScaleFactor()` functions
- [ ] ViroReact scene: anchor `Viro3DObject` to `neckAnchor` coordinates
- [ ] Dynamic scale: shoulder-width-based scaling
- [ ] Lighting estimation: ViroReact ambient + spot lights matching scene brightness
- [ ] ARCore Depth API: occlusion (chin-over-necklace handling)

### UX Polish
- [ ] "Move closer / farther" proximity guide
- [ ] "Better lighting" detection
- [ ] Scale ↕ and rotation ↔ manual adjustment sliders in AR view

### Milestone
> Model sticks to neck as user moves, turns head, and adjusts distance. Chin occludes necklace realistically.

---

## Phase 4 — UX & Features (Week 8)
**Goal:** App feels polished and is demo-ready for jewelry stores.

- [ ] Save try-on screenshot to gallery
- [ ] Share button (WhatsApp, Instagram)
- [ ] Try-on history (local SQLite via `react-native-sqlite-storage`)
- [ ] Dark/light mode
- [ ] Onboarding walkthrough (3 screens)
- [ ] Jewelry type badges on results (necklace / ring / bracelet / earring)
- [ ] Multiple items: try on up to 3 items simultaneously
- [ ] Store catalog mode: browse predefined jewelry SKUs (JSON catalog)

---

## Phase 5 — Physics & Realism (Week 9–10)
**Goal:** Necklace swings realistically with device motion.

- [ ] Cannon.js physics engine integrated with react-three-fiber
- [ ] Chain link rigid-body simulation with hinge joints
- [ ] `DeviceMotion` API feeds linear acceleration → Cannon.js
- [ ] LOD (Level of Detail) mesh switching at different distances
- [ ] PBR (Physically Based Rendering) materials on `.glb` assets

---

## Phase 6 — Platform & Scale (Post-MVP)
- [ ] iOS build (ARKit support, `.usdz` asset format)
- [ ] Partner API: jewelry store catalog ingestion (CSV/API)
- [ ] Cloud storage: AWS S3 for generated assets (replace local disk)
- [ ] CDN: CloudFront for global `.glb` serving
- [ ] Analytics: try-on events, conversion tracking
- [ ] Admin dashboard: store partners can upload their catalog

---

## Tech Risk Register

| Risk | Likelihood | Impact | Mitigation |
|:-----|:-----------|:-------|:-----------|
| Meshy.ai API rate limits | Medium | High | Celery queue + TripoSR fallback |
| MediaPipe false neck anchors | Medium | Medium | Confidence threshold gate + UX guide |
| ViroReact deprecated (no iOS 17+ support) | Low | High | Have react-three-fiber migration plan ready |
| `.glb` file too large (>5MB) | Low | Medium | Mandatory Draco compression in pipeline |
| ARCore not supported on user device | Medium | High | Graceful fallback to flat PNG try-on mode |
| Jewelry classifier misclassification | Low | Low | Classifier confidence shown to user + manual override |

---

## Agent Task Breakdown (for Auraya's own multi-agent system)

When using the Auraya agent workspace to build Auraya itself:

| Iteration | Agent | Task |
|:----------|:------|:-----|
| 1 | Researcher | Research best React Native AR libraries (ViroReact vs. react-three-fiber) |
| 2 | Coder | Scaffold FastAPI backend with image upload + rembg segmentation |
| 3 | Reviewer | Review backend code for security (OWASP: input validation, rate limiting) |
| 4 | Coder | Implement Meshy.ai API client + Celery task + WebSocket |
| 5 | Coder | Scaffold React Native app with Camera + Gallery screens |
| 6 | Coder | Implement MediaPipe tracking + ViroReact AR scene |
| 7 | Reviewer | Full integration review |
| 8 | Critic | Architecture critique: performance, security, scalability |
| 9 | Summarizer | Final build summary + deployment checklist |
