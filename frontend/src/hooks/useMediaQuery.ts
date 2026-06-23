import { useEffect, useState } from 'react';

/** Subscribe to a CSS media query. SSR-safe (defaults to false). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && 'matchMedia' in window
      ? window.matchMedia(query).matches
      : false,
  );

  useEffect(() => {
    if (typeof window === 'undefined' || !('matchMedia' in window)) return;
    const mql = window.matchMedia(query);
    // Re-sync only when the value actually differs (covers a changed `query`);
    // the useState initializer already matched on first mount, so an unchanged
    // value bails the re-render rather than forcing a redundant one.
    const onChange = () => setMatches((prev) => (prev === mql.matches ? prev : mql.matches));
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}
