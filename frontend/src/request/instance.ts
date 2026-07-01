import axios from 'axios'

const CLIENT_ID_HEADER = 'clientid'

export const baseURL = import.meta.env.VITE_APP_BASE_API || ''
export const clientId = import.meta.env.VITE_APP_CLIENT_ID || ''

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'

if (clientId) {
  axios.defaults.headers[CLIENT_ID_HEADER] = clientId
}

export const service = axios.create({
  baseURL,
  timeout: 50000,
  headers: {
    'Content-Type': 'application/json;charset=utf-8',
    ...(clientId ? { [CLIENT_ID_HEADER]: clientId } : {}),
  },
  transitional: {
    clarifyTimeoutError: true,
  },
})
