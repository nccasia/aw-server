from aw_core.config import load_config_toml

default_config = """
[server]
host = "0.0.0.0"
port = "5600"
storage = "peewee"
cors_origins = "*"

[server.custom_static]

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""

[server-testing.custom_static]
""".strip()

config = load_config_toml("aw-server", default_config)
