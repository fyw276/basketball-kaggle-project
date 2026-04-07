# Smart Outfit Assistant - 椤圭洰杩涘害

## 椤圭洰姒傝堪

鏅鸿兘绌挎惌鍔╂墜 - 鍩轰簬澶氭ā鎬佹帹鑽愪笌杞婚噺鍖栨帹鐞嗙殑绌挎惌鍐崇瓥绯荤粺

**鎶€鏈爤**: FastAPI + PostgreSQL + Redis + MobileNetV2 + Flutter

## 宸插畬鎴愭ā鍧?鉁?
### 1. 椤圭洰鍒濆鍖栦笌鍩虹璁炬柦鎼缓 鉁?- 鉁?鍒涘缓瀹屾暣鐨勯」鐩洰褰曠粨鏋?- 鉁?閰嶇疆 Python 铏氭嫙鐜鍜屼緷璧栫鐞?- 鉁?鍒濆鍖?FastAPI 椤圭洰妗嗘灦
- 鉁?閰嶇疆寮€鍙戠幆澧冿紙Git hooks, pre-commit, black, isort, flake8锛?- 鉁?閰嶇疆 Conventional Commits

### 2. 鏁版嵁搴撹璁′笌鍒濆鍖?鉁?- 鉁?璁捐 PostgreSQL 鏁版嵁搴撴ā寮忥紙users, user_profiles, garments锛?- 鉁?瀹炵幇 SQLAlchemy ORM 妯″瀷
- 鉁?閰嶇疆鏁版嵁搴撹繛鎺ュ拰浼氳瘽绠＄悊
- 鉁?閰嶇疆 Alembic 鏁版嵁搴撹縼绉?- 鉁?閰嶇疆 Redis 缂撳瓨灞?- 鉁?鍒涘缓鏁版嵁搴撳垵濮嬪寲鑴氭湰

### 3. 鐢ㄦ埛璁よ瘉涓庢巿鏉冩ā鍧?鉁?- 鉁?瀹炵幇鐢ㄦ埛娉ㄥ唽鍔熻兘锛堝瘑鐮?bcrypt 鍔犲瘑锛?- 鉁?瀹炵幇鐢ㄦ埛鐧诲綍鍔熻兘锛圝WT Token锛?- 鉁?瀹炵幇 JWT Token 楠岃瘉涓棿浠?- 鉁?鍒涘缓鍙椾繚鎶ょ殑 API 绔偣
- 鉁?瀹炵幇鏉冮檺鎺у埗

### 4. 鐢ㄦ埛鐢诲儚绠＄悊妯″潡 鉁?- 鉁?瀹炵幇鐢ㄦ埛鐢诲儚鏁版嵁妯″瀷锛堣韩楂樸€佷綋鍨嬨€佽偆鑹层€侀鏍煎亸濂姐€侀绠楄寖鍥达級
- 鉁?瀹炵幇鐢ㄦ埛鐢诲儚 CRUD API
- 鉁?娣诲姞瀹屾暣鐨勬暟鎹獙璇佽鍒?- 鉁?纭繚鏉冮檺鎺у埗

### 5. 妫€鏌ョ偣 - 鍩虹璁炬柦楠岃瘉 鉁?- 鉁?鍒涘缓缁煎悎楠岃瘉鑴氭湰
- 鉁?娴嬭瘯鏁版嵁搴撱€丷edis銆佽璇佸姛鑳?- 鉁?鎻愪緵璇︾粏鐨勯獙璇佹枃妗ｅ拰鏁呴殰鎺掗櫎鎸囧崡

