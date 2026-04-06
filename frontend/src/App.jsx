import { useState } from 'react'
import { getAIScore } from './api/aiScore.js'
import { ResultCard } from './components/ResultCard.jsx'
import { buildExplanation, buildRecommendations, SCORE_MAX } from './utils/recommendations.js'
import './App.css'

const initialForm = {
  top: '',
  bottom: '',
  color_top: '',
  color_bottom: '',
  season: '',
  occasion: '',
}

function App() {
  const [form, setForm] = useState(initialForm)
  const [loading, setLoading] = useState(false)
  const [score, setScore] = useState(null)
  const [recommendations, setRecommendations] = useState([])
  const [explanation, setExplanation] = useState('')
  const [error, setError] = useState('')

  const onChange = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    setError('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    const trimmed = Object.fromEntries(
      Object.entries(form).map(([k, v]) => [k, typeof v === 'string' ? v.trim() : v]),
    )
    const emptyKeys = Object.keys(trimmed).filter((k) => trimmed[k] === '')
    if (emptyKeys.length > 0) {
      setError('请填写全部字段后再获取推荐')
      return
    }

    setLoading(true)
    setError('')
    setScore(null)
    setRecommendations([])
    setExplanation('')

    const result = await getAIScore(trimmed)

    setLoading(false)

    if (!result.ok) {
      setError(result.error || '请求失败，请稍后重试')
      return
    }

    const base = result.score
    setScore(base)
    if (result.recommendations.length > 0 && result.explanation) {
      setRecommendations(result.recommendations)
      setExplanation(result.explanation)
    } else {
      setRecommendations(buildRecommendations(base, trimmed))
      setExplanation(buildExplanation(base))
    }
  }

  return (
    <div className="page">
      <div className="card">
        <header className="card__header">
          <h1>AI 穿搭推荐</h1>
          <p className="card__sub">填写单品与场景，获取评分与推荐搭配</p>
        </header>

        <form className="form" onSubmit={handleSubmit}>
          <div className="form__grid">
            <label className="field">
              <span>上装 top</span>
              <input
                value={form.top}
                onChange={onChange('top')}
                placeholder="例如：衬衫"
                required
              />
            </label>
            <label className="field">
              <span>下装 bottom</span>
              <input
                value={form.bottom}
                onChange={onChange('bottom')}
                placeholder="例如：西裤"
                required
              />
            </label>
            <label className="field">
              <span>上装颜色 color_top</span>
              <input
                value={form.color_top}
                onChange={onChange('color_top')}
                placeholder="white"
                required
              />
            </label>
            <label className="field">
              <span>下装颜色 color_bottom</span>
              <input
                value={form.color_bottom}
                onChange={onChange('color_bottom')}
                placeholder="navy"
                required
              />
            </label>
            <label className="field">
              <span>季节 season</span>
              <input
                value={form.season}
                onChange={onChange('season')}
                placeholder="spring / summer / autumn / winter"
                required
              />
            </label>
            <label className="field">
              <span>场合 occasion</span>
              <input
                value={form.occasion}
                onChange={onChange('occasion')}
                placeholder="office / casual / daily"
                required
              />
            </label>
          </div>

          <button
            type="submit"
            className="btn"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? 'AI分析中…' : '获取推荐'}
          </button>
        </form>

        {error && <p className="msg msg--error">{error}</p>}

        {loading && (
          <div className="result-area result-area--loading" role="status" aria-live="polite">
            <p className="loading-text">🤖 AI正在分析穿搭...</p>
          </div>
        )}

        {!loading && score !== null && recommendations.length > 0 && (
          <div className="result-area">
            <ResultCard
              score={score}
              recommendations={recommendations}
              explanation={explanation}
              scoreMax={SCORE_MAX}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
