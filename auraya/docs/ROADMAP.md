# Auraya — Development Roadmap

> **Deployment target:** Hugging Face Spaces (Docker). Validate the full loop in browser before building the Android app.
> **Scope:** Jewelry only for now (necklace, ring, bracelet, earring). Generic object AR requires physics + object-type-aware placement — deferred.

---

## Phase 1 — HF Spaces Web App: Core Loop (Weeks 1–3)
**Goal:** Working end-to-end in a browser. User uploads a jewelry photo → 3D model → AR overlay on webcam.

### Backend (FastAPI — Docker on HF Spaces)
- [ ] FastAPI scaffold with health check endpoint
- [ ] `Dockerfile` for HF Spaces (CPU-only, port 7860)
- [ ] Image upload endpoint with validation (size, MIME, blur)
- [ ] `rembg` (RMBG-1.4) integration for background removal — no GPU needed
- [ ] Jewelry classifier guard (MobileNetV3 — rejects non-jewelry before heavy compute)
- [ ] Meshy.ai Image-to-3D API integration (`/api/v1/generate-3d`)
- [ ] WebSocket progress endpoint (`/ws/{task_id}`)
- [ ] Static file serving for the HTML/JS frontend (`/` → `frontend/index.html`)
- [ ] Asset TTL cleanup (in-memory or tmp dir, 1h)

### Frontend (HTML + Vanilla JS — no build step)
- [ ] `index.html` single-page layout: Upload panel + Webcam panel + AR viewer
- [ ] File upload (`<input type="file">`) → POST to `/api/v1/segment`
- [ ] Webcam capture via `getUserMedia` → snapshot → POST to `/api/v1/segment`
- [ ] Processing state: WebSocket-driven live progress bar
- [ ] Three.js `GLTFLoader` — load returned `.glb` and render in a canvas overlay
- [ ] MediaPipe Pose (JS SDK via CDN) — detect shoulder landmarks from webcam feed
- [ ] `computeNeckAnchor()` — midpoint of landmarks #11 and #12
- [ ] Canvas compositor — blend Three.js render on top of `<video>` element each frame
- [ ] Manual scale / rotate sliders as fallback when MediaPipe can't find landmarks

### Milestone
> User opens the HF Space URL in a laptop browser, uploads a necklace photo, sees the 3D model overlaid on their webcam feed. No install required.

---

## Phase 2 — Quality & UX Polish (Weeks 4–5)
**Goal:** Smooth experience, better tracking, shareable results.

- [ ] SAM 2 integration for segmentation (replaces rembg as primary, better masks)
- [ ] TripoSR self-hosted fallback (if HF Spaces GPU tier is available)
- [ ] Draco-compressed `.glb` via `gltfpack` (faster download)
- [ ] "Move closer / farther" proximity guide (shoulder-width heuristic)
- [ ] Lighting estimation — adjust Three.js ambient light to match webcam brightness
- [ ] Save try-on screenshot (canvas `toBlob` → download)
- [ ] Jewelry type badge on result (necklace / ring / bracelet / earring)
- [ ] Mobile browser support — test on Chrome Android / Safari iOS (camera via same `getUserMedia`)

### Milestone
> The HF Space works reliably. Users can screenshot their try-on and share the link.

---

## Phase 3 — Android App (After Phase 2 is validated)
**Goal:** Native Android app that reuses the same FastAPI backend.

> **Start this phase only once the HF Spaces web version is working end-to-end.**

- [ ] React Native project init (TypeScript, New Architecture)
- [ ] Same FastAPI backend (no changes needed — just point the app at the HF Spaces URL or a separate deployment)
- [ ] Camera via `react-native-vision-camera`
- [ ] MediaPipe Pose on-device (native, faster than JS)
- [ ] Three.js / ViroReact for AR rendering
- [ ] Device testing via BrowserStack
- [ ] Play Store alpha release

---

## Future / Deferred
- **Generic object AR** (not just jewelry): Needs object-type classification to know *where* to place the model (neck vs. wrist vs. finger vs. table), plus physics for realistic drape/swing. Deferred until jewelry loop is solid.
- **Physics simulation**: Necklace swing via Cannon-es — deferred to after Phase 2.
- **iOS app**: After Android is stable.
- **Automation / CI testing**: Deferred — not needed for HF Spaces launch.
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
