import { toNumber } from 'lodash'
import cache from '@/utils/cache'
import type { PlusInternalRequestConfig, RepeatSubmitRecord } from './types'
import { getHeaderValue, getRequestMethod, isFalseLike } from './utils'

const SESSION_REPEAT_KEY = 'sessionObj'
const DEFAULT_REPEAT_INTERVAL = 500

/**
 * 判断当前 POST/PUT 是否为短时间内重复提交。
 *
 * 判定维度：url + data + time。
 * data 会先转成字符串，避免对象引用不同但内容相同导致误放行。
 */
export function checkRepeatSubmit(config: PlusInternalRequestConfig): boolean {
  const method = getRequestMethod(config)
  const repeatSubmitHeader = getHeaderValue(config, 'repeatSubmit')

  if (
    isFalseLike(repeatSubmitHeader) ||
    config.isRepeatSubmit === false ||
    (method !== 'post' && method !== 'put')
  ) {
    return false
  }

  const requestRecord: RepeatSubmitRecord = {
    url: config.url,
    data: typeof config.data === 'object' && config.data !== null
      ? JSON.stringify(config.data)
      : String(config.data ?? ''),
    time: Date.now(),
  }

  const previousRecord =
    cache.session.getJSON<RepeatSubmitRecord>(SESSION_REPEAT_KEY)

  if (!previousRecord) {
    cache.session.setJSON(SESSION_REPEAT_KEY, requestRecord)
    return false
  }

  const interval =
    toNumber(getHeaderValue(config, 'interval')) ||
    config.repeatSubmitInterval ||
    toNumber(import.meta.env.VITE_APP_REPEAT_SUBMIT_INTERVAL) ||
    DEFAULT_REPEAT_INTERVAL

  const isSameRequest =
    previousRecord.url === requestRecord.url &&
    previousRecord.data === requestRecord.data
  const isWithinInterval = requestRecord.time - previousRecord.time < interval

  if (isSameRequest && isWithinInterval) {
    console.warn(`[${requestRecord.url}]: 数据正在处理，请勿重复提交`)
    return true
  }

  cache.session.setJSON(SESSION_REPEAT_KEY, requestRecord)
  return false
}
