const backendUrl = document.querySelector<HTMLInputElement>('#backendUrl')
const token = document.querySelector<HTMLInputElement>('#token')
const save = document.querySelector<HTMLButtonElement>('#save')

chrome.storage.sync.get(['backendUrl', 'token']).then((data) => {
  if (backendUrl) backendUrl.value = String(data.backendUrl ?? '')
  if (token) token.value = String(data.token ?? '')
})

save?.addEventListener('click', () => {
  void chrome.storage.sync.set({
    backendUrl: backendUrl?.value ?? '',
    token: token?.value ?? '',
  })
})
