import { ReactNode } from 'react';

interface FrostedPanelProps {
  children: ReactNode;
  className?: string;
}

export default function FrostedPanel({ children, className = '' }: FrostedPanelProps) {
  return (
    <div className={`glass rounded-xl p-6 ${className}`}>
      {children}
    </div>
  );
}
