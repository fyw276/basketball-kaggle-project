# API 使用示例

本文档提供智能穿搭助手 API 的实际使用示例，包括 curl 命令、Python 代码和 JavaScript 代码。

## 目录

1. [认证流程](#认证流程)
2. [用户画像管理](#用户画像管理)
3. [图像识别](#图像识别)
4. [衣橱管理](#衣橱管理)
5. [智能分析](#智能分析)

---

## 认证流程

### 1. 注册新用户

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "fashionista",
    "email": "fashionista@example.com",
    "password": "SecurePass123"
  }'
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/auth/register"
data = {
    "username": "fashionista",
    "email": "fashionista@example.com",
    "password": "SecurePass123"
}

response = requests.post(url, json=data)
print(response.json())
```

**JavaScript (fetch)**:
```javascript
const url = 'http://localhost:8000/api/v1/auth/register';
const data = {
  username: 'fashionista',
  email: 'fashionista@example.com',
  password: 'SecurePass123'
};

fetch(url, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify(data)
})
  .then(response => response.json())
  .then(data => console.log(data));
```

**响应示例**:
```json
{
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "username": "fashionista",
  "email": "fashionista@example.com",
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z"
}
```

---

### 2. 用户登录

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "fashionista",
    "password": "SecurePass123"
  }'
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/auth/login"
data = {
    "username": "fashionista",
    "password": "SecurePass123"
}

response = requests.post(url, json=data)
token_data = response.json()
access_token = token_data["access_token"]

print(f"Access Token: {access_token}")
```

**响应示例**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjNlNDU2Ny1lODliLTEyZDMtYTQ1Ni00MjY2MTQxNzQwMDAiLCJ1c2VybmFtZSI6ImZhc2hpb25pc3RhIiwiZXhwIjoxNzA0MTg3MjAwfQ.abc123...",
  "token_type": "bearer"
}
```

---

## 用户画像管理

### 3. 创建用户画像

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "height": 168,
    "body_type": "沙漏型",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约", "优雅"],
    "budget_range": "中档",
    "avoid_body_parts": ["肩部"]
  }'
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/profile"
headers = {
    "Authorization": f"Bearer {access_token}"
}
data = {
    "height": 168,
    "body_type": "沙漏型",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约", "优雅"],
    "budget_range": "中档",
    "avoid_body_parts": ["肩部"]
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

---

### 4. 获取用户画像

**curl**:
```bash
curl -X GET "http://localhost:8000/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/profile"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.get(url, headers=headers)
profile = response.json()
print(f"Body Type: {profile['body_type']}")
print(f"Style Preference: {profile['style_preference']}")
```

---

### 5. 更新用户画像

**curl**:
```bash
curl -X PUT "http://localhost:8000/api/v1/profile" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "style_preference": ["通勤", "简约", "优雅", "休闲"],
    "budget_range": "高档"
  }'
```

---

## 图像识别

### 6. 品类识别

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/recognition/category" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/recognition/category"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()
print(f"Category: {result['category']}")
print(f"Confidence: {result['confidence']:.2%}")
```

**JavaScript (FormData)**:
```javascript
const url = 'http://localhost:8000/api/v1/recognition/category';
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch(url, {
  method: 'POST',
  body: formData
})
  .then(response => response.json())
  .then(data => {
    console.log(`Category: ${data.category}`);
    console.log(`Confidence: ${data.confidence}`);
  });
```

---

### 7. 颜色识别

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/recognition/colors" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/recognition/colors"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()

main_color = result["main_color"]
print(f"Main Color: {main_color['name']}")
print(f"RGB: {main_color['rgb']}")
print(f"Hex: {main_color['hex_code']}")

for i, color in enumerate(result["secondary_colors"], 1):
    print(f"Secondary Color {i}: {color['name']} ({color['hex_code']})")
```

---

### 8. 完整图像分析

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/recognition/analyze" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/recognition/analyze"
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}

response = requests.post(url, files=files)
result = response.json()

print(f"Category: {result['category']} (confidence: {result['category_confidence']:.2%})")
print(f"Main Color: {result['main_color']['name']}")
print(f"Style Tags: {', '.join(result['style_tags'])}")
print(f"Feature Vector Length: {len(result['feature_vector'])}")
```

---

## 衣橱管理

### 9. 添加服饰到衣橱

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/wardrobe/garments" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/shirt.jpg" \
  -F "category=上衣" \
  -F "main_color_name=蓝" \
  -F "main_color_rgb=52,120,180" \
  -F "main_color_hsv=210.0,71.1,70.6" \
  -F "main_color_hex=#3478b4" \
  -F "style_tags=通勤,简约" \
  -F "fit_type=合身" \
  -F "notes=蓝色衬衫，适合工作日穿着"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/wardrobe/garments"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}
data = {
    "category": "上衣",
    "main_color_name": "蓝",
    "main_color_rgb": "52,120,180",
    "main_color_hsv": "210.0,71.1,70.6",
    "main_color_hex": "#3478b4",
    "style_tags": "通勤,简约",
    "fit_type": "合身",
    "notes": "蓝色衬衫，适合工作日穿着"
}

response = requests.post(url, files=files, data=data, headers=headers)
garment = response.json()
print(f"Garment ID: {garment['garment_id']}")
```

---

### 10. 查询衣橱列表

**curl**:
```bash
# 获取所有服饰（第1页）
curl -X GET "http://localhost:8000/api/v1/wardrobe/garments?page=1&page_size=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"

# 按品类筛选
curl -X GET "http://localhost:8000/api/v1/wardrobe/garments?category=上衣" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/wardrobe/garments"
headers = {
    "Authorization": f"Bearer {access_token}"
}
params = {
    "page": 1,
    "page_size": 20,
    "category": "上衣"  # 可选筛选
}

response = requests.get(url, headers=headers, params=params)
result = response.json()

print(f"Total garments: {result['total']}")
print(f"Page {result['page']} of {result['total'] // result['page_size'] + 1}")

for garment in result["items"]:
    print(f"- {garment['category']}: {garment['main_color']['name']}")
```

---

### 11. 获取单个服饰详情

**curl**:
```bash
curl -X GET "http://localhost:8000/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://localhost:8000/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.get(url, headers=headers)
garment = response.json()
print(f"Category: {garment['category']}")
print(f"Color: {garment['main_color']['name']}")
print(f"Styles: {', '.join(garment['style_tags'])}")
```

---

### 12. 更新服饰信息

**curl**:
```bash
curl -X PUT "http://localhost:8000/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "style_tags": ["通勤", "简约", "优雅"],
    "fit_type": "宽松",
    "notes": "更新后的备注"
  }'
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://localhost:8000/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}
data = {
    "style_tags": ["通勤", "简约", "优雅"],
    "fit_type": "宽松",
    "notes": "更新后的备注"
}

