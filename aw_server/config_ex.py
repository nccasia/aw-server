from aw_core.config import load_config_toml

default_config = """
[server]
host = "SV_HOST"
port = "SV_PORT"
storage = "mongodb"
cors_origins = "*"
secret = "secret"
mongo_url = "mongodb://DB_HOST:DB_PORT/"

[server.custom_static]

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""

[server-testing.custom_static]
""".strip()

config = load_config_toml("aw-server", default_config)
