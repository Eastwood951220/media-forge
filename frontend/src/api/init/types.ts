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