response = requests.put(url, json=data, headers=headers)
updated_garment = response.json()
print("Garment updated successfully")
```

---

### 13. 删除服饰

**curl**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/wardrobe/garments/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Python**:
```python
import requests

garment_id = "123e4567-e89b-12d3-a456-426614174000"
url = f"http://localhost:8000/api/v1/wardrobe/garments/{garment_id}"
headers = {
    "Authorization": f"Bearer {access_token}"
}

response = requests.delete(url, headers=headers)
if response.status_code == 204:
    print("Garment deleted successfully")
```

---

## 智能分析

### 14. 相似度分析

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/analysis/similarity" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/new_shirt.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/analysis/similarity"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/new_shirt.jpg", "rb")
}

response = requests.post(url, files=files, headers=headers)
result = response.json()

print(f"Target: {result['target_garment']['category']}")
print(f"Similar garments found: {len(result['similar_garments'])}")
print(f"Duplicate warning: {result['has_duplicate_warning']}")
print(f"Recommendation: {result['recommendation']}")

for garment in result["similar_garments"]:
    print(f"- Similarity: {garment['similarity_score']:.2%} ({garment['similarity_level']})")
```

---

### 15. 搭配推荐

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/analysis/outfits?num_outfits=3" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/shirt.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/analysis/outfits"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/shirt.jpg", "rb")
}
params = {
    "num_outfits": 3
}

