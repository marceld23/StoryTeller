import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  // SPA: pure static build served by the FastAPI backend (StaticFiles +
  // catch-all -> index.html). No SSR / Node at runtime.
  kit: { adapter: adapter({ fallback: 'index.html' }) }
};

export default config;
