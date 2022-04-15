from aw_core.config import load_config_toml

default_config = """
[server]
host = "localhost"
port = "5600"
storage = "mongodb"
cors_origins = "*"
secret = "secret"

[server.custom_static]

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""

[server-testing.custom_static]
""".strip()

config = load_config_toml("aw-server", default_config)
