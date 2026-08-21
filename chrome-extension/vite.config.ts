import { copyFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [
    {
      name: 'copy-extension-manifest',
      closeBundle() {
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
        content: 'src/content.ts',
        options: 'options.html',
        popup: 'popup.html',
      },
      output: {
        entryFileNames: '[name].js',
      },
    },
  },
})
