import { useState } from 'react'
import type { FormInstance } from 'antd'
import { testPostgres, testRedis } from '@/api/init'
import type { ConnectionTestResult, InitConfigRequest } from '@/api/init/types'
import { getPgTestParams, getRedisTestParams } from '../utils/initParams'

export function useInitConnectionTests(form: FormInstance<InitConfigRequest>) {
  const [pgTesting, setPgTesting] = useState(false)
  const [redisTesting, setRedisTesting] = useState(false)
  const [pgResult, setPgResult] = useState<ConnectionTestResult | null>(null)
  const [redisResult, setRedisResult] = useState<ConnectionTestResult | null>(null)

  const handleTestPg = async () => {
    setPgTesting(true)
    setPgResult(null)
    try {
      const values = form.getFieldsValue()
      const res = await testPostgres(getPgTestParams(values))
      setPgResult(res as ConnectionTestResult)
    } catch {
      setPgResult({ success: false, message: '测试请求失败' })
    } finally {
      setPgTesting(false)
    }
  }

  const handleTestRedis = async () => {
    setRedisTesting(true)
    setRedisResult(null)
    try {
      const values = form.getFieldsValue()
      const res = await testRedis(getRedisTestParams(values))
      setRedisResult(res as ConnectionTestResult)
    } catch {
      setRedisResult({ success: false, message: '测试请求失败' })
    } finally {
      setRedisTesting(false)
    }
  }

  return {
    pgTesting,
    redisTesting,
    pgResult,
    redisResult,
    handleTestPg,
    handleTestRedis,
  }
}
