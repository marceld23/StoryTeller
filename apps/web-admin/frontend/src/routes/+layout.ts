// SPA mode: no server-side rendering, no prerender. The whole app is a
// static bundle served by the FastAPI backend; all data comes from /api at
// runtime in the browser.
export const ssr = false;
export const prerender = false;