### 6. 鍥惧儚璇嗗埆妯″潡 - 妯″瀷鍑嗗 鉁?- 鉁?涓嬭浇鍜岄厤缃?MobileNetV2 棰勮缁冩ā鍨?- 鉁?瀹炵幇妯″瀷鍔犺浇鍑芥暟锛圡odelLoader锛?- 鉁?瀹炵幇鍥惧儚棰勫鐞嗘祦绋嬶紙ImagePreprocessor锛?  - 鍥惧儚璇诲彇鍜屾牸寮忚浆鎹?  - 鍥惧儚缂╂斁鍒?224x224
  - 褰掍竴鍖栧鐞嗭紙[-1, 1]锛?  - 鎵归噺棰勫鐞嗗嚱鏁?- 鉁?瀹炵幇鐗瑰緛鎻愬彇鍣紙FeatureExtractor锛?  - 1280 缁寸壒寰佸悜閲忔彁鍙?  - L2 褰掍竴鍖?  - 鎵归噺鐗瑰緛鎻愬彇
- 鉁?鍒涘缓娴嬭瘯鑴氭湰楠岃瘉鍔熻兘

### 7. 鍥惧儚璇嗗埆妯″潡 - 鍝佺被璇嗗埆 鉁?- 鉁?瀹氫箟 6 涓搧绫诲父閲忥紙涓婅。/瑁ゅ瓙/瑁欏瓙/澶栧/闉?鍖咃級
- 鉁?瀹炵幇 MobileNetV2 鍝佺被鍒嗙被澶达紙CategoryClassifier锛?- 鉁?瀹炵幇 classify_category 鍑芥暟
- 鉁?瀹炵幇缃俊搴﹂槇鍊煎鐞嗛€昏緫锛堥珮/涓?浣庣疆淇″害锛?- 鉁?鍒涘缓鍥剧墖涓婁紶绔偣锛圥OST /api/v1/recognition/category锛?- 鉁?闆嗘垚鍝佺被鍒嗙被鍣ㄥ埌 API
- 鉁?杩斿洖鍝佺被鍜岀疆淇″害
- 鉁?鍒涘缓娴嬭瘯鑴氭湰楠岃瘉鍔熻兘

### 8. 鍥惧儚璇嗗埆妯″潡 - 棰滆壊璇嗗埆 鉁?- 鉁?瀹炵幇 K-Means 棰滆壊鑱氱被锛圕olorExtractor锛?- 鉁?瀹炵幇涓昏壊鍜岃緟鍔╄壊鎻愬彇
- 鉁?瀹炵幇鏍囧噯鑹茬郴鏄犲皠锛?0 绉嶆爣鍑嗛鑹诧級
- 鉁?瀹炵幇 RGB/HSV/Hex 棰滆壊杞崲
- 鉁?鍒涘缓棰滆壊璇嗗埆绔偣锛圥OST /api/v1/recognition/colors锛?- 鉁?鍒涘缓娴嬭瘯鑴氭湰楠岃瘉鍔熻兘

### 9. 鍥惧儚璇嗗埆妯″潡 - 椋庢牸璇嗗埆 鉁?- 鉁?瀹氫箟 12 涓鏍兼爣绛惧父閲?- 鉁?瀹炵幇 MobileNetV2 椋庢牸鍒嗙被澶达紙StyleClassifier锛?- 鉁?瀹炵幇澶氭爣绛惧垎绫伙紙Sigmoid 婵€娲伙級
- 鉁?瀹炵幇缃俊搴﹂槇鍊艰繃婊?- 鉁?鍒涘缓娴嬭瘯鑴氭湰楠岃瘉鍔熻兘

### 10. 鍥惧儚璇嗗埆妯″潡 - 瀹屾暣娴佺▼闆嗘垚 鉁?- 鉁?瀹炵幇 ImageRecognizer 绫婚泦鎴愭墍鏈夎瘑鍒ā鍧?- 鉁?瀹炵幇 recognize() 鏂规硶杩斿洖 RecognitionResult
- 鉁?瀹炵幇鎵归噺璇嗗埆 recognize_batch() 鏂规硶
- 鉁?瀹炵幇瀹屾暣璇嗗埆 API 绔偣锛圥OST /api/v1/recognition/analyze锛?- 鉁?瀹炵幇閿欒澶勭悊鍜屾棩蹇楄褰?- 鉁?鎬ц兘楠岃瘉锛? 2 绉掓瘡寮犲浘鐗囷級
- 鉁?鍒涘缓娴嬭瘯鑴氭湰楠岃瘉鍔熻兘

