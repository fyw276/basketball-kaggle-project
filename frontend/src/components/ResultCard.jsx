import './ResultCard.css'

/**
 * @param {{
 *   score: number,
 *   recommendations: { outfit: string, score: number }[],
 *   explanation: string,
 *   scoreMax?: number
 * }} props
 */
export function ResultCard({ score, recommendations, explanation, scoreMax = 10 }) {
  return (
    <div className="result-card">
      <div className="result-card__section result-card__section--score">
        <p className="result-card__emoji" aria-hidden="true">
          ⭐
        </p>
        <h2 className="result-card__title">AI评分</h2>
        <p className="result-card__score-line">
          <span className="result-card__score-num">{score.toFixed(1)}</span>
          <span className="result-card__score-slash"> / </span>
          <span className="result-card__score-max">{scoreMax}</span>
        </p>
      </div>

      <div className="result-card__section">
        <p className="result-card__block-title" aria-hidden="true">
          🔥 推荐搭配（Top 3）
        </p>
        <ol className="result-card__list">
          {recommendations.map((item, idx) => (
            <li key={`${item.outfit}-${idx}`} className="result-card__list-item">
              <span className="result-card__rank">{idx + 1}.</span>
              <span className="result-card__outfit">{item.outfit}</span>
              <span className="result-card__item-score">
                ⭐ {item.score.toFixed(1)}
              </span>
            </li>
          ))}
        </ol>
      </div>

      <div className="result-card__section result-card__section--tip">
        <p className="result-card__block-title" aria-hidden="true">
          💡 AI建议
        </p>
        <p className="result-card__explanation">{explanation}</p>
      </div>
    </div>
  )
}
