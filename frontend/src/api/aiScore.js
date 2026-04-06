/**
 * AI 穿搭风格分 API（FastAPI `POST /predict`）
 * 默认 http://127.0.0.1:8765 — 可通过 VITE_API_BASE 覆盖（与 Flutter `PREDICT_API_PORT` / 独立 predict 服务对齐）
 */
const PREDICT_URL =
  import.meta.env.VITE_API_BASE != null && String(import.meta.env.VITE_API_BASE).trim() !== ''
    ? `${String(import.meta.env.VITE_API_BASE).replace(/\/$/, '')}/predict`
    : 'http://127.0.0.1:8765/predict'

/**
 * @param {Record<string, string>} data - top, bottom, color_top, color_bottom, season, occasion
 * @returns {Promise<
 *   | { ok: true, score: number, recommendations: { outfit: string, score: number }[], explanation: string }
 *   | { ok: false, error: string }
 * >}
 */
export async function getAIScore(data) {
  try {
    const res = await fetch(PREDICT_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    })

    const payload = await res.json().catch(() => ({}))

    if (!res.ok) {
      const detail = payload?.detail
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail) && detail[0]?.msg
            ? String(detail[0].msg)
            : `请求失败（HTTP ${res.status}）`
      console.error('AI接口HTTP错误:', res.status, payload)
      return { ok: false, error: msg }
    }

    if (typeof payload.score !== 'number' || Number.isNaN(payload.score)) {
      return { ok: false, error: '未返回有效分数' }
    }

    const recRaw = payload.recommendations
    const recommendations = Array.isArray(recRaw)
      ? recRaw
          .map((r) => {
            if (r && typeof r === 'object' && typeof r.outfit === 'string') {
              const s = r.score
              const num = typeof s === 'number' && !Number.isNaN(s) ? s : Number(s)
              return { outfit: r.outfit, score: Number.isFinite(num) ? num : payload.score }
            }
            return null
          })
          .filter(Boolean)
      : []

    const explanation =
      typeof payload.explanation === 'string' && payload.explanation.trim() !== ''
        ? payload.explanation
        : ''

    return {
      ok: true,
      score: payload.score,
      recommendations,
      explanation,
    }
  } catch (err) {
    console.error('AI接口调用失败:', err)
    const message = err instanceof Error ? err.message : String(err)
    return { ok: false, error: message || '网络错误' }
  }
}

export { PREDICT_URL }
