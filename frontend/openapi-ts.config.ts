import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input:
    process.env.MOLABEL_OPENAPI_INPUT ??
    'http://localhost:8000/api/openapi.json',
  output: { path: 'src/api/generated', postProcess: ['prettier'] },
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
    '@tanstack/react-query',
  ],
})
