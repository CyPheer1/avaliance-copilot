import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Outlet } from 'react-router-dom'

interface RouteErrorBoundaryProps {
  children?: ReactNode
}

interface RouteErrorBoundaryState {
  error: Error | null
}

export class RouteErrorBoundary extends Component<RouteErrorBoundaryProps, RouteErrorBoundaryState> {
  state: RouteErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): RouteErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Route rendering failed without unmounting the application shell.', error, info)
  }

  render() {
    if (this.state.error) {
      return <section className="page" role="alert"><h1>Cette page n’a pas pu être affichée.</h1><p>{this.state.error.message}</p><button className="button button--secondary" type="button" onClick={() => this.setState({ error: null })}>Réessayer</button></section>
    }
    return this.props.children ?? <Outlet />
  }
}
