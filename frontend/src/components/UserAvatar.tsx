import { User } from 'lucide-react'

type UserAvatarProps = {
  className?: string
  size?: number
}

/** A neutral account marker shared wherever Avaliance represents a user. */
export function UserAvatar({ className = '', size = 18 }: UserAvatarProps) {
  return (
    <span className={`user-avatar ${className}`.trim()} aria-hidden="true">
      <User size={size} strokeWidth={1.8} />
    </span>
  )
}
