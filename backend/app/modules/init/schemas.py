from pydantic import BaseModel, Field


class InitConfigResponse(BaseModel):
    initialized: bool
    databaseConfigured: bool
    redisConfigured: bool


class InitConfigRequest(BaseModel):
    # PostgreSQL
    databaseHost: str = Field(default="localhost", min_length=1)
    databasePort: int = Field(default=54329, ge=1, le=65535)
    databaseName: str = Field(default="jav", min_length=1)
    databaseUser: str = Field(default="admin", min_length=1)
    databasePassword: str = Field(default="admin123")
    postgresConnectTimeout: int = Field(default=5, ge=1, le=60)
    postgresPoolSize: int = Field(default=5, ge=1, le=50)
    postgresMaxOverflow: int = Field(default=10, ge=0, le=100)
    postgresMaxRetries: int = Field(default=10, ge=1, le=60)
    postgresRetryDelay: int = Field(default=3, ge=0, le=60)
    # Redis
    redisHost: str = Field(default="localhost", min_length=1)
    redisPort: int = Field(default=6379, ge=1, le=65535)
    redisPassword: str = Field(default="")
    redisSocketTimeout: int = Field(default=5, ge=1, le=60)
    redisConnectTimeout: int = Field(default=5, ge=1, le=60)
    redisMaxConnections: int = Field(default=10, ge=1, le=200)
