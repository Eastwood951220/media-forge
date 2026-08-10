const backendUrl = document.querySelector<HTMLInputElement>('#backendUrl')
const token = document.querySelector<HTMLInputElement>('#token')
const save = document.querySelector<HTMLButtonElement>('#save')
const statusText = document.querySelector<HTMLElement>('#status')

chrome.storage.sync.get(['backendUrl', 'token']).then((data) => {
  if (backendUrl) backendUrl.value = String(data.backendUrl ?? '')
  if (token) token.value = String(data.token ?? '')
})

save?.addEventListener('click', async () => {
  await chrome.storage.sync.set({
    backendUrl: backendUrl?.value ?? '',
    token: token?.value ?? '',
  })
  try {
    await chrome.runtime.sendMessage({ type: 'agent_settings_saved' })
    if (statusText) statusText.textContent = 'Saved. Agent is reconnecting.'
  } catch (error) {
    if (statusText) statusText.textContent = error instanceof Error ? error.message : 'Saved. Reload extension if needed.'
  }
})
