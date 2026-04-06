/**
 * 基于模型 score 与当前表单，在前端生成 Top3 推荐与解释（模拟逻辑）
 */

const SCORE_MAX = 10

/**
 * @param {number} base
 * @param {Record<string, string>} form
 * @returns {{ outfit: string, score: number }[]}
 */
export function buildRecommendations(base, form) {
  const primary = `${form.top.trim()} + ${form.bottom.trim()}`
  const s1 = base
  const s2 = Math.max(0, base - 0.3)
  const s3 = Math.max(0, base - 0.6)
  return [
    { outfit: primary, score: s1 },
    { outfit: 'Shirt + Chinos', score: s2 },
    { outfit: 'Hoodie + Joggers', score: s3 },
  ]
}

/**
 * @param {number} base
 * @returns {string}
 */
export function buildExplanation(base) {
  return base > 8
    ? '颜色搭配协调，适合当前季节和场景'
    : '搭配一般，可以尝试更协调的颜色组合'
}

export { SCORE_MAX }
