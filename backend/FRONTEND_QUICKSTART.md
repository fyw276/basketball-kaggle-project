# 前端开发快速入门指南

本指南帮助前端开发者快速接入智能穿搭助手 API。

---

## 📋 前置准备

### 1. 确保后端服务运行

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000/docs 确认 API 文档可访问。

### 2. 阅读 API 文档

- **Swagger UI**: http://localhost:8000/docs （交互式测试）
- **ReDoc**: http://localhost:8000/redoc （详细文档）
- **API 规范**: `backend/API_SPECIFICATION.md`
- **API 契约**: `backend/API_CONTRACT_v1.0.md`

### 3. 导入 Postman 集合（可选）

导入 `backend/postman_collection.json` 到 Postman 进行 API 测试。

---

## 🚀 快速开始

### TypeScript 类型定义

创建 `src/types/api.ts`:

```typescript
// 基础类型
export interface ColorSchema {
  name: string;
  rgb: [number, number, number];
  hsv: [number, number, number];
  hex_code: string;
}

export interface User {
  user_id: string;
  username: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface UserProfile {
  profile_id: string;
  user_id: string;
  height: number | null;
  body_type: string | null;
  skin_tone: string | null;
  style_preference: string[];
  budget_range: string | null;
  avoid_body_parts: string[];
  created_at: string;
  updated_at: string;
}

export interface Garment {
  garment_id: string;
  user_id: string;
  category: string;
  main_color: ColorSchema;
  secondary_colors: ColorSchema[];
  style_tags: string[];
  fit_type: string | null;
  image_url: string;
  feature_vector: number[];
  notes: string | null;
  created_at: string;
}

export interface RecognitionResult {
  category: string;
  category_confidence: number;
  main_color: ColorSchema;
  secondary_colors: ColorSchema[];
  style_tags: string[];
  fit_type: string | null;
  feature_vector: number[];
  processing_time: number;
}

// API 响应类型
export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface GarmentListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Garment[];
}

export interface SimilarityAnalysisResponse {
  target_garment: RecognitionResult;
  similar_garments: Array<{
    garment_id: string;
    similarity_score: number;
    similarity_level: string;
    image_url: string;
    category: string;
    main_color: ColorSchema;
  }>;
  has_duplicate_warning: boolean;
  recommendation: string;
}

export interface OutfitCard {
  outfit_id: string;
  items: Array<{
    garment_id: string;
    category: string;
    image_url: string;
    role: string;
  }>;
  occasion: string;
  description: string;
  color_harmony: string;
  color_harmony_score: number;
  style_consistency: number;
  overall_score: number;
}

export interface SuitabilityAnalysisResponse {
  garment: RecognitionResult;
  suitability_score: number;
  color_score: number;
  fit_score: number;
  style_score: number;
  explanation: {
    color: string;
    fit: string;
    style: string;
  };
  recommended_occasions: string[];
  suggestions: string[];
}

// 错误响应
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: any;
  };
}
```

---

### API 客户端封装

创建 `src/services/api.ts`:

