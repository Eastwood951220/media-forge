import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: 'src/background.ts',
        content: 'src/content.ts',
        options: 'src/options.html',
      },
      output: {
        entryFileNames: '[name].js',
      },
    },
  },
})
