export interface InitConfigResponse {
  initialized: boolean
  databaseConfigured: boolean
  redisConfigured: boolean
}

export interface InitConfigRequest {
  databaseHost: string
  databasePort: number
  databaseName: string
  databaseUser: string
  databasePassword: string
  postgresConnectTimeout: number
  postgresPoolSize: number
  postgresMaxOverflow: number
  postgresMaxRetries: number
  postgresRetryDelay: number
  redisHost: string
  redisPort: number
  redisPassword: string
  redisSocketTimeout: number
  redisConnectTimeout: number
  redisMaxConnections: number
}

export interface ConnectionTestResult {
  success: boolean
  message: string
}

export interface PostgresTestParams {
  host: string
  port: number
  database: string
  user: string
  password: string
  connect_timeout: number
}

export interface RedisTestParams {
  host: string
  port: number
  password: string
  socket_timeout: number
  connect_timeout: number
}
