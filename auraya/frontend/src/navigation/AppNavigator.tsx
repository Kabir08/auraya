import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator }  from '@react-navigation/stack';

import HomeScreen       from '../screens/HomeScreen';
import CameraScreen     from '../screens/CameraScreen';
import ProcessingScreen from '../screens/ProcessingScreen';
import ARScreen         from '../screens/ARScreen';

export type RootStackParamList = {
  Home:       undefined;
  Camera:     undefined;
  Processing: undefined;
  AR:         undefined;
};

const Stack = createStackNavigator<RootStackParamList>();

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerStyle:   { backgroundColor: '#0a0a0a' },
          headerTintColor: '#f5c842',
          headerTitleStyle: { fontWeight: 'bold' },
          cardStyle:     { backgroundColor: '#0a0a0a' },
        }}
      >
        <Stack.Screen name="Home"       component={HomeScreen}       options={{ title: '✨ Auraya' }} />
        <Stack.Screen name="Camera"     component={CameraScreen}     options={{ title: 'Capture Jewelry' }} />
        <Stack.Screen name="Processing" component={ProcessingScreen} options={{ title: 'Processing…',  headerLeft: () => null }} />
        <Stack.Screen name="AR"         component={ARScreen}         options={{ headerShown: false }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
