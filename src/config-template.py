class Config:
    # Bot token
    TOKEN: str = "token"

    # In debug mode commands will be enabled by default in the debug guild
    DEBUG_MODE: bool = False

    # Debug guilds, commands will be enabled here by default
    DEBUG_GUILD_IDS: list[int] = []

    # Error tracebacks and other logs will be sent to this channel
    LOGGING_CHANNEL_ID: int = 1234

    # POSTGRES Database connection
    POSTGRES_DB: str = "battlefrontbot"
    POSTGRES_USER: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_VERSION: int = 16
