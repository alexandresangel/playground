# dia_jwt

Small RS256 JWT helper (PKCS#12, mint, validate, revoke). Copy this folder into other Python projects.

```bash
pip install pyjwt cryptography
export JWT_KEYSTORE_PASSWORD='…'
python3 -m dia_jwt create-keystore --path jwt_keystore.p12
python3 -m dia_jwt mint --sub instance:prod --role chat --days 365
```

```python
from dia_jwt import JwtAuth

auth = JwtAuth("jwt_keystore.p12", os.environ["JWT_KEYSTORE_PASSWORD"])
# or: JwtAuth(keystore_password=..., keystore_bytes=base64.b64decode(...))
token = auth.mint(sub="instance:prod", roles=["chat"])
auth.validate(token["access_token"], roles=["chat"])
```

FastAPI: `from dia_jwt.fastapi import jwt_deps, Identity` then `deps = jwt_deps(auth)` — roles `admin`, `chat`, `refresh` (e.g. `POST /api/refresh-prompt` requires `refresh`).