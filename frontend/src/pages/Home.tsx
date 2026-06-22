/**
 * Birdle AI home — a single conversational identifier wired to the live SSE
 * backend, rendered with the redesigned mobile / desktop layouts.
 */
import { useBirdleSession } from '../hooks/useBirdleSession';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { MobileBirdle } from '../components/birdle/MobileBirdle';
import { DesktopBirdle } from '../components/birdle/DesktopBirdle';

export function Home() {
  const session = useBirdleSession();
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  return isDesktop ? <DesktopBirdle s={session} /> : <MobileBirdle s={session} />;
}