### 11. 琛ｆ┍绠＄悊妯″潡 鉁?- 鉁?瀹炵幇 Garment 鏁版嵁妯″瀷锛堝搧绫汇€侀鑹层€侀鏍笺€佺増鍨嬶級
- 鉁?瀹炵幇鍥剧墖瀛樺偍鏈嶅姟
- 鉁?瀹炵幇娣诲姞鏈嶉グ API
- 鉁?瀹炵幇鏌ヨ琛ｆ┍ API锛堝垎椤点€佺瓫閫夛級
- 鉁?瀹炵幇鍒犻櫎鍜岀紪杈戞湇楗?API
- 鉁?瀹炵幇鏉冮檺鎺у埗

## 褰撳墠 API 绔偣

### 璁よ瘉 (Authentication)
- `POST /api/v1/auth/register` - 鐢ㄦ埛娉ㄥ唽
- `POST /api/v1/auth/login` - 鐢ㄦ埛鐧诲綍

### 鐢ㄦ埛 (Users)
- `GET /api/v1/users/me` - 鑾峰彇褰撳墠鐢ㄦ埛淇℃伅

### 鐢ㄦ埛鐢诲儚 (Profile)
- `POST /api/v1/profile` - 鍒涘缓鐢ㄦ埛鐢诲儚
- `GET /api/v1/profile` - 鑾峰彇鐢ㄦ埛鐢诲儚
- `PUT /api/v1/profile` - 鏇存柊鐢ㄦ埛鐢诲儚

### 琛ｆ┍绠＄悊 (Wardrobe)
- `POST /api/v1/wardrobe/garments` - 娣诲姞鏈嶉グ
- `GET /api/v1/wardrobe/garments` - 鍒楄〃鏌ヨ锛堝垎椤点€佺瓫閫夛級
- `GET /api/v1/wardrobe/garments/{id}` - 鑾峰彇鏈嶉グ璇︽儏
- `PUT /api/v1/wardrobe/garments/{id}` - 鏇存柊鏈嶉グ
- `DELETE /api/v1/wardrobe/garments/{id}` - 鍒犻櫎鏈嶉グ

### 绯荤粺 (System)
- `GET /` - 鏍圭鐐?- `GET /health` - 鍋ュ悍妫€鏌?- `GET /docs` - Swagger UI 鏂囨。
- `GET /redoc` - ReDoc 鏂囨。

### 鍥惧儚璇嗗埆 (Recognition)
- `POST /api/v1/recognition/category` - 璇嗗埆鏈嶉グ鍝佺被
- `GET /api/v1/recognition/categories` - 鑾峰彇鍙敤鍝佺被鍒楄〃
- `POST /api/v1/recognition/colors` - 鎻愬彇鏈嶉グ棰滆壊
- `POST /api/v1/recognition/analyze` - 瀹屾暣鍥惧儚璇嗗埆鍒嗘瀽锛堝搧绫?棰滆壊+椋庢牸+鐗瑰緛锛?
## 寰呭疄鐜版ā鍧?馃毀

### 12. 妫€鏌ョ偣 - 鍥惧儚璇嗗埆妯″潡楠岃瘉 鈴?
### 13. 鐩镐技搴﹀垎鏋愭ā鍧?鈴?- 鈴?瀹炵幇浣欏鸡鐩镐技搴﹁绠?- 鈴?瀹炵幇鐩镐技搴﹀垎绾ч€昏緫
- 鈴?瀹炵幇鐩镐技搴﹀垎鏋?API
- 鈴?瀹炵幇閲嶅棰勮鍔熻兘

### 15-16. 鎼厤鎺ㄨ崘妯″潡 鈴?- 鈴?瀹炵幇棰滆壊鎼厤瑙勫垯
- 鈴?瀹炵幇椋庢牸涓€鑷存€ц鍒?- 鈴?瀹炵幇鍝佺被鎼厤瑙勫垯
- 鈴?瀹炵幇鎼厤鎺ㄨ崘鐢熸垚绠楁硶
- 鈴?瀹炵幇鎼厤鎺ㄨ崘 API

