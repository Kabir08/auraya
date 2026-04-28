# Auraya — CV/AR Pipeline Deep Dive

---

## Stage A: Segmentation & Extraction

### Goal
Strip the background from the jewelry photo and output a clean transparent PNG.

### Primary Model — SAM (Segment Anything Model)
- **Variant:** SAM 2 (Meta, 2024) — faster than SAM 1, supports single-image mode
- **Mode:** Automatic mask generation with point prompt at image center, or bounding-box prompt derived from the jewelry classifier's output
- **Output:** Binary mask → applied to original image → RGBA PNG

### Fallback — RMBG-1.4 (BRIA AI)
- Lighter model, runs faster on CPU
- Used when SAM inference exceeds 3 seconds (circuit breaker triggers fallback)

### Jewelry Pre-Filter (Classifier Guard)
```
Input image
    │
    ▼
MobileNetV3 (fine-tuned on jewelry categories)
    │
    ├── Confidence ≥ 0.70  → PASS  → proceed to SAM
    └── Confidence < 0.70  → FAIL  → return 400 "Not recognized as jewelry"
```
**Categories:** necklace, ring, bracelet, earring, pendant, brooch

### Segmentation Pipeline (Server-side)
```python
# Pseudocode — full implementation in backend/services/sam_service.py
def segment_jewelry(image_bytes: bytes) -> bytes:
    image = load_image(image_bytes)          # PIL → numpy RGB
    label = classifier.predict(image)        # MobileNetV3
    if label.confidence < 0.70:
        raise JewelryNotDetectedError()
    
    masks = sam.generate(image)              # SAM automatic mode
    best_mask = select_largest_central(masks) # pick the dominant object
    rgba = apply_mask_to_image(image, best_mask)
    return encode_png(rgba)                  # transparent PNG bytes
```

### Edge Cases
| Scenario | Handling |
|:---------|:---------|
| Multiple jewelry items in frame | Select the mask with the largest area closest to center |
| Jewelry on a person (worn photo) | SAM point prompt at detected object centroid |
| Low contrast background | RMBG-1.4 fallback (better on light backgrounds) |
| Blurry image | Return `422 Unprocessable` with "Image too blurry" message |

---

## Stage B: 3D Reconstruction (Image → Mesh)

### Goal
Convert the transparent PNG into a photorealistic `.glb` 3D model.

### Primary — Meshy.ai Image-to-3D API
```
POST https://api.meshy.ai/v1/image-to-3d
{
  "image_url": "<presigned S3 URL>",
  "enable_pbr": true,
  "surface_mode": "hard"   // jewelry = hard surface
}
→ Returns task_id

GET https://api.meshy.ai/v1/image-to-3d/{task_id}
→ Polls until status = "SUCCEEDED"
→ Returns model_urls.glb
```

### Self-Hosted Fallback — TripoSR
- Runs on GPU server (A100/V100 or local RTX)
- ~5s inference for 512×512 input
- Output: `.obj` → converted to `.glb` via `trimesh`

### 3D Generation Flow
```
Transparent PNG
    │
    ▼
[Upload to temp S3 / local fileserver]  → get public URL (valid 10 min)
    │
    ▼
[POST Meshy.ai /image-to-3d]
    │
    ▼
[WebSocket: stream progress to frontend]  → 0% ... 50% ... 100%
    │
    ▼ (on SUCCEEDED)
[Download .glb from Meshy CDN]
    │
    ▼
[Serve .glb from Auraya CDN / local cache]
    │
    ▼
[Frontend downloads .glb]  → cached locally on device
```

### Asset Optimization (Before Serving)
- **Draco compression:** reduce `.glb` size by ~70% via `gltfpack`
- **LOD (Level of Detail):** generate 3 mesh resolutions (high/med/low) for distance-based rendering
- **Max file size target:** < 2MB per jewelry item

### Math: Scale Normalization
The 3D model must be normalized to a real-world reference size:
```
normalized_scale = REFERENCE_NECKLACE_LENGTH_CM / mesh_bounding_box_y
```
The AR renderer then applies an additional dynamic scale based on shoulder width:
```
shoulder_width_px = dist(landmark_11, landmark_12)
scale_factor = shoulder_width_px / REFERENCE_SHOULDER_PX
final_scale = normalized_scale × scale_factor
```

---

## Stage C: Anatomical Tracking

### Goal
Track the user's neck/chest area in real-time at ≥ 30fps on a mid-range Android device.

