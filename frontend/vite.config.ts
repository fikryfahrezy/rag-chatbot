import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

const pageRoutes: Record<string, string> = {
  '/initial': '/initial/',
  '/initial/': '/initial/',
  '/database': '/second/',
  '/database/': '/second/',
  '/pdf': '/second/',
  '/pdf/': '/second/',
  '/admin': '/second/',
  '/admin/': '/second/',
}

function routeEntries(): Plugin {
  const rewrite = () => (request: { url?: string }, _response: unknown, next: () => void) => {
    if (request.url) {
      const [pathname, query] = request.url.split('?', 2)
      const target = pageRoutes[pathname]
      if (target) request.url = target + (query ? `?${query}` : '')
    }
    next()
  }

  return {
    name: 'route-entries',
    configureServer(server) {
      server.middlewares.use(rewrite())
    },
    configurePreviewServer(server) {
      server.middlewares.use(rewrite())
    },
  }
}

export default defineConfig({
  envDir: '..',
  plugins: [vue(), routeEntries()],
  build: {
    rollupOptions: {
      input: {
        initial: 'initial/index.html',
        second: 'second/index.html',
      },
    },
  },
  server: { port: 5173 },
})
