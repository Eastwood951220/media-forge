export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type?: string
  expires_in?: number
}
