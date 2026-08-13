import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, readSession, writeSession } from '../api/client.ts'
import type { AuthSession } from '../types.ts'
import { AuthContext } from './auth-context.ts'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<AuthSession | null>(() => readSession())

  useEffect(() => {
    const expire = () => {
      queryClient.clear()
      setSession(null)
    }
    window.addEventListener('avaliance:session-expired', expire)
    return () => window.removeEventListener('avaliance:session-expired', expire)
  }, [queryClient])

  const login = async (username: string, password: string) => {
    const nextSession = await api.login(username, password)
    writeSession(nextSession)
    queryClient.clear()
    setSession(nextSession)
  }

  const logout = () => {
    writeSession(null)
    queryClient.clear()
    setSession(null)
  }

  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>
}
