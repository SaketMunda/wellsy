import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Local TTS (kokoro-js/onnxruntime-web) and the local LLM (web-llm) ship
  // multi-threaded WASM builds that need SharedArrayBuffer, which browsers
  // only grant to a cross-origin-isolated page. Without these, threading
  // silently degrades instead of erroring — that's what caused espeak-ng's
  // "Invalid language identifier" failure during Day 4 verification.
  server: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
  preview: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
  // `phonemizer`'s Emscripten glue (espeak-ng compiled to WASM) breaks when
  // Vite's dev-time esbuild pre-bundler rewrites it: espeak's internal voice
  // table ends up empty ("Invalid language identifier ... Should be one of:
  // <empty>") every time, deterministically, not as a race. Serving it
  // unbundled fixes it.
  optimizeDeps: {
    exclude: ['kokoro-js', 'phonemizer'],
  },
})