response = requests.post(url, files=files, headers=headers, params=params)
result = response.json()

print(f"Target: {result['target_garment']['category']}")
print(f"Generated {len(result['outfit_cards'])} outfit recommendations:")

for i, outfit in enumerate(result["outfit_cards"], 1):
    print(f"\nOutfit {i}:")
    print(f"  Occasion: {outfit['occasion']}")
    print(f"  Description: {outfit['description']}")
    print(f"  Overall Score: {outfit['overall_score']:.2%}")
    print(f"  Items: {len(outfit['items'])}")
```

---

### 16. 适合度评分

**curl**:
```bash
curl -X POST "http://localhost:8000/api/v1/analysis/suitability" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -F "file=@/path/to/dress.jpg"
```

**Python**:
```python
import requests

url = "http://localhost:8000/api/v1/analysis/suitability"
headers = {
    "Authorization": f"Bearer {access_token}"
}
files = {
    "file": open("/path/to/dress.jpg", "rb")
}

response = requests.post(url, files=files, headers=headers)
result = response.json()

print(f"Overall Suitability: {result['suitability_score']}/100")
print(f"Color Score: {result['color_score']}/100")
print(f"Fit Score: {result['fit_score']}/100")
print(f"Style Score: {result['style_score']}/100")

print("\nExplanations:")
for key, explanation in result["explanation"].items():
    print(f"  {key}: {explanation}")

print(f"\nRecommended Occasions: {', '.join(result['recommended_occasions'])}")

print("\nSuggestions:")
for suggestion in result["suggestions"]:
    print(f"  - {suggestion}")
```

---

## 完整工作流示例

### Python 完整示例：从注册到分析

```python
import requests
import time

BASE_URL = "http://localhost:8000/api/v1"

# 1. 注册用户
print("1. Registering user...")
register_data = {
    "username": "demo_user",
    "email": "demo@example.com",
    "password": "DemoPass123"
}
response = requests.post(f"{BASE_URL}/auth/register", json=register_data)
user = response.json()
print(f"   User created: {user['username']}")

# 2. 登录获取 Token
print("\n2. Logging in...")
login_data = {
    "username": "demo_user",
    "password": "DemoPass123"
}
response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("   Login successful")

# 3. 创建用户画像
print("\n3. Creating user profile...")
profile_data = {
    "height": 170,
    "body_type": "沙漏型",
    "skin_tone": "冷白",
    "style_preference": ["通勤", "简约"],
    "budget_range": "中档"
}
response = requests.post(f"{BASE_URL}/profile", json=profile_data, headers=headers)
print("   Profile created")

# 4. 图像识别
print("\n4. Analyzing image...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/recognition/analyze", files=files)
result = response.json()
print(f"   Category: {result['category']}")
print(f"   Color: {result['main_color']['name']}")
print(f"   Styles: {', '.join(result['style_tags'])}")

# 5. 添加到衣橱
print("\n5. Adding to wardrobe...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    data = {
        "category": result["category"],
        "main_color_name": result["main_color"]["name"],
        "main_color_rgb": ",".join(map(str, result["main_color"]["rgb"])),
        "main_color_hsv": ",".join(map(str, result["main_color"]["hsv"])),
        "main_color_hex": result["main_color"]["hex_code"],
        "style_tags": ",".join(result["style_tags"])
    }
    response = requests.post(f"{BASE_URL}/wardrobe/garments", files=files, data=data, headers=headers)
