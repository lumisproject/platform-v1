import { useState } from 'react'
import { supabase } from '../supabase'

export default function SignUp() {
  const [formData, setFormData] = useState({
    email: '', password: '', fullName: '', phone: '', org: ''
  })

  const handleSignUp = async (e) => {
    e.preventDefault()
    // 1. Create Auth User
    const { data, error } = await supabase.auth.signUp({
      email: formData.email,
      password: formData.password,
    })
    
    if (error) return alert(error.message)

    // 2. Save extra info to 'profiles' table
    if (data.user) {
      await supabase.from('profiles').insert({
        id: data.user.id,
        full_name: formData.fullName,
        phone_number: formData.phone,
        organization: formData.org
      })
      alert("Account created! Check your email.")
    }
  }

  return (
    <form onSubmit={handleSignUp}>
      <input type="email" placeholder="Email" onChange={e => setFormData({...formData, email: e.target.value})} />
      <input type="password" placeholder="Password" onChange={e => setFormData({...formData, password: e.target.value})} />
      <input type="text" placeholder="Full Name" onChange={e => setFormData({...formData, fullName: e.target.value})} />
      <input type="tel" placeholder="Phone Number" onChange={e => setFormData({...formData, phone: e.target.value})} />
      <input type="text" placeholder="Organization" onChange={e => setFormData({...formData, org: e.target.value})} />
      <button type="submit">Sign Up</button>
    </form>
  )
}