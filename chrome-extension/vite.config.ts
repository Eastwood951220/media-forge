import { copyFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { build, defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    {
      name: 'copy-extension-manifest',
      apply: 'build',
      async closeBundle() {
        // Manifest content scripts cannot import shared React chunks.
        await build({
          configFile: false,
          define: { 'process.env.NODE_ENV': JSON.stringify('production'), 'process.env': '{}'  },
          build: {
            outDir: 'dist', emptyOutDir: false,
            lib: { entry: resolve(import.meta.dirname, 'src/content.ts'), name: 'MediaForgeContent', formats: ['iife'], fileName: () => 'content.js' },
          },
        })
        copyFileSync(
          resolve(import.meta.dirname, 'manifest.json'),
          resolve(import.meta.dirname, 'dist/manifest.json'),
        )
      },
    },
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: 'src/background.ts',
        options: 'options.html',
        popup: 'popup.html',
      },
      output: {
        entryFileNames: '[name].js',
      },
    },
  },
})
