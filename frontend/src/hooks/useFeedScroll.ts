import { useEffect, useRef } from 'react';
import type { FeedItem } from '../components/birdle/types';

/** Auto-scrolls a container to the newest item whenever the feed changes. */
export function useFeedScroll(feed: FeedItem[]) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [feed]);
  return ref;
}
