// Tiny shared theme store. The no-flash script in app.html sets
// `data-theme` before first paint; this module just reads + flips it
// in response to a user click. Persisted via localStorage so each
// route sees the same value on next mount.

const KEY = 'st-theme';

function currentFromDom(): 'dark' | 'light' {
  if (typeof document === 'undefined') return 'dark';
  const t = document.documentElement.dataset.theme;
  return t === 'light' ? 'light' : 'dark';
}

class ThemeStore {
  // Svelte 5 reactive primitive — consumers read .value, writes
  // propagate to DOM + localStorage.
  value = $state<'dark' | 'light'>('dark');
  constructor() {
    if (typeof document !== 'undefined') {
      this.value = currentFromDom();
    }
  }
  toggle() {
    this.value = this.value === 'light' ? 'dark' : 'light';
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.theme = this.value;
    }
    try { localStorage.setItem(KEY, this.value); } catch { /* ignore */ }
  }
}

export const theme = new ThemeStore();