```typescript
import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  LoginResponse,
  User,
  UserProfile,
  Garment,
  GarmentListResponse,
  RecognitionResult,
  SimilarityAnalysisResponse,
  OutfitCard,
  SuitabilityAnalysisResponse,
  ApiError
} from '../types/api';

class ApiClient {
  private client: AxiosInstance;
  private accessToken: string | null = null;

  constructor(baseURL: string = 'http://localhost:8000/api/v1') {
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 请求拦截器：自动添加 Token
    this.client.interceptors.request.use((config) => {
      if (this.accessToken) {
        config.headers.Authorization = `Bearer ${this.accessToken}`;
      }
      return config;
    });

    // 响应拦截器：统一错误处理
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError<ApiError>) => {
        if (error.response) {
          const apiError = error.response.data;
          console.error('API Error:', apiError);

          // 401 错误：清除 Token
          if (error.response.status === 401) {
            this.clearToken();
          }
        }
        return Promise.reject(error);
      }
    );
  }

  // Token 管理
  setToken(token: string) {
    this.accessToken = token;
    localStorage.setItem('access_token', token);
  }

  getToken(): string | null {
    if (!this.accessToken) {
      this.accessToken = localStorage.getItem('access_token');
    }
    return this.accessToken;
  }

  clearToken() {
    this.accessToken = null;
    localStorage.removeItem('access_token');
  }

  // 认证 API
  async register(username: string, email: string, password: string): Promise<User> {
    const response = await this.client.post<User>('/auth/register', {
      username,
      email,
      password,
    });
    return response.data;
  }

  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>('/auth/login', {
      username,
      password,
    });
    this.setToken(response.data.access_token);
    return response.data;
  }

  logout() {
    this.clearToken();
  }

  // 用户画像 API
  async createProfile(profile: Partial<UserProfile>): Promise<UserProfile> {
    const response = await this.client.post<UserProfile>('/profile', profile);
    return response.data;
  }

  async getProfile(): Promise<UserProfile> {
    const response = await this.client.get<UserProfile>('/profile');
    return response.data;
  }

  async updateProfile(profile: Partial<UserProfile>): Promise<UserProfile> {
    const response = await this.client.put<UserProfile>('/profile', profile);
    return response.data;
  }

  // 图像识别 API
  async recognizeCategory(file: File): Promise<{ category: string; confidence: number; confidence_level: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post('/recognition/category', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async recognizeColors(file: File): Promise<{ main_color: any; secondary_colors: any[] }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post('/recognition/colors', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async analyzeImage(file: File): Promise<RecognitionResult> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post<RecognitionResult>('/recognition/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  // 衣橱管理 API
  async addGarment(file: File, data: {
    category: string;
    main_color_name: string;
    main_color_rgb: string;
    main_color_hsv: string;
    main_color_hex: string;
    style_tags?: string;
    fit_type?: string;
    notes?: string;
  }): Promise<Garment> {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(data).forEach(([key, value]) => {
      if (value !== undefined) {
        formData.append(key, value);
      }
    });

    const response = await this.client.post<Garment>('/wardrobe/garments', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async listGarments(params?: {
    page?: number;
    page_size?: number;
    category?: string;
  }): Promise<GarmentListResponse> {
    const response = await this.client.get<GarmentListResponse>('/wardrobe/garments', { params });
    return response.data;
  }

  async getGarment(garmentId: string): Promise<Garment> {
    const response = await this.client.get<Garment>(`/wardrobe/garments/${garmentId}`);
    return response.data;
  }

  async updateGarment(garmentId: string, data: Partial<Garment>): Promise<Garment> {
    const response = await this.client.put<Garment>(`/wardrobe/garments/${garmentId}`, data);
    return response.data;
  }

  async deleteGarment(garmentId: string): Promise<void> {
    await this.client.delete(`/wardrobe/garments/${garmentId}`);
  }

  // 智能分析 API
  async analyzeSimilarity(file: File): Promise<SimilarityAnalysisResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post<SimilarityAnalysisResponse>('/analysis/similarity', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async recommendOutfits(
    fileOrFiles: File | File[],
    numOutfits: number = 3,
  ): Promise<{ target_garment: RecognitionResult; outfit_cards: OutfitCard[] }> {
    const formData = new FormData();
    if (Array.isArray(fileOrFiles)) {
      fileOrFiles.forEach((f) => formData.append('files', f));
    } else {
      formData.append('file', fileOrFiles);
    }

    const response = await this.client.post(`/analysis/outfits?num_outfits=${numOutfits}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }

  async analyzeSuitability(file: File): Promise<SuitabilityAnalysisResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await this.client.post<SuitabilityAnalysisResponse>('/analysis/suitability', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  }
}

// 导出单例
export const apiClient = new ApiClient();
export default apiClient;
```

---

### React 使用示例

#### 1. 登录组件

```tsx
import React, { useState } from 'react';
import { apiClient } from '../services/api';

export const LoginForm: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await apiClient.login(username, password);
      // 登录成功，跳转到主页
      window.location.href = '/dashboard';
    } catch (err: any) {
      setError(err.response?.data?.error?.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleLogin}>
      <input
        type="text"
        placeholder="用户名"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        required
      />
      <input
        type="password"
        placeholder="密码"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />
      {error && <div className="error">{error}</div>}
      <button type="submit" disabled={loading}>
        {loading ? '登录中...' : '登录'}
      </button>
    </form>
  );
};
```

#### 2. 图片上传识别组件

```tsx
import React, { useState } from 'react';
import { apiClient } from '../services/api';
import type { RecognitionResult } from '../types/api';