garment = response.json()
print(f"   Garment added: {garment['garment_id']}")

# 6. 相似度分析
print("\n6. Analyzing similarity...")
with open("/path/to/another_shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/similarity", files=files, headers=headers)
similarity = response.json()
print(f"   Similar items: {len(similarity['similar_garments'])}")
print(f"   Recommendation: {similarity['recommendation']}")

# 7. 搭配推荐
print("\n7. Getting outfit recommendations...")
with open("/path/to/shirt.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/outfits?num_outfits=3", files=files, headers=headers)
outfits = response.json()
print(f"   Generated {len(outfits['outfit_cards'])} outfits")

# 8. 适合度评分
print("\n8. Calculating suitability score...")
with open("/path/to/dress.jpg", "rb") as f:
    files = {"file": f}
    response = requests.post(f"{BASE_URL}/analysis/suitability", files=files, headers=headers)
suitability = response.json()
print(f"   Overall score: {suitability['suitability_score']}/100")

print("\n✓ Complete workflow finished successfully!")
```

---

## 错误处理示例

### Python 错误处理

```python
import requests

def make_api_request(url, method="GET", **kwargs):
    """
    Make API request with error handling
    """
    try:
        if method == "GET":
            response = requests.get(url, **kwargs)
        elif method == "POST":
            response = requests.post(url, **kwargs)
        elif method == "PUT":
            response = requests.put(url, **kwargs)
        elif method == "DELETE":
            response = requests.delete(url, **kwargs)

        # Raise exception for bad status codes
        response.raise_for_status()

        # Return JSON if available
        if response.status_code != 204:  # No Content
            return response.json()
        return None

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors
        if e.response.status_code == 400:
            print(f"Bad Request: {e.response.json()}")
        elif e.response.status_code == 401:
            print("Unauthorized: Please login again")
        elif e.response.status_code == 403:
            print("Forbidden: You don't have permission")
        elif e.response.status_code == 404:
            print("Not Found: Resource doesn't exist")
        elif e.response.status_code == 422:
            print(f"Validation Error: {e.response.json()}")
        elif e.response.status_code == 500:
            print("Server Error: Please try again later")
        raise

    except requests.exceptions.ConnectionError:
        print("Connection Error: Cannot reach the server")
        raise

    except requests.exceptions.Timeout:
        print("Timeout: Request took too long")
        raise

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        raise

# Usage
try:
    result = make_api_request(
        "http://localhost:8000/api/v1/profile",
        method="GET",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(result)
except Exception as e:
    print(f"Failed to get profile: {e}")
```

---

## 性能测试示例

### Python 性能测试

```python
import requests
import time

def test_api_performance(url, files=None, headers=None):
    """
    Test API endpoint performance
    """
    start_time = time.time()

    if files:
        response = requests.post(url, files=files, headers=headers)
    else:
        response = requests.get(url, headers=headers)

    elapsed_time = time.time() - start_time

    print(f"Endpoint: {url}")
    print(f"Status: {response.status_code}")
    print(f"Response Time: {elapsed_time:.3f}s")

    return elapsed_time

# Test image recognition performance
with open("/path/to/test_image.jpg", "rb") as f:
    files = {"file": f}
    elapsed = test_api_performance(
        "http://localhost:8000/api/v1/recognition/analyze",
        files=files
    )

    if elapsed < 2.0:
        print("✓ Performance requirement met (< 2s)")
    else:
        print("✗ Performance requirement not met")
```

---

## 注意事项

1. **Token 管理**: Access Token 有效期为 24 小时，过期后需要重新登录
2. **文件上传**: 支持 JPEG, PNG, WebP 格式，建议文件大小 < 10MB
3. **并发限制**: 建议单用户并发请求不超过 10 个
4. **错误重试**: 遇到 500 错误时，建议使用指数退避策略重试
5. **图片质量**: 为获得最佳识别效果，建议上传清晰、光线充足的图片

---

## 更多资源

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json
