import { useEffectOnActive } from 'keepalive-for-react'

export function useRouteActivationRefresh(callback: () => void) {
  useEffectOnActive(callback, [callback], true)
}