export const ImageRecognition: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleAnalyze = async () => {
    if (!file) return;

    setLoading(true);
    try {
      const result = await apiClient.analyzeImage(file);
      setResult(result);
    } catch (err) {
      console.error('识别失败:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input type="file" accept="image/*" onChange={handleFileChange} />
      <button onClick={handleAnalyze} disabled={!file || loading}>
        {loading ? '识别中...' : '开始识别'}
      </button>

      {result && (
        <div className="result">
          <h3>识别结果</h3>
          <p>品类: {result.category} ({(result.category_confidence * 100).toFixed(1)}%)</p>
          <p>主色: {result.main_color.name} ({result.main_color.hex_code})</p>
          <p>风格: {result.style_tags.join(', ')}</p>
          <p>处理时间: {result.processing_time.toFixed(2)}秒</p>
        </div>
      )}
    </div>
  );
};
```

#### 3. 衣橱列表组件

```tsx
import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/api';
import type { Garment } from '../types/api';

export const WardrobeList: React.FC = () => {
  const [garments, setGarments] = useState<Garment[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    loadGarments();
  }, [page]);

  const loadGarments = async () => {
    setLoading(true);
    try {
      const response = await apiClient.listGarments({ page, page_size: 20 });
      setGarments(response.items);
      setTotal(response.total);
    } catch (err) {
      console.error('加载失败:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (garmentId: string) => {
    if (!confirm('确定要删除这件服饰吗？')) return;

    try {
      await apiClient.deleteGarment(garmentId);
      loadGarments(); // 重新加载列表
    } catch (err) {
      console.error('删除失败:', err);
    }
  };

  if (loading) return <div>加载中...</div>;

  return (
    <div>
      <h2>我的衣橱 ({total} 件)</h2>
      <div className="garment-grid">
        {garments.map((garment) => (
          <div key={garment.garment_id} className="garment-card">
            <img src={garment.image_url} alt={garment.category} />
            <h3>{garment.category}</h3>
            <p>{garment.main_color.name}</p>
            <p>{garment.style_tags.join(', ')}</p>
            <button onClick={() => handleDelete(garment.garment_id)}>删除</button>
          </div>
        ))}
      </div>

      <div className="pagination">
        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
          上一页
        </button>
        <span>第 {page} 页</span>
        <button onClick={() => setPage(p => p + 1)} disabled={page * 20 >= total}>
          下一页
        </button>
      </div>
    </div>
  );
};
```

---

### Vue 使用示例

#### Composable (Vue 3)

```typescript
// src/composables/useApi.ts
import { ref } from 'vue';
import { apiClient } from '../services/api';
import type { Garment, RecognitionResult } from '../types/api';

export function useWardrobe() {
  const garments = ref<Garment[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const loadGarments = async (page: number = 1, pageSize: number = 20) => {
    loading.value = true;
    error.value = null;

    try {
      const response = await apiClient.listGarments({ page, page_size: pageSize });
      garments.value = response.items;
      return response;
    } catch (err: any) {
      error.value = err.message;
      throw err;
    } finally {
      loading.value = false;
    }
  };

  const deleteGarment = async (garmentId: string) => {
    try {
      await apiClient.deleteGarment(garmentId);
      garments.value = garments.value.filter(g => g.garment_id !== garmentId);
    } catch (err: any) {
      error.value = err.message;
      throw err;
    }
  };

  return {
    garments,
    loading,
    error,
    loadGarments,
    deleteGarment,
  };
}

export function useImageRecognition() {
  const result = ref<RecognitionResult | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const analyzeImage = async (file: File) => {
    loading.value = true;
    error.value = null;

    try {
      result.value = await apiClient.analyzeImage(file);
      return result.value;
    } catch (err: any) {
      error.value = err.message;
      throw err;
    } finally {
      loading.value = false;
    }
  };

  return {
    result,
    loading,
    error,
    analyzeImage,
  };
}
```

---

## 🔐 认证流程

### 完整认证流程

```typescript
// 1. 注册
await apiClient.register('username', 'email@example.com', 'password');

// 2. 登录（自动保存 Token）
await apiClient.login('username', 'password');

// 3. 后续请求自动携带 Token
const profile = await apiClient.getProfile();

// 4. 登出
apiClient.logout();
```

### Token 持久化

Token 自动保存在 `localStorage`，页面刷新后自动恢复：

```typescript
// 应用启动时检查 Token
const token = apiClient.getToken();
if (token) {
  // 用户已登录
  // 可以尝试获取用户信息验证 Token 有效性
  try {
    await apiClient.getProfile();
  } catch (err) {
    // Token 无效，清除并跳转到登录页
    apiClient.clearToken();
    window.location.href = '/login';
  }
}
```

---

## 📱 移动端注意事项

### Flutter/React Native

使用相同的 API 端点，但需要注意：

1. **图片上传**: 使用平台特定的文件选择器
2. **Token 存储**: 使用 SecureStorage 而非 localStorage
3. **网络请求**: 使用 dio (Flutter) 或 axios (React Native)

### Flutter 示例

```dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ApiClient {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:8000/api/v1',
  ));
  final _storage = FlutterSecureStorage();

  Future<void> login(String username, String password) async {
    final response = await _dio.post('/auth/login', data: {
      'username': username,
      'password': password,
    });

    final token = response.data['access_token'];
    await _storage.write(key: 'access_token', value: token);

    // 设置默认 header
    _dio.options.headers['Authorization'] = 'Bearer $token';
  }

  Future<void> analyzeImage(File imageFile) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(imageFile.path),
    });

    final response = await _dio.post('/recognition/analyze', data: formData);
    return response.data;
  }
}
```

---

## 🐛 错误处理最佳实践

```typescript
async function handleApiCall<T>(
  apiCall: () => Promise<T>,
  errorMessage: string = '操作失败'
): Promise<T | null> {
  try {
    return await apiCall();
  } catch (error: any) {
    if (error.response) {
      // API 返回的错误
      const apiError = error.response.data?.error;
      console.error(`${errorMessage}:`, apiError?.message || error.message);

      // 根据错误码处理
      switch (error.response.status) {
        case 401:
          // 未认证，跳转登录
          apiClient.clearToken();
          window.location.href = '/login';
          break;
        case 403:
          alert('您没有权限执行此操作');
          break;
        case 404:
          alert('资源不存在');
          break;
        case 422:
          alert('数据验证失败，请检查输入');
          break;
        default:
          alert(apiError?.message || errorMessage);
      }
    } else if (error.request) {
      // 网络错误
      console.error('网络错误:', error.message);
      alert('网络连接失败，请检查网络设置');
    } else {
      // 其他错误
      console.error('错误:', error.message);
      alert(errorMessage);
    }
    return null;
  }
}

