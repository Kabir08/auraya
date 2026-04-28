/**
 * ARScreen — full-screen AR try-on view.
 *
 * Renders the .glb jewelry model anchored to the user's neck using:
 *   • expo-gl  — OpenGL surface
 *   • react-three-fiber — Three.js scene graph
 *   • react-native-mediapipe — on-device pose tracking
 *
 * Phase 1: fixed depth (no ARCore Depth API), pose-anchored position.
 * Phase 2: ARCore depth → real occlusion + physics swing.
 */
import React, { Suspense, useEffect, useRef, useState } from 'react';
import { Dimensions, StyleSheet, TouchableOpacity, View, Text } from 'react-native';
import { Canvas } from '@react-three/fiber/native';
import { useGLTF, Environment } from '@react-three/drei/native';
import { PoseLandmarker } from 'react-native-mediapipe';
import { CameraView } from 'expo-camera';
import * as MediaLibrary from 'expo-media-library';

import { useARStore } from '../store/useARStore';
import {
  computeNeckAnchor,
  computeScaleFactor,
  isPoseReliable,
  anchorToWorldPosition,
} from '../services/mediapipe';

const { width: W, height: H } = Dimensions.get('window');

// ─── 3D model component ───────────────────────────────────────────────────────
function JewelryModel({
  uri,
  position,
  scale,
  rotationY,
}: {
  uri:      string;
  position: [number, number, number];
  scale:    number;
  rotationY: number;
}) {
  const { scene } = useGLTF(uri);
  return (
    <primitive
      object={scene}
      position={position}
      scale={[scale, scale, scale]}
      rotation={[0, (rotationY * Math.PI) / 180, 0]}
    />
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────
export default function ARScreen() {
  const {
    glbUri, scaleFactor, rotationY,
    setNeckAnchor, setRotationY,
    neckAnchor, poseReliable,
  } = useARStore();

  const [guide, setGuide] = useState<string | null>(null);
  const cameraRef = useRef<CameraView>(null);

  // ── MediaPipe pose tracking ───────────────────────────────────────────────
  const poseLandmarker = useRef<PoseLandmarker | null>(null);

  useEffect(() => {
    let running = true;

    async function initMediaPipe() {
      poseLandmarker.current = await PoseLandmarker.createFromModelPath(
        'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',
      );

      const loop = async () => {
        if (!running || !poseLandmarker.current) return;
        // In a real integration, feed camera frames here.
        // react-native-mediapipe provides a frame processor plugin for VisionCamera.
        // This stub shows the structure; see docs for frame processor wiring.
        requestAnimationFrame(loop);
      };
      loop();
    }

    initMediaPipe();
    return () => { running = false; };
  }, []);

  // Guide message based on shoulder width (scale factor is a proxy)
  useEffect(() => {
    if (!poseReliable) { setGuide('Point camera at yourself'); return; }
    if (scaleFactor < 0.5) { setGuide('Move closer'); return; }
    if (scaleFactor > 2.5) { setGuide('Move back a bit'); return; }
    setGuide(null);
  }, [scaleFactor, poseReliable]);

  // ── Compute world position ────────────────────────────────────────────────
  const modelPosition: [number, number, number] = neckAnchor
    ? anchorToWorldPosition(neckAnchor, W, H)
    : [0, 0, -0.5];

  // ── Screenshot save ───────────────────────────────────────────────────────
  const saveSnapshot = async () => {
    if (!cameraRef.current) return;
    const snap = await cameraRef.current.takePictureAsync({ skipProcessing: true });
    if (!snap) return;
    await MediaLibrary.saveToLibraryAsync(snap.uri);
    setGuide('Saved to gallery ✓');
    setTimeout(() => setGuide(null), 2000);
  };

  if (!glbUri) return (
    <View style={styles.container}>
      <Text style={styles.errorText}>No 3D model loaded. Go back and try again.</Text>
    </View>
  );

  return (
    <View style={styles.container}>
      {/* Live camera background */}
      <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="front" />

      {/* Three.js AR overlay */}
      <Canvas style={StyleSheet.absoluteFill}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[2, 4, 2]} intensity={1.2} />
        <Suspense fallback={null}>
          <JewelryModel
            uri={glbUri}
            position={modelPosition}
            scale={scaleFactor}
            rotationY={rotationY}
          />
          <Environment preset="studio" />
        </Suspense>
      </Canvas>

      {/* Guide overlay */}
      {guide && (
        <View style={styles.guideBanner}>
          <Text style={styles.guideText}>{guide}</Text>
        </View>
      )}

      {/* Bottom toolbar */}
      <View style={styles.toolbar}>
        <TouchableOpacity style={styles.toolBtn} onPress={() => setRotationY((rotationY + 15) % 360)}>
          <Text style={styles.toolIcon}>↻</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.captureBtn} onPress={saveSnapshot}>
          <Text style={styles.captureIcon}>📸</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.toolBtn} onPress={() => setRotationY((rotationY - 15 + 360) % 360)}>
          <Text style={styles.toolIcon}>↺</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: '#000' },
  guideBanner: { position: 'absolute', top: 60, alignSelf: 'center', backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 20, paddingHorizontal: 20, paddingVertical: 8 },
  guideText:   { color: '#f5c842', fontSize: 14 },
  toolbar:     { position: 'absolute', bottom: 40, flexDirection: 'row', width: '100%', justifyContent: 'center', alignItems: 'center', gap: 32 },
  toolBtn:     { width: 48, height: 48, borderRadius: 24, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  toolIcon:    { color: '#fff', fontSize: 22 },
  captureBtn:  { width: 72, height: 72, borderRadius: 36, backgroundColor: '#f5c842', alignItems: 'center', justifyContent: 'center' },
  captureIcon: { fontSize: 32 },
  errorText:   { color: '#f44336', textAlign: 'center', marginTop: 100, fontSize: 16 },
});
