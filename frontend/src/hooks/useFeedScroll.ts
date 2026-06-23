import { useEffect, useRef } from 'react';
import type { FeedItem } from '../components/birdle/types';

const NEAR_BOTTOM_PX = 120;

/**
 * Auto-scrolls a container to the newest item when the feed changes, and keeps
 * it pinned to the bottom as async content (e.g. a result's Wikimedia photo)
 * loads and grows the container after that render — unless the user has
 * scrolled up, in which case it stays put.
 */
export function useFeedScroll(feed: FeedItem[]) {
  const ref = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  const stick = () => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  // A new feed item: jump to the newest and re-pin.
  useEffect(() => {
    pinnedRef.current = true;
    stick();
  }, [feed]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onScroll = () => {
      pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    };
    el.addEventListener('scroll', onScroll, { passive: true });

    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => {
        if (pinnedRef.current) stick();
      });
      // Observe the content (the children grow; the scroll viewport doesn't).
      for (const child of Array.from(el.children)) ro.observe(child);
    }

    return () => {
      el.removeEventListener('scroll', onScroll);
      ro?.disconnect();
    };
  }, [feed]);

  return ref;
}
