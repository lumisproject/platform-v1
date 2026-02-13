import { Link } from 'react-router-dom'

export default function Landing() {
  return (
    <div className="container">
      <nav className="flex-between">
        <Link to="/" className="logo">Lumis.</Link>
        <div style={{display:'flex', gap:'1rem'}}>
           <Link to="/login" style={{color: 'var(--text-muted)', textDecoration:'none', fontWeight: 500}}>Log in</Link>
           <Link to="/signup" className="btn" style={{padding: '8px 16px', fontSize:'0.9rem'}}>Sign Up</Link>
        </div>
      </nav>

      <main style={{marginTop: '6rem', maxWidth: '700px'}}>
        <div className="badge">Beta</div>
        <h1 style={{marginTop: '1rem'}}>Talk to your codebase.</h1>
        <p style={{marginBottom: '2rem'}}>
          Lumis creates a semantic digital twin of your repository. 
          Stop grepping. Start asking complex architectural questions about your Python, JS, and Rust projects.
        </p>
        
        <div style={{display:'flex', gap:'1rem', marginBottom: '4rem'}}>
          <Link to="/signup" className="btn">Get Started</Link>
          <a href="https://github.com" target="_blank" className="btn btn-secondary">View Demo</a>
        </div>

        <div style={{borderTop: '1px solid var(--border)', paddingTop: '2rem'}}>
          <h2>How it works</h2>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '2rem', marginTop: '2rem'}}>
            <div>
              <strong>1. Ingest</strong>
              <p style={{fontSize: '0.9rem'}}>We clone your repo and build a graph of function calls and variable dependencies.</p>
            </div>
            <div>
              <strong>2. Vectorize</strong>
              <p style={{fontSize: '0.9rem'}}>Code blocks are embedded into Supabase Vector store for semantic search.</p>
            </div>
            <div>
              <strong>3. Query</strong>
              <p style={{fontSize: '0.9rem'}}>Ask questions like "How does auth flow work?" and get context-aware answers.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}