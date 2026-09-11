import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_ROUTES = ['/chat', '/system', '/tasks', '/notes', '/actions', '/confirm', '/health'];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: 'http://localhost:8000', changeOrigin: true }]),
    ),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.js'],
    globals: true,
  },
});
