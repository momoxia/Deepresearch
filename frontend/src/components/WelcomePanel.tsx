export default function WelcomePanel() {
  return (
    <main className="chat-panel welcome">
      <div className="welcome-content">
        <h1>Deep Research</h1>
        <p>联网检索 + 长记忆：可溯源的研究助手</p>

        <div className="feature-grid">
          <div className="feature-card">
            <span className="feature-icon">🔍</span>
            <h3>搜索与抓取</h3>
            <p>Serper 搜索、正文提取与 Kimi 摘要，可选 Firecrawl 降级</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">🧠</span>
            <h3>项目级记忆</h3>
            <p>语义 / 情景 / 流程 / 偏好分层存储，支持向量检索</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">📎</span>
            <h3>来源面板</h3>
            <p>流式展示访问过的链接，便于核对与回溯</p>
          </div>
          <div className="feature-card">
            <span className="feature-icon">⚡</span>
            <h3>复合工具</h3>
            <p>web_search_and_fetch 并行抓取与总结，加快多源对比</p>
          </div>
        </div>

        <p className="start-hint">← 点击左侧"新建对话"开始</p>
      </div>
    </main>
  );
}
