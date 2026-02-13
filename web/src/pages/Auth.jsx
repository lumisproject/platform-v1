import { useState } from 'react'
import { supabase } from '../supabase'
import { useNavigate } from 'react-router-dom'

export default function Auth({ type = 'login' }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [formData, setFormData] = useState({
    email: '', password: '', fullName: '', phone: '', org: ''
  })

  const handleAuth = async (e) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      if (type === 'signup') {
        const { data, error } = await supabase.auth.signUp({
          email: formData.email,
          password: formData.password,
        })
        if (error) throw error
        
        // Create Profile
        if (data.user) {
          await supabase.from('profiles').insert({
            id: data.user.id,
            full_name: formData.fullName,
            phone_number: formData.phone,
            organization: formData.org
          })
          alert('Check your email for the confirmation link.')
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({
          email: formData.email,
          password: formData.password,
        })
        if (error) throw error
        navigate('/dashboard')
      }
    } catch (error) {
      alert(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <nav>
        <a href="/" className="logo">Lumis.</a>
      </nav>
      <div className="auth-box">
        <h2 style={{marginTop: 0}}>{type === 'signup' ? 'Create Account' : 'Welcome Back'}</h2>
        <form onSubmit={handleAuth} className="flex-col">
          
          {type === 'signup' && (
            <>
              <input placeholder="Full Name" required onChange={e => setFormData({...formData, fullName: e.target.value})} />
              <input placeholder="Organization" onChange={e => setFormData({...formData, org: e.target.value})} />
              <input placeholder="Phone Number" type="tel" onChange={e => setFormData({...formData, phone: e.target.value})} />
            </>
          )}

          <input type="email" placeholder="name@company.com" required onChange={e => setFormData({...formData, email: e.target.value})} />
          <input type="password" placeholder="Password" required onChange={e => setFormData({...formData, password: e.target.value})} />
          
          <button type="submit" className="btn" disabled={loading}>
            {loading ? 'Processing...' : (type === 'signup' ? 'Sign Up' : 'Log In')}
          </button>
        </form>
        
        <p style={{fontSize: '0.9rem', marginTop: '1.5rem', textAlign: 'center'}}>
          {type === 'signup' ? "Already have an account? " : "Don't have an account? "}
          <a href={type === 'signup' ? '/login' : '/signup'} style={{color: 'var(--accent)'}}>
            {type === 'signup' ? 'Log in' : 'Sign up'}
          </a>
        </p>
      </div>
    </div>
  )
}