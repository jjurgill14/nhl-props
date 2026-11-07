/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built into ../docs/app so GitHub Pages serves it next to the pipeline's JSON.
// In dev, ../docs is served as the public dir so board.json and assets/ resolve the same way.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: '/nhl-props/app/',
  publicDir: command === 'serve' ? '../docs' : false,
  build: { outDir: '../docs/app', emptyOutDir: true },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
}))
