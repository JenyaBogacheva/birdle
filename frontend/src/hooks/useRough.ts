import { useRef, useEffect, useState } from 'react';
import rough from 'roughjs';
import type { RoughSVG } from 'roughjs/bin/svg';

export function useRough() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [rc, setRc] = useState<RoughSVG | null>(null);

  useEffect(() => {
    if (svgRef.current) {
      setRc(rough.svg(svgRef.current));
    }
  }, []);

  return { svgRef, rc };
}
