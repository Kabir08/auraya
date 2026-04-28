import React from 'react';
import { View, StyleSheet, Image } from 'react-native';
import { Button, Text, Surface } from 'react-native-paper';
import { useNavigation } from '@react-navigation/native';
import type { StackNavigationProp } from '@react-navigation/stack';
import * as ImagePicker from 'expo-image-picker';

import { useARStore } from '../store/useARStore';
import { segmentImage, generate3D, connectProgressSocket } from '../services/api';
import type { RootStackParamList } from '../navigation/AppNavigator';

type Nav = StackNavigationProp<RootStackParamList, 'Home'>;

export default function HomeScreen() {
  const navigation = useNavigation<Nav>();
  const { setRawImage, setSegmentedPng, setMeshTask, setProgress, setGlbUri, setError, resetSession } =
    useARStore();

  const handleGallery = async () => {
    resetSession();
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      alert('Gallery permission is required.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality:    0.9,
    });
    if (result.canceled || !result.assets[0]) return;

    const uri = result.assets[0].uri;
    setRawImage(uri);
    navigation.navigate('Processing');
    await _runPipeline(uri);
  };

  const handleCamera = () => {
    resetSession();
    navigation.navigate('Camera');
  };

  // ── Full pipeline: segment → 3D → navigate to AR ──────────────────────────
  const _runPipeline = async (imageUri: string) => {
    try {
      // Stage A: segmentation
      const seg = await segmentImage(imageUri);
      setSegmentedPng(seg.png_url, seg.jewelry_type);

      // Stage B: 3D generation
      const mesh = await generate3D(seg.png_url, seg.jewelry_type);
      setMeshTask(mesh.task_id);

      // Stream progress via WebSocket
      await new Promise<void>((resolve, reject) => {
        const ws = connectProgressSocket(
          mesh.task_id,
          (event) => {
            if (event.type === 'progress')   setProgress(event.percent);
            if (event.type === 'completed') { setGlbUri(event.glb_url); ws.close(); resolve(); }
            if (event.type === 'error')     { setError(event.message);  ws.close(); reject(new Error(event.message)); }
          },
        );
      });

      navigation.navigate('AR');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  return (
    <View style={styles.container}>
      <Image
        source={require('../../assets/logo-placeholder.png')}
        style={styles.logo}
        resizeMode="contain"
      />
      <Text variant="headlineMedium" style={styles.tagline}>
        Wear it before you buy it.
      </Text>

      <Surface style={styles.card} elevation={2}>
        <Button
          mode="contained"
          icon="camera"
          onPress={handleCamera}
          style={styles.btn}
          contentStyle={styles.btnContent}
        >
          Use Camera
        </Button>
        <Button
          mode="outlined"
          icon="image"
          onPress={handleGallery}
          style={styles.btn}
          contentStyle={styles.btnContent}
        >
          Upload from Gallery
        </Button>
      </Surface>

      <Text variant="bodySmall" style={styles.hint}>
        Point your camera at a jewelry item or upload a photo from your gallery.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container:  { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: '#0a0a0a' },
  logo:       { width: 160, height: 80, marginBottom: 16 },
  tagline:    { color: '#f5c842', marginBottom: 32, textAlign: 'center' },
  card:       { width: '100%', padding: 24, borderRadius: 16, backgroundColor: '#1a1a1a' },
  btn:        { marginVertical: 8 },
  btnContent: { paddingVertical: 6 },
  hint:       { marginTop: 24, color: '#888', textAlign: 'center' },
});
