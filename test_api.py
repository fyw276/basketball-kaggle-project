# -*- coding: utf-8 -*-
import urllib.request, urllib.error, json, http.client

BASE = 'http://127.0.0.1:8010/api/v1'

# 1. Login
print('[1] Login...')
try:
    data = json.dumps({'username': 'testuser123', 'password': 'test123456'}).encode()
    req = urllib.request.Request(f'{BASE}/auth/login', data=data,
        headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req, timeout=5)
    result = json.loads(resp.read())
    token = result.get('access_token', '')
    print(f'    Login OK, token: {token[:30]}...')
except Exception as e:
    print(f'    Login EXC: {e}')
    exit(1)

headers_auth = {'Authorization': f'Bearer {token}'}

# 2. Upload garment
print('[2] Upload garment...')
try:
    # 创建最小 JPEG 图片
    img_data = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07'
        b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
        b'\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xff\xc4\x00\x14\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xff\xc4\x00\x14\x11\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9'
    )

    boundary = '----WebKitFormBoundary7MA4YWfX'
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="test.jpg"\r\n'
        f'Content-Type: image/jpeg\r\n\r\n'
    ).encode() + img_data + f'\r\n--{boundary}--\r\n'.encode()

    req = urllib.request.Request(
        f'{BASE}/wardrobe/simple/garments',
        data=body,
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        },
        method='POST'
    )
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    print(f'    Upload OK: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}')
except urllib.error.HTTPError as e:
    body = e.read()
    print(f'    HTTP {e.code}: {body[:300]}')
except Exception as e:
    print(f'    EXC: {type(e).__name__}: {e}')

# 3. Get garments
print('[3] Get garments...')
try:
    req = urllib.request.Request(f'{BASE}/wardrobe/simple/garments',
        headers=headers_auth)
    resp = urllib.request.urlopen(req, timeout=5)
    result = json.loads(resp.read())
    print(f'    Got garments: {json.dumps(result, indent=2, ensure_ascii=False)[:500]}')
except urllib.error.HTTPError as e:
    print(f'    HTTP {e.code}: {e.read()[:300]}')
except Exception as e:
    print(f'    EXC: {type(e).__name__}: {e}')
