import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'lab',
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: false,
  },
  build: {
    outDir: '../dist-lab',
    emptyOutDir: true,
  },
});
