// frontend/src/components/BirdBackground.tsx
import { useState, useEffect } from 'react';

interface BirdBackgroundProps {
  src: string;
  className?: string;
}

export default function BirdBackground({ src, className = '' }: BirdBackgroundProps) {
  const [currentSrc, setCurrentSrc] = useState(src);
  const [nextSrc, setNextSrc] = useState<string | null>(null);
  const [showNext, setShowNext] = useState(false);

  useEffect(() => {
    if (src !== currentSrc) {
      // Preload new image, then crossfade
      const img = new Image();
      img.onload = () => {
        setNextSrc(src);
        // Small delay to ensure the element renders before transition
        requestAnimationFrame(() => {
          setShowNext(true);
        });
      };
      img.src = src;
    }
  }, [src, currentSrc]);

  const handleTransitionEnd = () => {
    if (showNext && nextSrc) {
      setCurrentSrc(nextSrc);
      setNextSrc(null);
      setShowNext(false);
    }
  };

  return (
    <div className={`fixed inset-0 ${className}`}>
      {/* Current image */}
      <img
        src={currentSrc}
        alt=""
        className="absolute inset-0 w-full h-full object-cover"
      />
      {/* Next image (crossfade) */}
      {nextSrc && (
        <img
          src={nextSrc}
          alt=""
          className="absolute inset-0 w-full h-full object-cover transition-opacity duration-700"
          style={{ opacity: showNext ? 1 : 0 }}
          onTransitionEnd={handleTransitionEnd}
        />
      )}
      {/* Dark overlay */}
      <div className="absolute inset-0 overlay" />
    </div>
  );
}
