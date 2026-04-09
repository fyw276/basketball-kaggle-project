/// 后端 HTTP 端口，须与 `backend` 中 `PORT` / `uvicorn --port` 一致。
///
/// 默认 **8010**，避免与本机其它占用 **8000** 的服务冲突（登录 404、根路径非本仓库）。
/// 若需改端口：`flutter run --dart-define=API_PORT=xxxx`，后端同端口启动 uvicorn。
const int kApiPort = int.fromEnvironment('API_PORT', defaultValue: 8010);

/// 默认 ApiClient baseUrl（无 [resolveApiBaseUrl] 时回退）。
String get kDefaultApiBaseUrl => 'http://127.0.0.1:$kApiPort/api/v1';

/// AI 穿搭风格分 `POST /predict` 端口。
///
/// 当前后端已把 `/predict` 挂在主服务（8010）上，默认保持同端口；
/// 如需独立预测服务，可通过 `--dart-define=PREDICT_API_PORT=xxxx` 覆盖。
const int kPredictApiPort =
    int.fromEnvironment('PREDICT_API_PORT', defaultValue: 8010);

/// 默认预测服务根 URL（无 `/api/v1`，路径为 `/predict`）。
String get kDefaultPredictApiBaseUrl => 'http://127.0.0.1:$kPredictApiPort';