### Framework — MediaPipe Holistic (On-Device)
- Runs entirely on the device (no server round-trip for tracking)
- Uses device GPU via TensorFlow Lite delegate
- Provides 33 pose landmarks in 3D space (x, y, z, visibility)

### Key Landmarks Used

```
MediaPipe Pose Landmark Map (relevant subset):

        [0] Nose
          │
    [11]──┼──[12]   ← Left Shoulder / Right Shoulder
     Left │   Right
          │
    [23]──┼──[24]   ← Left Hip / Right Hip
```

| Landmark | Index | Use |
|:---------|:------|:----|
| Left Shoulder  | 11 | Anchor left bound |
| Right Shoulder | 12 | Anchor right bound |
| Neck Base      | computed | midpoint(11, 12) shifted up by 20% of shoulder height |

### Anchor Point Calculation
```typescript
// TypeScript / React Native side
const neckBase = {
  x: (landmark[11].x + landmark[12].x) / 2,
  y: (landmark[11].y + landmark[12].y) / 2 - shoulderHeight * 0.20,
  z: (landmark[11].z + landmark[12].z) / 2,
};
```

### ARCore Integration
- **Depth API:** Per-pixel depth map from dual cameras → enables realistic occlusion
- **Motion Tracking:** 6-DOF pose tracking → model stays anchored as user moves
- **Hit Testing:** Initial placement uses ARCore plane detection as ground truth

### Performance Targets
| Metric | Target |
|:-------|:-------|
| Landmark detection | ≥ 30 FPS |
| Model re-render latency | < 16ms (60fps frame budget) |
| Occlusion accuracy | ±2cm depth tolerance |
| Cold-start (first detection) | < 1.5 seconds |

---

## Stage D: AR Overlay & Rendering

### Goal
Render the `.glb` 3D model anchored at the neck base, correctly scaled and occluded.

### Rendering Stack Options (Ranked)

| Option | Library | Pros | Cons |
|:-------|:--------|:-----|:-----|
| **Primary** | ViroReact | ARCore/ARKit native bridge, GLB support, mature | Maintenance slowed |
| **Alternative** | react-three-fiber + expo-gl | Active community, full Three.js power | Manual ARCore integration |
| **Fallback** | React Native AR Kit (community) | Simpler API | Android support limited |

### ViroReact AR Scene Structure
```jsx
<ViroARScene onTrackingUpdated={onTracking}>
  <ViroAmbientLight color="#ffffff" intensity={200} />
  <ViroSpotLight
    innerAngle={5} outerAngle={25}
    direction={[0, -1, 0]}
    position={[0, 3, 1]}
    castsShadow={true}
  />
  <ViroARImageMarker   // alternative: ViroARPlaneSelector
    target="neckAnchor"
    onAnchorFound={onAnchorFound}
  >
    <Viro3DObject
      source={{ uri: glbFileUri }}
      position={[0, 0, 0]}
      scale={[scaleFactor, scaleFactor, scaleFactor]}
      rotation={[0, rotationY, 0]}   // tracks head rotation
      type="GLB"
      animation={{ name: "swing", run: physicsEnabled }}
    />
  </ViroARImageMarker>
</ViroARScene>
```

### Occlusion (Z-Buffering)
- ViroReact supports **real-world occlusion** via ARCore Depth API
- When user's chin moves in front of necklace, depth buffer hides the obscured portion
- Requires ARCore-compatible device (Android 9+, most mid-range 2020+ phones)

### Physics — Necklace Swing (Phase 2)
```
F = ma  →  Necklace pendant acceleration = device_acceleration × mass_coefficient
```
- **Engine:** Cannon.js integrated via `@react-three/cannon`
- **Constraint:** Chain links modeled as rigid bodies with hinge joints
- **Trigger:** `DeviceMotion` API feeds linear acceleration → physics engine

---

## Edge Cases & Failure Handling

| Edge Case | Detection | Response |
|:----------|:----------|:---------|
| Poor lighting | Frame brightness < threshold | Toast: "Move to better lighting" |
| No person detected | MediaPipe confidence < 0.5 | Overlay: "Point camera at yourself" |
| Person too far away | Shoulder width < 80px | Toast: "Move closer to camera" |
| Person too close | Shoulder width > 600px | Toast: "Move back a bit" |
| Model load failure | `.glb` fetch error | Retry ×3, then fallback to flat PNG overlay |
| Meshy.ai timeout (>30s) | Backend circuit breaker | Use TripoSR fallback or queue |
| Non-jewelry image | Classifier confidence < 0.70 | Return clear error with instructions |
