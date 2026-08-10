import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json'), 'utf8'))
const background = readFileSync(resolve(root, 'src/background.ts'), 'utf8')
const options = readFileSync(resolve(root, 'src/options.ts'), 'utf8')

const requiredDistFiles = [
  'dist/manifest.json',
  'dist/options.html',
  'dist/background.js',
  'dist/content.js',
]

for (const file of requiredDistFiles) {
  if (!existsSync(resolve(root, file))) {
    throw new Error(`missing build output: ${file}`)
  }
}

const hostPermissions = manifest.host_permissions ?? []
if (!hostPermissions.includes('http://*/*') || !hostPermissions.includes('https://*/*')) {
  throw new Error('manifest must allow configured non-local backend URLs')
}

if (!background.includes('chrome.storage.onChanged.addListener')) {
  throw new Error('background must reconnect when saved backend settings change')
}

if (!options.includes('chrome.runtime.sendMessage')) {
  throw new Error('options page must wake background after saving settings')
}

console.log('agent extension verification passed')