// 使用示例
const garments = await handleApiCall(
  () => apiClient.listGarments(),
  '加载衣橱失败'
);
```

---

## 📊 性能优化建议

### 1. 图片压缩

上传前压缩图片以提高速度：

```typescript
async function compressImage(file: File, maxWidth: number = 1024): Promise<File> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        let width = img.width;
        let height = img.height;

        if (width > maxWidth) {
          height = (height * maxWidth) / width;
          width = maxWidth;
        }

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(img, 0, 0, width, height);

        canvas.toBlob((blob) => {
          resolve(new File([blob!], file.name, { type: 'image/jpeg' }));
        }, 'image/jpeg', 0.8);
      };
      img.src = e.target!.result as string;
    };
    reader.readAsDataURL(file);
  });
}
```

### 2. 请求缓存

缓存不常变化的数据：

```typescript
const cache = new Map<string, { data: any; timestamp: number }>();

async function cachedApiCall<T>(
  key: string,
  apiCall: () => Promise<T>,
  ttl: number = 5 * 60 * 1000 // 5分钟
): Promise<T> {
  const cached = cache.get(key);
  if (cached && Date.now() - cached.timestamp < ttl) {
    return cached.data;
  }

  const data = await apiCall();
  cache.set(key, { data, timestamp: Date.now() });
  return data;
}

// 使用示例
const profile = await cachedApiCall(
  'user-profile',
  () => apiClient.getProfile()
);
```

### 3. 分页加载

使用虚拟滚动或无限滚动优化大列表：

```typescript
const [garments, setGarments] = useState<Garment[]>([]);
const [page, setPage] = useState(1);
const [hasMore, setHasMore] = useState(true);

const loadMore = async () => {
  const response = await apiClient.listGarments({ page, page_size: 20 });
  setGarments(prev => [...prev, ...response.items]);
  setHasMore(response.items.length === 20);
  setPage(p => p + 1);
};
```

---

## 🧪 测试建议

### 单元测试示例 (Jest)

```typescript
import { apiClient } from '../services/api';
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

describe('ApiClient', () => {
  it('should login successfully', async () => {
    const mockResponse = {
      data: {
        access_token: 'test-token',
        token_type: 'bearer',
      },
    };
    mockedAxios.post.mockResolvedValue(mockResponse);

    const result = await apiClient.login('testuser', 'password');

    expect(result.access_token).toBe('test-token');
    expect(apiClient.getToken()).toBe('test-token');
  });
});
```

---

## 📚 更多资源

- **API 完整规范**: `backend/API_SPECIFICATION.md`
- **API 使用示例**: `backend/API_EXAMPLES.md`
- **API 契约**: `backend/API_CONTRACT_v1.0.md`
- **Postman 集合**: `backend/postman_collection.json`
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 💬 获取帮助

遇到问题？

1. 查看 Swagger UI 的交互式文档
2. 检查浏览器控制台的网络请求
3. 查看后端日志 `backend/logs/app.log`
4. 联系后端团队: support@smartoutfit.example.com

---

祝开发顺利！🎉