### 17. 妫€鏌ョ偣 - 鏍稿績涓氬姟閫昏緫楠岃瘉 鈴?
### 18. 閫傚悎搴﹁瘎鍒嗘ā鍧?鈴?- 鈴?瀹炵幇棰滆壊閫傚悎搴﹁瘎鍒?- 鈴?瀹炵幇鐗堝瀷閫傚悎搴﹁瘎鍒?- 鈴?瀹炵幇椋庢牸閫傚悎搴﹁瘎鍒?- 鈴?瀹炵幇缁煎悎璇勫垎璁＄畻
- 鈴?瀹炵幇鍦哄悎鎺ㄨ崘鍜屾敼杩涘缓璁?- 鈴?瀹炵幇閫傚悎搴﹁瘎鍒?API

### 19. API 鏂囨。涓庨敊璇鐞?鈴?- 鈴?閰嶇疆 OpenAPI 鏂囨。
- 鈴?瀹炵幇鏍囧噯鍖栭敊璇鐞?
### 20. 鎬ц兘浼樺寲涓庣紦瀛?鈴?- 鈴?瀹炵幇 Redis 缂撳瓨绛栫暐
- 鈴?瀹炵幇寮傛澶勭悊
- 鈴?瀹炵幇鎵归噺澶勭悊浼樺寲

### 21. 鏁版嵁瀹夊叏涓庨殣绉佷繚鎶?鈴?- 鈴?瀹炵幇鏁版嵁鍔犲瘑
- 鈴?瀹炵幇鏉冮檺鎺у埗
- 鈴?瀹炵幇璐﹀彿鍒犻櫎鍔熻兘

### 22. 妫€鏌ョ偣 - 鍚庣鏈嶅姟瀹屾暣鎬ч獙璇?鈴?
### 23-32. Flutter 绉诲姩绔?鈴?- 鈴?椤圭洰鍒濆鍖?- 鈴?璁よ瘉鍔熻兘
- 鈴?鐢ㄦ埛鐢诲儚鍔熻兘
- 鈴?鍥剧墖閲囬泦鍔熻兘
- 鈴?琛ｆ┍绠＄悊鍔熻兘
- 鈴?鐩镐技搴﹀垎鏋愬姛鑳?- 鈴?鎼厤鎺ㄨ崘鍔熻兘
- 鈴?閫傚悎搴﹁瘎鍒嗗姛鑳?
### 33. CLI 宸ュ叿寮€鍙?鈴?
### 34. MCP 鏈嶅姟寮€鍙?鈴?
### 35. 妯″瀷璁粌涓庝紭鍖栵紙鍙€夛級鈴?
### 36. 閮ㄧ讲鍑嗗 鈴?
### 37. 鏈€缁堟鏌ョ偣 鈴?
## 鏁版嵁搴撴ā寮?
### users 琛?- user_id (UUID, PK)
- username (VARCHAR, UNIQUE)
- email (VARCHAR, UNIQUE)
- password_hash (VARCHAR)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)
- is_active (BOOLEAN)

### user_profiles 琛?- profile_id (UUID, PK)
- user_id (UUID, FK 鈫?users)
- height (INTEGER)
- body_type (VARCHAR)
- skin_tone (VARCHAR)
- style_preference (JSONB)
- budget_range (VARCHAR)
- avoid_body_parts (JSONB)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

### garments 琛?- garment_id (UUID, PK)
- user_id (UUID, FK 鈫?users)
- category (VARCHAR)
- main_color (JSONB)
- secondary_colors (JSONB)
- style_tags (JSONB)
- fit_type (VARCHAR)
- image_path (VARCHAR)
- image_url (VARCHAR)
- feature_vector (FLOAT8[])
- notes (TEXT)
- created_at (TIMESTAMP)
- updated_at (TIMESTAMP)

