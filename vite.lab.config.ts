import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'lab',
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: false,
    proxy: {
      '/api/v20': 'http://127.0.0.1:8176',
      '/api/source-tracking-lab': 'http://127.0.0.1:8176',
    },
  },
  build: {
    outDir: '../dist-lab',
    emptyOutDir: true,
    rollupOptions: { input: { main: 'lab/index.html', sourceTracking: 'lab/source-tracking.html', repositoryTracking: 'lab/repository-tracking.html' } },
  },
});
