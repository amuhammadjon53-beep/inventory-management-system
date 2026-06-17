import { defineConfig } from 'vite';
import path from 'path';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  root: '.',
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://192.168.1.238:8000',
        changeOrigin: true,
      }
    }
  },
  appType: 'mpa',
  build: {
    rollupOptions: {
      input: {
        home: path.resolve(__dirname, 'index.html'),
        commands: path.resolve(__dirname, 'Commands/index.html'),
        server: path.resolve(__dirname, 'Manage Servers/index.html'),
        docs: path.resolve(__dirname, 'docs/index.html'),
        cart: path.resolve(__dirname, 'Cart/index.html'),
        mySubscriptions: path.resolve(__dirname, 'My Subscriptions/index.html'),
        premium: path.resolve(__dirname, 'Premium/index.html'),
        messages: path.resolve(__dirname, 'Dashboard/Messages/index.html'),
        voice: path.resolve(__dirname, 'Dashboard/Voice Activity/index.html'),
        activity: path.resolve(__dirname, 'Dashboard/Activity/index.html'),
        emojis: path.resolve(__dirname, 'Dashboard/Emoji Tracking/index.html'),
        mentions: path.resolve(__dirname, 'Dashboard/Mentions/index.html'),
        invites: path.resolve(__dirname, 'Dashboard/Invite Tracking/index.html'),
        growth: path.resolve(__dirname, 'Dashboard/Growth/index.html'),
        settings: path.resolve(__dirname, 'Dashboard/Settings/index.html'),
        resetStats: path.resolve(__dirname, 'Dashboard/Reset/index.html'),
        blacklist: path.resolve(__dirname, 'Dashboard/Blacklist/index.html'),
        debug: path.resolve(__dirname, 'Dashboard/Debug/index.html'),
        distribution: path.resolve(__dirname, 'Dashboard/Distribution/index.html'),
        subscriptions: path.resolve(__dirname, 'Dashboard/Subscriptions/index.html'),
      },
    },
  },
});