## 鎶€鏈爤璇︽儏

### 鍚庣
- **妗嗘灦**: FastAPI 0.115.6
- **ORM**: SQLAlchemy 2.0.36
- **鏁版嵁搴?*: PostgreSQL 12+
- **缂撳瓨**: Redis 5.2.1
- **璁よ瘉**: JWT (python-jose 3.3.0)
- **瀵嗙爜鍔犲瘑**: Bcrypt 4.2.1
- **鏁版嵁楠岃瘉**: Pydantic 2.10.5
- **杩佺Щ**: Alembic 1.14.0

### AI/ML
- **娣卞害瀛︿範**: TensorFlow 2.18.0
- **妯″瀷**: MobileNetV2 (ImageNet pretrained)
- **鍥惧儚澶勭悊**: OpenCV 4.10.0, Pillow 11.1.0
- **绉戝璁＄畻**: NumPy 1.26.0+, scikit-learn 1.6.1
- **鐗瑰緛鎻愬彇**: 1280 缁?L2-normalized vectors

### 寮€鍙戝伐鍏?- **浠ｇ爜鏍煎紡鍖?*: Black 24.10.0
- **瀵煎叆鎺掑簭**: isort 5.13.2
- **浠ｇ爜妫€鏌?*: Flake8 7.1.1
- **Git Hooks**: Pre-commit 妗嗘灦
- **鎻愪氦瑙勮寖**: Conventional Commits

## 寮€鍙戞寚鍗?
### 鐜璁剧疆

1. 瀹夎渚濊禆锛?```bash
cd backend
pip install -r requirements.txt
```

2. 閰嶇疆鐜鍙橀噺锛?```bash
cp .env.example .env
# 缂栬緫 .env 鏂囦欢閰嶇疆鏁版嵁搴撳拰 Redis
```

3. 鍒濆鍖栨暟鎹簱锛?```bash
python scripts/init_db.py
```

4. 楠岃瘉鍩虹璁炬柦锛?```bash
python scripts/verify_infrastructure.py
```

5. 鍚姩寮€鍙戞湇鍔″櫒锛?```bash
python run.py
# 鎴?uvicorn app.main:app --reload
```

### 璁块棶 API 鏂囨。

- Swagger UI: http://127.0.0.1:8010/docs
- ReDoc: http://127.0.0.1:8010/redoc

### 杩愯娴嬭瘯

```bash
pytest -v
```

### 浠ｇ爜璐ㄩ噺妫€鏌?
```bash
# 杩愯鎵€鏈?pre-commit hooks
pre-commit run --all-files

# 鍗曠嫭杩愯
black backend/
isort backend/
flake8 backend/
```

## 椤圭洰缁撴瀯

