/**
 * MediaPipe pose tracking helpers.
 *
 * Uses react-native-mediapipe to detect PoseLandmarks in each camera frame.
 * Exports utilities to compute the 3D neck anchor and scale factor for AR.
 */
import { PoseLandmarker, PoseLandmark } from 'react-native-mediapipe';

export interface Coords3D {
  x: number;
  y: number;
  z: number;
}

/** Euclidean distance in 2D (x/y normalised 0-1). */
function dist2D(a: PoseLandmark, b: PoseLandmark): number {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
}

/**
 * Compute the 3D neck-base anchor from MediaPipe pose landmarks.
 *
 * Uses landmarks 11 (left shoulder) and 12 (right shoulder).
 * Shifts the midpoint upward by 20 % of the shoulder separation height
 * to approximate the base of the neck / collarbone area.
 *
 * @param landmarks - Array of 33 PoseLandmarks from MediaPipe Holistic.
 * @returns { x, y, z } in normalised image space (0-1).
 */
export function computeNeckAnchor(landmarks: PoseLandmark[]): Coords3D {
  const L = landmarks[11]; // left shoulder
  const R = landmarks[12]; // right shoulder

  const midX = (L.x + R.x) / 2;
  const midY = (L.y + R.y) / 2;
  const midZ = (L.z + R.z) / 2;

  // Shoulder vertical separation used as the offset unit
  const shoulderHeight = Math.abs(L.y - R.y);
  const neckOffsetY    = shoulderHeight * 0.20;

  return { x: midX, y: midY - neckOffsetY, z: midZ };
}

/**
 * Compute a scale factor for the 3D model based on shoulder width.
 *
 * The reference width (250 normalised pixels) was calibrated for an average
 * adult standing ~60 cm from the camera.  The actual shoulder width in
 * normalised coords is divided by this reference to get a relative scale.
 */
const REFERENCE_SHOULDER_WIDTH = 0.25; // in normalised 0-1 space

export function computeScaleFactor(landmarks: PoseLandmark[]): number {
  const width = dist2D(landmarks[11], landmarks[12]);
  return Math.max(0.2, Math.min(3.0, width / REFERENCE_SHOULDER_WIDTH));
}

/**
 * Check whether MediaPipe has enough confidence to use the pose.
 * Returns false if either shoulder visibility is below threshold.
 */
const VISIBILITY_THRESHOLD = 0.5;

export function isPoseReliable(landmarks: PoseLandmark[]): boolean {
  const L = landmarks[11];
  const R = landmarks[12];
  return (
    (L.visibility ?? 0) > VISIBILITY_THRESHOLD &&
    (R.visibility ?? 0) > VISIBILITY_THRESHOLD
  );
}

/**
 * Normalised neck-anchor → Three.js world position.
 *
 * `viewportWidth` and `viewportHeight` are the camera preview dimensions in px.
 * `depth` is fixed for Phase 1 (no ARCore Depth API yet).
 */
export function anchorToWorldPosition(
  anchor: Coords3D,
  viewportWidth:  number,
  viewportHeight: number,
  depth = -0.5,
): [number, number, number] {
  // Map 0-1 normalised coords → centred coordinates (−0.5 to +0.5)
  const x =  (anchor.x - 0.5) * (viewportWidth  / viewportHeight);
  const y = -(anchor.y - 0.5); // Y is inverted in Three.js
  return [x, y, depth];
}
