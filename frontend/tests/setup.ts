import '@testing-library/jest-dom/vitest'

// Mock window.matchMedia for Ant Design components in jsdom
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// Mock window.scrollTo for TanStack Router scroll restoration in jsdom
window.scrollTo = () => {}
