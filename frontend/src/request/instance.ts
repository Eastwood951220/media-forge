import axios from 'axios'

export const baseURL = import.meta.env.VITE_APP_BASE_API || ''

axios.defaults.headers['Content-Type'] = 'application/json;charset=utf-8'

export const service = axios.create({
  baseURL,
  timeout: 50000,
  headers: {
    'Content-Type': 'application/json;charset=utf-8',
  },
  transitional: {
    clarifyTimeoutError: true,
  },
})
