import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const manifest = JSON.parse(readFileSync(resolve(root, 'manifest.json'), 'utf8'))
const packageJson = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
const background = readFileSync(resolve(root, 'src/background.ts'), 'utf8')
const content = readFileSync(resolve(root, 'src/content.ts'), 'utf8')
const pageActionTypes = readFileSync(resolve(root, 'src/pageActions/types.ts'), 'utf8')
const options = readFileSync(resolve(root, 'src/options.ts'), 'utf8')
const popup = readFileSync(resolve(root, 'src/popup.ts'), 'utf8')

const requiredDistFiles = [
  'dist/manifest.json',
  'dist/options.html',
  'dist/popup.html',
  'dist/background.js',
  'dist/content.js',
]

for (const file of requiredDistFiles) {
  if (!existsSync(resolve(root, file))) {
    throw new Error(`missing build output: ${file}`)
  }
}

if (manifest.version !== packageJson.version) {
  throw new Error('manifest version must match package version')
}

const hostPermissions = manifest.host_permissions ?? []
if (!hostPermissions.includes('http://*/*') || !hostPermissions.includes('https://*/*')) {
  throw new Error('manifest must allow configured non-local backend URLs')
}

if (manifest.action?.default_popup !== 'popup.html') {
  throw new Error('manifest must expose the popup as the default action')
}

if (!background.includes('chrome.storage.onChanged.addListener')) {
  throw new Error('background must reconnect when saved backend settings change')
}

if (!background.includes('agent_reconnect_requested')) {
  throw new Error('background must handle explicit reconnect requests')
}

if (!content.includes("import { mountPageActions }") || !content.includes('bootstrapPageActions')) {
  throw new Error('content script must import and bootstrap JavDB page actions')
}

if (
  !background.includes('isPageActionMessage') ||
  !pageActionTypes.includes('page_action.list_tasks') ||
  !pageActionTypes.includes('page_action.open_run')
) {
  throw new Error('background message bridge must handle page-action task listing and run opening')
}

if (!options.includes('chrome.runtime.sendMessage')) {
  throw new Error('options page must wake background after saving settings')
}

if (!popup.includes('chrome.runtime.sendMessage') || !popup.includes('openOptionsPage')) {
  throw new Error('popup must support reconnect and opening the options page')
}

const distBackground = readFileSync(resolve(root, 'dist/background.js'), 'utf8')
const distContent = readFileSync(resolve(root, 'dist/content.js'), 'utf8')
const requiredStrings = [
  'agent.task_request',
  'protocol_version',
  'execution_deadline_at',
  'reconnect',
  'agent.heartbeat',
  'removeTab',
]
for (const str of requiredStrings) {
  if (!distBackground.includes(str)) {
    throw new Error(`built background.js must include ${str}`)
  }
}

for (const label of ['加入临时任务', '快速创建并全量爬取', '加入已有任务并增量爬取']) {
  if (!distContent.includes(label)) {
    throw new Error(`built content.js must include ${label}`)
  }
}

for (const [name, source] of [['background.js', distBackground], ['content.js', distContent]]) {
  if (source.includes('agt_secret')) {
    throw new Error(`built ${name} must not include a concrete Agent token`)
  }
}

console.log('agent extension verification passed')
