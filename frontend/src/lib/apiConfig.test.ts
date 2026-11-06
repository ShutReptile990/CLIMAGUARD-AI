import assert from 'node:assert/strict'
import test from 'node:test'
import { buildApiUrl, normalizeApiBase } from './apiConfig.ts'

test('development may use the Vite proxy when no API origin is configured', () => {
  assert.equal(normalizeApiBase(undefined, false), '')
})

test('production requires an explicit HTTPS API origin', () => {
  assert.throws(() => normalizeApiBase(undefined, true), /required for production/)
  assert.throws(() => normalizeApiBase('http://api.example.com', true), /HTTPS/)
})

test('normalization removes trailing slash and accepted API suffixes', () => {
  assert.equal(normalizeApiBase('https://api.example.com/api/v1/', true), 'https://api.example.com')
  assert.equal(normalizeApiBase('https://api.example.com/api', true), 'https://api.example.com')
})

test('normalization rejects deployment paths that could duplicate routes', () => {
  assert.throws(() => normalizeApiBase('https://api.example.com/backend', true), /backend origin/)
})

test('API paths receive exactly one version prefix', () => {
  assert.equal(buildApiUrl('https://api.example.com', '/health'), 'https://api.example.com/api/v1/health')
})
