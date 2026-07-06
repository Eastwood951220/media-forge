import { useState } from 'react'
import { message } from 'antd'
import { saveInitConfig, testPostgres, testRedis } from '@/api/init'
import type { InitConfigRequest } from '@/api/init/types'
import { getPgTestParams, getRedisTestParams } from '../utils/initParams'

export function useInitSubmit() {
  const [loading, setLoading] = useState(false)

  const handleFinish = async (values: InitConfigRequest) => {
    setLoading(true)
    try {
      // Auto-test both connections before saving
      const [pgRes, redisRes] = await Promise.all([
        testPostgres(getPgTestParams(values)),
        testRedis(getRedisTestParams(values)),
      ])

      const pgOk = pgRes.success
      const redisOk = redisRes.success

      if (!pgOk || !redisOk) {
        const msgs: string[] = []
        if (!pgOk) msgs.push('PostgreSQL: ' + pgRes.message)
        if (!redisOk) msgs.push('Redis: ' + redisRes.message)
        void message.error(msgs.join('\n'))
        return
      }

      // Both passed — save configuration
      await saveInitConfig(values)
      void message.success('配置保存成功！正在跳转...')
      setTimeout(() => {
        window.location.href = '/login'
      }, 1500)
    } catch {
      void message.error('配置保存失败')
    } finally {
      setLoading(false)
    }
  }

  return { loading, handleFinish }
}
