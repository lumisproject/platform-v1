import { useState, useEffect, useRef } from 'react'
import { supabase } from '../supabase'
import { useNavigate } from 'react-router-dom'
import IngestionWizard from '../components/IngestionWizard'
import ReactMarkdown from 'react-markdown'

export default function Dashboard() {
  const navigate = useNavigate()

  // -- State: User & Project --
  const [session, setSession] = useState(null)
  const [projectData, setProjectData] = useState(null)
  const [repoUrl, setRepoUrl] = useState('')

  // ...existing code...

  // -- State: Ingestion & Chat --
  const [isIngesting, setIsIngesting] = useState(false)
  const [ingestionProjectId, setIngestionProjectId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const bottomRef = useRef(null)

  // 1. Initial Load: Auth and Project Check
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        navigate('/login')
      } else {
        setSession(session)
        fetchUserProject(session.user.id)
      }
    })
  }, [])

  // 2. Poll for updates (Project)
  useEffect(() => {
    if (!session?.user?.id) return
    const interval = setInterval(() => {
      fetchUserProject(session.user.id)
    }, 15000) // Poll every 15s
    return () => clearInterval(interval)
  }, [session])

  const fetchUserProject = async (userId) => {
    const { data } = await supabase.from('projects').select('*').eq('user_id', userId).single()
    if (data) setProjectData(data)
  }

  // ...existing code...

  const handleIngest = async () => {
    if (!repoUrl.trim()) return alert("Please enter a GitHub URL")
    try {
      const res = await fetch('http://localhost:5000/api/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: session.user.id, repo_url: repoUrl })
      })
      const data = await res.json()
      if (res.ok) {
        setIngestionProjectId(data.project_id)
        setIsIngesting(true)
      }
    } catch (e) { alert("Error: " + e.message) }
  }

  const handleChat = async (e) => {
    e.preventDefault()
    if (!input.trim() || chatLoading) return
    const userMsg = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setChatLoading(true)
    
    try {
      const res = await fetch('http://localhost:5000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: projectData.id, query: userMsg.content })
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'lumis', content: data.response }])
    } finally {
      setChatLoading(false)
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  if (!session) return null
  const webhookUrl = projectData ? `https://unsparing-kaley-unmodest.ngrok-free.dev/api/webhook/${session.user.id}/${projectData.id}` : ''

  return (
    <div className="container">
      {isIngesting && <IngestionWizard projectId={ingestionProjectId} onComplete={() => { setIsIngesting(false); fetchUserProject(session.user.id); }} />}

      <nav className="flex-between">
        <span className="logo">Lumis Intelligence</span>
        <div className="flex-center" style={{ gap: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{session.user.email}</span>
          <button onClick={() => supabase.auth.signOut().then(() => navigate('/'))} className="btn btn-secondary">Log Out</button>
        </div>
      </nav>

      <main style={{ marginTop: '2rem' }}>
        {!projectData?.id ? (
          <div style={{ maxWidth: '500px', margin: '4rem auto', textAlign: 'center' }}>
            <h2>Analyze your Codebase</h2>
            <div className="flex-col" style={{ marginTop: '1.5rem' }}>
              <input type="text" placeholder="GitHub Repo URL" value={repoUrl} onChange={e => setRepoUrl(e.target.value)} />
              <button onClick={handleIngest} className="btn">Build Digital Twin</button>
            </div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '2rem' }}>
            
            {/* CHAT SECTION */}
            <div className="chat-window">
              <div className="messages-area" style={{ height: '550px' }}>
                {messages.length === 0 && <div style={{ textAlign: 'center', marginTop: '4rem', opacity: 0.5 }}><h3>Digital Twin Active</h3><p>Syncing with {projectData.repo_url.split('/').pop()}</p></div>}
                {messages.map((m, i) => (
                  <div key={i} className={`message ${m.role}`}>
                    {m.role === 'lumis' ? <ReactMarkdown>{m.content}</ReactMarkdown> : m.content}
                  </div>
                ))}
                {chatLoading && <div className="message lumis">Analyzing...</div>}
                <div ref={bottomRef} />
              </div>
              <form onSubmit={handleChat} className="input-area">
                <input value={input} onChange={e => setInput(e.target.value)} placeholder="Ask about logic, bugs, or architecture..." />
                <button type="submit" className="btn">Send</button>
              </form>
            </div>

            {/* SIDEBAR: PROJECT */}
            <div className="flex-col" style={{ gap: '1.5rem' }}>
              {/* WEBHOOK CARD */}
              <div style={{ padding: '1.5rem', border: '1px solid var(--border)', borderRadius: '12px', background: '#f9f9f9' }}>
                <h4 style={{ margin: 0 }}>Sync Status</h4>
                <div style={{ fontSize: '0.8rem', margin: '1rem 0' }}>
                  <div className="flex-between"><span>Last Hash:</span> <code>{projectData.last_commit?.substring(0,7)}</code></div>
                </div>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Webhook URL:</p>
                <div style={{ background: '#fff', border: '1px solid #ddd', padding: '6px', fontSize: '0.65rem', borderRadius: '4px', overflow: 'hidden' }}>{webhookUrl}</div>
                <button className="btn btn-secondary" style={{ width: '100%', marginTop: '0.5rem', fontSize: '0.7rem' }} onClick={() => { navigator.clipboard.writeText(webhookUrl); alert("Copied!"); }}>Copy Webhook</button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}