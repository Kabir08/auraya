import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ActivityIndicator, Text, ProgressBar } from 'react-native-paper';

import { useARStore } from '../store/useARStore';

const STEP_LABELS: Record<string, string> = {
  idle:       'Waiting…',
  uploading:  'Uploading image…',
  segmenting: 'Removing background…',
  generating: 'Generating 3D model…',
  ready:      '✓ Ready',
  error:      '✗ Something went wrong',
};

export default function ProcessingScreen() {
  const { processingStatus, processingProgress, processingError, jewelryType } =
    useARStore();

  const isError    = processingStatus === 'error';
  const isDone     = processingStatus === 'ready';
  const label      = STEP_LABELS[processingStatus] ?? processingStatus;
  const progressFraction = processingProgress / 100;

  return (
    <View style={styles.container}>
      {!isError && !isDone && (
        <ActivityIndicator animating size="large" color="#f5c842" style={styles.spinner} />
      )}

      <Text variant="titleLarge" style={[styles.label, isError && styles.errorText]}>
        {label}
      </Text>

      {processingStatus === 'generating' && (
        <>
          <ProgressBar
            progress={progressFraction}
            color="#f5c842"
            style={styles.bar}
          />
          <Text variant="bodySmall" style={styles.percent}>
            {processingProgress}%
          </Text>
        </>
      )}

      {isError && (
        <Text variant="bodyMedium" style={styles.errorDetail}>
          {processingError ?? 'Unknown error. Please try again.'}
        </Text>
      )}

      <View style={styles.steps}>
        {[
          { key: 'uploading',  label: 'Upload image' },
          { key: 'segmenting', label: 'Remove background' },
          { key: 'generating', label: 'Generate 3D model' },
          { key: 'ready',      label: 'Launch AR try-on' },
        ].map(({ key, label: stepLabel }) => {
          const statuses = ['uploading', 'segmenting', 'generating', 'ready', 'error'];
          const currentIdx = statuses.indexOf(processingStatus);
          const stepIdx    = statuses.indexOf(key);
          const done  = stepIdx < currentIdx || processingStatus === 'ready';
          const active = key === processingStatus;
          return (
            <Text
              key={key}
              variant="bodyMedium"
              style={[styles.step, done && styles.stepDone, active && styles.stepActive]}
            >
              {done ? '✓' : active ? '↻' : '○'}  {stepLabel}
            </Text>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container:   { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, backgroundColor: '#0a0a0a' },
  spinner:     { marginBottom: 24 },
  label:       { color: '#f5c842', marginBottom: 12, textAlign: 'center' },
  bar:         { width: '80%', height: 8, borderRadius: 4, marginVertical: 8 },
  percent:     { color: '#aaa', marginBottom: 16 },
  steps:       { marginTop: 32, alignSelf: 'flex-start', width: '100%' },
  step:        { color: '#555', marginVertical: 4, paddingHorizontal: 16 },
  stepDone:    { color: '#4caf50' },
  stepActive:  { color: '#f5c842' },
  errorText:   { color: '#f44336' },
  errorDetail: { color: '#f44336', textAlign: 'center', marginTop: 8 },
});
