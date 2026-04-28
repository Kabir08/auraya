import React, { useEffect, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import { Button, Text } from 'react-native-paper';
import { CameraView, CameraType, useCameraPermissions } from 'expo-camera';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';

import { useARStore } from '../store/useARStore';
import { segmentImage, generate3D, connectProgressSocket } from '../services/api';
import type { RootStackParamList } from '../navigation/AppNavigator';

type Nav = StackNavigationProp<RootStackParamList, 'Camera'>;

export default function CameraScreen() {
  const navigation           = useNavigation<Nav>();
  const cameraRef            = useRef<CameraView>(null);
  const [permission, request] = useCameraPermissions();
  const { setRawImage, setSegmentedPng, setMeshTask, setProgress, setGlbUri, setError } =
    useARStore();

  useEffect(() => {
    if (!permission?.granted) request();
  }, []);

  const captureAndProcess = async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.9 });
      if (!photo) return;

      setRawImage(photo.uri);
      navigation.navigate('Processing');

      // Stage A: segmentation
      const seg = await segmentImage(photo.uri);
      setSegmentedPng(seg.png_url, seg.jewelry_type);

      // Stage B: 3D
      const mesh = await generate3D(seg.png_url, seg.jewelry_type);
      setMeshTask(mesh.task_id);

      await new Promise<void>((resolve, reject) => {
        const ws = connectProgressSocket(mesh.task_id, (event) => {
          if (event.type === 'progress')   setProgress(event.percent);
          if (event.type === 'completed') { setGlbUri(event.glb_url); ws.close(); resolve(); }
          if (event.type === 'error')     { setError(event.message);  ws.close(); reject(new Error(event.message)); }
        });
      });

      navigation.navigate('AR');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Capture failed');
      navigation.goBack();
    }
  };

  if (!permission) return <View style={styles.container} />;
  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.msg}>Camera permission required.</Text>
        <Button onPress={request}>Grant Permission</Button>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back">
        <View style={styles.overlay}>
          <Text style={styles.guide}>Point at a jewelry item</Text>
          <Button
            mode="contained"
            onPress={captureAndProcess}
            style={styles.captureBtn}
            icon="camera"
          >
            Capture
          </Button>
        </View>
      </CameraView>
    </View>
  );
}

const styles = StyleSheet.create({
  container:  { flex: 1, backgroundColor: '#000' },
  camera:     { flex: 1 },
  overlay:    { flex: 1, justifyContent: 'flex-end', padding: 32, alignItems: 'center' },
  guide:      { color: '#fff', fontSize: 16, marginBottom: 24, textShadowColor: '#000', textShadowRadius: 4 },
  captureBtn: { width: 180 },
  msg:        { color: '#fff', textAlign: 'center', marginBottom: 16 },
});