```
backend/
鈹溾攢鈹€ app/
鈹?  鈹溾攢鈹€ api/              # API 璺敱
鈹?  鈹?  鈹溾攢鈹€ auth.py       # 璁よ瘉绔偣
鈹?  鈹?  鈹溾攢鈹€ users.py      # 鐢ㄦ埛绔偣
鈹?  鈹?  鈹溾攢鈹€ profile.py    # 鐢ㄦ埛鐢诲儚绔偣
鈹?  鈹?  鈹溾攢鈹€ wardrobe.py   # 琛ｆ┍绠＄悊绔偣
鈹?  鈹?  鈹溾攢鈹€ recognition.py # 鍥惧儚璇嗗埆绔偣
鈹?  鈹?  鈹斺攢鈹€ dependencies.py # 渚濊禆娉ㄥ叆
鈹?  鈹溾攢鈹€ core/             # 鏍稿績閰嶇疆
鈹?  鈹?  鈹溾攢鈹€ config.py     # 搴旂敤閰嶇疆
鈹?  鈹?  鈹溾攢鈹€ logging.py    # 鏃ュ織閰嶇疆
鈹?  鈹?  鈹斺攢鈹€ cache.py      # Redis 缂撳瓨
鈹?  鈹溾攢鈹€ db/               # 鏁版嵁搴?鈹?  鈹?  鈹溾攢鈹€ base.py       # Base 绫?鈹?  鈹?  鈹溾攢鈹€ session.py    # 浼氳瘽绠＄悊
鈹?  鈹?  鈹斺攢鈹€ utils.py      # 宸ュ叿鍑芥暟
鈹?  鈹溾攢鈹€ models/           # ORM 妯″瀷
鈹?  鈹?  鈹溾攢鈹€ user.py
鈹?  鈹?  鈹溾攢鈹€ user_profile.py
鈹?  鈹?  鈹斺攢鈹€ garment.py
鈹?  鈹溾攢鈹€ schemas/          # Pydantic schemas
鈹?  鈹?  鈹溾攢鈹€ user.py
鈹?  鈹?  鈹溾攢鈹€ user_profile.py
鈹?  鈹?  鈹斺攢鈹€ garment.py
鈹?  鈹溾攢鈹€ services/         # 涓氬姟閫昏緫
鈹?  鈹?  鈹溾攢鈹€ auth.py       # 璁よ瘉鏈嶅姟
鈹?  鈹?  鈹溾攢鈹€ user.py       # 鐢ㄦ埛鏈嶅姟
鈹?  鈹?  鈹溾攢鈹€ user_profile.py # 鐢诲儚鏈嶅姟
鈹?  鈹?  鈹溾攢鈹€ garment.py    # 鏈嶉グ鏈嶅姟
鈹?  鈹?  鈹斺攢鈹€ storage.py    # 瀛樺偍鏈嶅姟
鈹?  鈹溾攢鈹€ ml/               # 鏈哄櫒瀛︿範妯″潡
鈹?  鈹?  鈹溾攢鈹€ model_loader.py         # MobileNetV2 妯″瀷鍔犺浇
鈹?  鈹?  鈹溾攢鈹€ image_preprocessor.py   # 鍥惧儚棰勫鐞?鈹?  鈹?  鈹溾攢鈹€ feature_extractor.py    # 鐗瑰緛鎻愬彇
鈹?  鈹?  鈹溾攢鈹€ category_classifier.py  # 鍝佺被鍒嗙被
鈹?  鈹?  鈹溾攢鈹€ color_extractor.py      # 棰滆壊鎻愬彇
鈹?  鈹?  鈹溾攢鈹€ style_classifier.py     # 椋庢牸鍒嗙被
鈹?  鈹?  鈹溾攢鈹€ image_recognizer.py     # 瀹屾暣璇嗗埆娴佺▼
鈹?  鈹?  鈹斺攢鈹€ README.md               # ML 妯″潡鏂囨。
鈹?  鈹斺攢鈹€ main.py           # 搴旂敤鍏ュ彛
鈹溾攢鈹€ scripts/              # 宸ュ叿鑴氭湰
鈹?  鈹溾攢鈹€ init_db.py
鈹?  鈹溾攢鈹€ test_db_connection.py
鈹?  鈹溾攢鈹€ test_redis_connection.py
鈹?  鈹溾攢鈹€ test_model_loading.py
鈹?  鈹斺攢鈹€ verify_infrastructure.py
鈹溾攢鈹€ tests/                # 娴嬭瘯
鈹溾攢鈹€ alembic/              # 鏁版嵁搴撹縼绉?鈹溾攢鈹€ uploads/              # 涓婁紶鏂囦欢
鈹斺攢鈹€ logs/                 # 鏃ュ織鏂囦欢
```

## 璐＄尞鎸囧崡

1. 閬靛惊 Conventional Commits 瑙勮寖
2. 鎵€鏈変唬鐮佸繀椤婚€氳繃 pre-commit hooks
3. 娣诲姞閫傚綋鐨勬祴璇?4. 鏇存柊鐩稿叧鏂囨。

## 璁稿彲璇?
MIT License

## 鑱旂郴鏂瑰紡

椤圭洰浠撳簱: https://github.com/fyw276/clothing-assistant
