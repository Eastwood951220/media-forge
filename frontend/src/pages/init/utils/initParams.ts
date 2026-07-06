import type {
  InitConfigRequest,
  PostgresTestParams,
  RedisTestParams,
} from '@/api/init/types'

export function getPgTestParams(values: InitConfigRequest): PostgresTestParams {
  return {
    host: values.databaseHost,
    port: values.databasePort,
    database: values.databaseName,
    user: values.databaseUser,
    password: values.databasePassword,
    connect_timeout: values.postgresConnectTimeout,
  }
}

export function getRedisTestParams(values: InitConfigRequest): RedisTestParams {
  return {
    host: values.redisHost,
    port: values.redisPort,
    password: values.redisPassword,
    socket_timeout: values.redisSocketTimeout,
    connect_timeout: values.redisConnectTimeout,
  }
}
